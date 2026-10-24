"""F1-36: pré-anotação, validação da anotação e avaliação de modelos locais de NER.

Roda NA MÁQUINA DO ANOTADOR, sobre ``amostra.jsonl`` gerada por ``ner_amostragem.py``.
Tudo é local: os modelos são baixados uma vez e rodam na máquina; nenhum texto sai dela.

Marcação (campo ``texto_anotado``, ver ``docs/ner-anotacao.md``):

- ``[[Nome]]``: pessoa física que deve ser anonimizada (parte, vítima, testemunha…);
- ``{{Nome}}``: nome que deve ficar (relator, magistrado citado, epônimo, doutrinador).

Comandos (de ``backend/``; as dependências dos modelos entram só com ``--with``)::

    uv run --with "spacy>=3.8,<3.9" python scripts/ner_avaliacao.py preanotar \\
        --modelo spacy --entrada AMOSTRA --saida AMOSTRA_PREANOTADA
    uv run python scripts/ner_avaliacao.py validar --entrada AMOSTRA_ANOTADA
    uv run --with "spacy>=3.8,<3.9" --with "transformers>=4.44,<5" --with torch \\
        python scripts/ner_avaliacao.py avaliar --entrada AMOSTRA_ANOTADA \\
        --relatorio ../docs/avaliacao-ner.md

O relatório tem **só métricas agregadas**: nenhum trecho de ementa, nome ou id de amostra.
"""

import argparse
import json
import re
import statistics
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from buscajus.ingest.anonimizacao.camada2 import Entidade, selecionar
from buscajus.ingest.anonimizacao.nomes import PARTICULAS, alinhado

MARCACAO = re.compile(r"\[\[(.+?)\]\]|\{\{(.+?)\}\}", re.DOTALL)
SPACY_PADRAO = "pt_core_news_lg"
LENERBR_PADRAO = "pierreguillou/ner-bert-base-cased-pt-lenerbr"
LIMIARES = (0.3, 0.5, 0.7, 0.9)


@dataclass(frozen=True)
class Marca:
    inicio: int
    fim: int
    anonimizar: bool


def ler_marcacao(anotado: str) -> tuple[str, list[Marca]]:
    partes: list[str] = []
    marcas: list[Marca] = []
    tamanho = 0
    ultimo = 0
    for m in MARCACAO.finditer(anotado):
        antes = anotado[ultimo : m.start()]
        partes.append(antes)
        tamanho += len(antes)
        nome = m.group(1) if m.group(1) is not None else m.group(2)
        marcas.append(Marca(tamanho, tamanho + len(nome), m.group(1) is not None))
        partes.append(nome)
        tamanho += len(nome)
        ultimo = m.end()
    partes.append(anotado[ultimo:])
    return "".join(partes), marcas


def marcar(texto: str, entidades: Iterable[Entidade]) -> str:
    saida: list[str] = []
    ultimo = 0
    for e in sorted(entidades, key=lambda e: e.inicio):
        if e.inicio < ultimo:
            continue
        saida += [texto[ultimo : e.inicio], "[[", texto[e.inicio : e.fim], "]]"]
        ultimo = e.fim
    saida.append(texto[ultimo:])
    return "".join(saida)


def ler(caminho: Path) -> list[dict[str, Any]]:
    with caminho.open(encoding="utf-8") as arquivo:
        return [json.loads(linha) for linha in arquivo if linha.strip()]


def gravar(caminho: Path, registros: Sequence[dict[str, Any]]) -> None:
    with caminho.open("w", encoding="utf-8") as arquivo:
        for registro in registros:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
    caminho.chmod(0o600)


# --- Modelos locais --------------------------------------------------------------------

Detectar = Callable[[str], list[tuple[Entidade, float]]]


def modelo_spacy(nome: str) -> Detectar:
    import spacy  # dependência opcional, só na máquina do anotador

    nlp = spacy.load(nome)

    def detectar(texto: str) -> list[tuple[Entidade, float]]:
        return [
            (Entidade(ent.start_char, ent.end_char), 1.0)
            for ent in nlp(texto).ents
            if ent.label_ in {"PER", "PERSON", "PESSOA"}
        ]

    return detectar


def modelo_hf(nome: str) -> Detectar:
    from transformers import pipeline

    ner = pipeline("token-classification", model=nome, aggregation_strategy="simple")

    def detectar(texto: str) -> list[tuple[Entidade, float]]:
        return [
            (Entidade(int(r["start"]), int(r["end"])), float(r["score"]))
            for r in ner(texto)
            if str(r.get("entity_group", "")).upper() in {"PESSOA", "PER", "PERSON"}
        ]

    return detectar


def carregar(modelo: str, nome: str | None) -> Detectar:
    if modelo == "spacy":
        return modelo_spacy(nome or SPACY_PADRAO)
    return modelo_hf(nome or LENERBR_PADRAO)


# --- Métricas ----------------------------------------------------------------------------


def _tokens(texto: str, inicio: int, fim: int) -> list[tuple[int, int]]:
    trecho = alinhado(texto[inicio:fim])
    return [
        (inicio + m.start(), inicio + m.end())
        for m in re.finditer(r"[A-Z0-9]+", trecho)
        if m.group() not in PARTICULAS and len(m.group()) > 1
    ]


def _coberto(token: tuple[int, int], previstas: Sequence[Entidade]) -> bool:
    return any(p.inicio <= token[0] and token[1] <= p.fim for p in previstas)


@dataclass
class Placar:
    ementas: int = 0
    anonimizar: int = 0
    anonimizar_total: int = 0  # todos os tokens cobertos
    anonimizar_parcial: int = 0  # pelo menos um token coberto
    manter: int = 0
    manter_preservados: int = 0
    previstas: int = 0
    previstas_corretas: int = 0

    def somar(self, texto: str, marcas: Sequence[Marca], previstas: Sequence[Entidade]) -> None:
        self.ementas += 1
        for marca in marcas:
            tokens = _tokens(texto, marca.inicio, marca.fim)
            cobertos = [t for t in tokens if _coberto(t, previstas)]
            if marca.anonimizar:
                self.anonimizar += 1
                self.anonimizar_total += bool(tokens) and len(cobertos) == len(tokens)
                self.anonimizar_parcial += bool(cobertos)
            else:
                self.manter += 1
                self.manter_preservados += not cobertos
        ouro = [m for m in marcas if m.anonimizar]
        self.previstas += len(previstas)
        self.previstas_corretas += sum(
            any(p.inicio < m.fim and m.inicio < p.fim for m in ouro) for p in previstas
        )

    def linha(self) -> dict[str, str]:
        def taxa(a: int, b: int) -> str:
            return f"{a / b:.3f}" if b else "-"

        return {
            "ementas": str(self.ementas),
            "nomes a anonimizar": str(self.anonimizar),
            "recall (nome inteiro)": taxa(self.anonimizar_total, self.anonimizar),
            "recall (algum token)": taxa(self.anonimizar_parcial, self.anonimizar),
            "precisão": taxa(self.previstas_corretas, self.previstas),
            "nomes a manter": str(self.manter),
            "manter preservados": taxa(self.manter_preservados, self.manter),
        }


def avaliar(
    registros: Sequence[dict[str, Any]], detectar: Detectar, limiar: float
) -> tuple[dict[str, Placar], float]:
    placares: dict[str, Placar] = {}
    tempos: list[float] = []
    for registro in registros:
        texto, marcas = ler_marcacao(registro["texto_anotado"])
        inicio = time.perf_counter()
        brutas = [e for e, score in detectar(texto) if score >= limiar]
        tempos.append(time.perf_counter() - inicio)
        previstas = selecionar(texto, brutas)
        for chave in (registro["estrato"], "total"):
            placares.setdefault(chave, Placar()).somar(texto, marcas, previstas)
    return placares, statistics.mean(tempos) if tempos else 0.0


def tabela(linhas: Sequence[tuple[str, dict[str, str]]]) -> str:
    colunas = list(linhas[0][1])
    saida = ["| | " + " | ".join(colunas) + " |", "|---" * (len(colunas) + 1) + "|"]
    saida += [
        f"| {rotulo} | " + " | ".join(dados[c] for c in colunas) + " |" for rotulo, dados in linhas
    ]
    return "\n".join(saida)


# --- Comandos ----------------------------------------------------------------------------


def cmd_preanotar(args: argparse.Namespace) -> int:
    detectar = carregar(args.modelo, args.nome_modelo)
    registros = ler(args.entrada)
    for registro in registros:
        if registro.get("texto_anotado") is None:
            entidades = [e for e, _ in detectar(registro["texto"])]
            registro["texto_anotado"] = marcar(registro["texto"], entidades)
    gravar(args.saida, registros)
    print(f"pré-anotadas: {len(registros)} ementas")
    return 0


def problemas(registro: dict[str, Any]) -> list[str]:
    anotado = registro.get("texto_anotado")
    if not isinstance(anotado, str):
        return ["sem anotação"]
    texto, _ = ler_marcacao(anotado)
    erros = []
    if texto != registro["texto"]:
        erros.append("o texto sem marcação difere do original")
    if any(s in texto for s in ("[[", "]]", "{{", "}}")):
        erros.append("marcação desbalanceada")
    return erros


def cmd_validar(args: argparse.Namespace) -> int:
    registros = ler(args.entrada)
    com_erro = 0
    for registro in registros:
        for erro in problemas(registro):
            com_erro += 1
            print(f"{registro['id_amostra']}: {erro}")
    print(f"{len(registros)} ementas, {com_erro} problemas")
    return 1 if com_erro else 0


def cmd_avaliar(args: argparse.Namespace) -> int:
    registros = ler(args.entrada)
    invalidos = [r for r in registros if problemas(r)]
    if invalidos:
        print(f"{len(invalidos)} ementas com anotação inválida; rode o comando validar")
        return 1
    modelos = [("spacy", args.spacy), ("lenerbr", args.lenerbr)]
    secoes = [
        "# Avaliação do NER de pessoas (F1-36)",
        "",
        f"Gerado em {datetime.now(UTC).date().isoformat()} por `scripts/ner_avaliacao.py`, "
        f"sobre {len(registros)} ementas anotadas (já processadas pela camada 1). **Só métricas "
        "agregadas**: nenhum trecho de ementa nem nome.",
        "",
        "- *recall (nome inteiro)*: nomes a anonimizar com todos os tokens substituídos.",
        "- *recall (algum token)*: nomes com pelo menos um token substituído.",
        "- *precisão*: substituições que caíram num nome a anonimizar.",
        "- *manter preservados*: relatores, magistrados citados, epônimos etc. não substituídos.",
        "- As exceções da camada 2 (relator, títulos de magistrado, epônimos) já estão aplicadas.",
        "",
    ]
    for modelo, nome in modelos:
        detectar = carregar(modelo, nome)
        limiares = (0.0,) if modelo == "spacy" else LIMIARES
        for limiar in limiares:
            placares, tempo = avaliar(registros, detectar, limiar)
            titulo = (
                f"## {modelo} (`{nome or (SPACY_PADRAO if modelo == 'spacy' else LENERBR_PADRAO)}`)"
            )
            if modelo != "spacy":
                titulo += f", limiar {limiar}"
            ordem = ["criminal", "familia", "civel", "total"]
            secoes += [
                titulo,
                "",
                tabela([(e, placares[e].linha()) for e in ordem if e in placares]),
                "",
                f"Tempo médio por ementa: {tempo * 1000:.0f} ms.",
                "",
            ]
    secoes += [
        "## Decisão",
        "",
        "_A preencher: modelo escolhido, limiar, meta de recall, lista de exceções e data._",
        "",
    ]
    args.relatorio.write_text("\n".join(secoes), encoding="utf-8")
    print(f"relatório gravado em {args.relatorio}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("preanotar")
    p.add_argument("--entrada", type=Path, required=True)
    p.add_argument("--saida", type=Path, required=True)
    p.add_argument("--modelo", choices=["spacy", "lenerbr"], default="spacy")
    p.add_argument("--nome-modelo")
    p.set_defaults(executar=cmd_preanotar)
    v = sub.add_parser("validar")
    v.add_argument("--entrada", type=Path, required=True)
    v.set_defaults(executar=cmd_validar)
    a = sub.add_parser("avaliar")
    a.add_argument("--entrada", type=Path, required=True)
    a.add_argument("--relatorio", type=Path, required=True)
    a.add_argument("--spacy", default=SPACY_PADRAO)
    a.add_argument("--lenerbr", default=LENERBR_PADRAO)
    a.set_defaults(executar=cmd_avaliar)
    args = parser.parse_args()
    codigo: int = args.executar(args)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
