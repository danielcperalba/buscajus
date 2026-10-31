"""Ferramenta de avaliação da busca (F3-04; ARCHITECTURE.md, seção 7.1).

1. ``carregar_consultas``: conjunto versionado (``backend/eval/consultas.yaml``, F3-01).
2. ``gerar_pool``: top-k (20) de cada sistema por consulta, sem repetição, para julgamento.
3. ``exportar_pool``/``importar_julgamentos``: planilha CSV com a coluna ``relevancia``
   (0, 1 ou 2) preenchida por pessoa com formação jurídica.
4. ``avaliar``: nDCG@10, Recall@50 e MRR por sistema, com a latência das consultas.

O pool exportado traz o início da ementa para o julgamento: é um arquivo de trabalho, que
fica fora do repositório.
"""

import csv
import math
import statistics
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from buscajus.embed.indice import Sistema

Julgamentos = dict[tuple[str, str], int]  # (consulta, documento) → 0, 1 ou 2
CAMPOS_POOL = ("consulta_id", "consulta", "documento_id", "sistemas", "trecho", "relevancia")


@dataclass(frozen=True)
class Consulta:
    id: str
    texto: str
    area: str = ""
    obrigatoria: bool = False
    esperado: str = ""


def carregar_consultas(caminho: Path) -> list[Consulta]:
    conteudo = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    consultas = [
        Consulta(
            id=str(c["id"]),
            texto=str(c["texto"]),
            area=str(c.get("area", "")),
            obrigatoria=bool(c.get("obrigatoria", False)),
            esperado=str(c.get("esperado", "")),
        )
        for c in conteudo["consultas"]
    ]
    ids = [c.id for c in consultas]
    if len(set(ids)) != len(ids):
        raise ValueError("ids de consulta repetidos")
    return consultas


# --- Métricas -------------------------------------------------------------------------


def dcg(relevancias: Sequence[int]) -> float:
    return float(sum((2**r - 1) / math.log2(i + 2) for i, r in enumerate(relevancias)))


def ndcg(ranking: Sequence[str], relevancia: Mapping[str, int], k: int = 10) -> float:
    ideal = dcg(sorted(relevancia.values(), reverse=True)[:k])
    if ideal == 0:
        return 0.0
    return dcg([relevancia.get(doc, 0) for doc in ranking[:k]]) / ideal


def recall(ranking: Sequence[str], relevancia: Mapping[str, int], k: int = 50) -> float:
    relevantes = {doc for doc, r in relevancia.items() if r > 0}
    if not relevantes:
        return 0.0
    return len(relevantes & set(ranking[:k])) / len(relevantes)


def mrr(ranking: Sequence[str], relevancia: Mapping[str, int]) -> float:
    for posicao, doc in enumerate(ranking, start=1):
        if relevancia.get(doc, 0) > 0:
            return 1 / posicao
    return 0.0


# --- Pool e julgamentos ---------------------------------------------------------------


@dataclass
class ItemPool:
    consulta: Consulta
    documento_id: str
    sistemas: dict[str, int] = field(default_factory=dict)  # sistema → posição (1 = topo)


def gerar_pool(
    consultas: Sequence[Consulta], sistemas: Sequence[Sistema], k: int = 20
) -> list[ItemPool]:
    pool: list[ItemPool] = []
    for consulta in consultas:
        por_documento: dict[str, ItemPool] = {}
        for sistema in sistemas:
            for posicao, resultado in enumerate(sistema.buscar(consulta.texto, k), start=1):
                item = por_documento.setdefault(resultado.id, ItemPool(consulta, resultado.id))
                item.sistemas[sistema.nome] = posicao
        pool += sorted(por_documento.values(), key=lambda i: min(i.sistemas.values()))
    return pool


def exportar_pool(
    pool: Iterable[ItemPool], textos: Mapping[str, str], destino: Path, tamanho_trecho: int = 400
) -> None:
    with destino.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=CAMPOS_POOL)
        escritor.writeheader()
        for item in pool:
            escritor.writerow(
                {
                    "consulta_id": item.consulta.id,
                    "consulta": item.consulta.texto,
                    "documento_id": item.documento_id,
                    "sistemas": "; ".join(f"{s}#{p}" for s, p in sorted(item.sistemas.items())),
                    "trecho": " ".join(textos.get(item.documento_id, "").split())[:tamanho_trecho],
                    "relevancia": "",
                }
            )


def importar_julgamentos(origem: Path) -> Julgamentos:
    """Lê a planilha julgada; linhas sem relevância ficam de fora (não julgadas)."""
    julgamentos: Julgamentos = {}
    with origem.open(encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            valor = (linha.get("relevancia") or "").strip()
            if not valor:
                continue
            relevancia = int(valor)
            if relevancia not in (0, 1, 2):
                raise ValueError(f"relevância inválida na consulta {linha['consulta_id']}")
            julgamentos[(linha["consulta_id"], linha["documento_id"])] = relevancia
    return julgamentos


# --- Avaliação ------------------------------------------------------------------------


@dataclass
class Relatorio:
    sistema: str
    consultas: int
    ndcg_10: float
    recall_50: float
    mrr: float
    latencia_p50_ms: float
    latencia_p95_ms: float
    por_consulta: dict[str, dict[str, float]] = field(default_factory=dict)

    def resumo(self) -> dict[str, Any]:
        return {
            "sistema": self.sistema,
            "consultas": self.consultas,
            "ndcg@10": round(self.ndcg_10, 4),
            "recall@50": round(self.recall_50, 4),
            "mrr": round(self.mrr, 4),
            "latencia_p50_ms": round(self.latencia_p50_ms, 1),
            "latencia_p95_ms": round(self.latencia_p95_ms, 1),
        }


def _percentil(valores: Sequence[float], p: float) -> float:
    if len(valores) == 1:
        return valores[0]
    return statistics.quantiles(valores, n=100, method="inclusive")[int(p) - 1]


def avaliar(
    consultas: Sequence[Consulta],
    sistemas: Sequence[Sistema],
    julgamentos: Julgamentos,
    *,
    k: int = 50,
) -> list[Relatorio]:
    """Métricas por sistema, só sobre as consultas que têm julgamentos."""
    por_consulta: dict[str, dict[str, int]] = {}
    for (consulta_id, documento_id), nota in julgamentos.items():
        por_consulta.setdefault(consulta_id, {})[documento_id] = nota
    julgadas = [c for c in consultas if c.id in por_consulta]
    if not julgadas:
        raise ValueError("nenhuma consulta com julgamento")
    relatorios = []
    for sistema in sistemas:
        latencias: list[float] = []
        metricas: dict[str, dict[str, float]] = {}
        for consulta in julgadas:
            antes = time.perf_counter()
            ranking = [r.id for r in sistema.buscar(consulta.texto, k)]
            latencias.append((time.perf_counter() - antes) * 1000)
            relevancia = por_consulta[consulta.id]
            metricas[consulta.id] = {
                "ndcg@10": ndcg(ranking, relevancia, 10),
                "recall@50": recall(ranking, relevancia, 50),
                "mrr": mrr(ranking, relevancia),
            }
        relatorios.append(
            Relatorio(
                sistema=sistema.nome,
                consultas=len(julgadas),
                ndcg_10=statistics.fmean(m["ndcg@10"] for m in metricas.values()),
                recall_50=statistics.fmean(m["recall@50"] for m in metricas.values()),
                mrr=statistics.fmean(m["mrr"] for m in metricas.values()),
                latencia_p50_ms=_percentil(latencias, 50),
                latencia_p95_ms=_percentil(latencias, 95),
                por_consulta=metricas,
            )
        )
    return relatorios
