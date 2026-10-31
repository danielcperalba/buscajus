"""Revisão por amostra das ementas já anonimizadas (F1-42; ARCHITECTURE.md, seção 6.7).

Quem revisa é uma pessoa, no próprio terminal. Os textos da amostra e os trechos marcados como
vazamento ficam **só** na pasta privada (``ner-avaliacao-privado/``, fora do git); o resultado
gravado em ``docs/`` tem apenas agregados.

- :func:`amostrar`: sorteia ementas ativas do banco local, estratificadas por tribunal e área
  (TJPR: ~50% câmaras criminais, ~25% família, ~25% cível; TJDFT: uma fração da amostra).
- :func:`revisar`: mostra uma ementa por vez e registra "ok" ou "vazou" (com o trecho que
  escapou); salva a cada resposta, para parar e continuar depois. "Vazou" põe o acórdão em
  quarentena na hora.
- :func:`resultado`: revisadas, vazamentos, taxa e limite superior de 95%.
- :func:`verificar`: confere se as regras atuais pegam os trechos marcados (só contagens).

Critério de aprovação: 0 vazamentos em 100 ementas revisadas.
"""

import json
import math
import os
import random
import re
import shutil
import textwrap
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text

from buscajus.core.erros import ErroSeguro
from buscajus.ingest.anonimizacao import camada2 as c2
from buscajus.ingest.anonimizacao.cpf import mascarar_cpf
from buscajus.ingest.anonimizacao.documentos import mascarar_documentos
from buscajus.ingest.anonimizacao.nomes import alinhado, tokens
from buscajus.ingest.texto import chave
from buscajus.ingest.upsert import marcar_vazamento

NOME_PASTA = "ner-avaliacao-privado"
AMOSTRA = "amostra.jsonl"
RESPOSTAS = "respostas.jsonl"
HISTORICO = "historico.json"  # só agregados de cada rodada
RODADAS = "rodadas"

# Proporções dentro de cada tribunal. No TJPR, família e sucessões ficam na 11ª e na 12ª
# Câmara Cível; no TJDFT não há turma própria, e família entra em cível.
PROPORCOES: dict[str, dict[str, float]] = {
    "TJPR": {"criminal": 0.50, "familia": 0.25, "civel": 0.25},
    "TJDFT": {"criminal": 0.50, "civel": 0.50},
}
ORGAOS_FAMILIA = {"TJPR": ("11ª Câmara Cível", "12ª Câmara Cível")}
FRACAO_TJDFT = 0.20
META_APROVACAO = 100
CONFIANCA = 0.95


class ErroRevisao(ErroSeguro):
    pass


def estrato(tribunal: str, orgao: str | None) -> str:
    nome = chave(orgao or "")
    if "criminal" in nome or "penal" in nome:
        return "criminal"
    familia = {chave(o) for o in ORGAOS_FAMILIA.get(tribunal, ())}
    if nome in familia and "familia" in PROPORCOES.get(tribunal, {}):
        return "familia"
    return "civel"


# --- Pasta privada -------------------------------------------------------------------------


def preparar_pasta(pasta: Path) -> Path:
    pasta.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        pasta.chmod(0o700)
    return pasta


def _gravar_jsonl(caminho: Path, registros: Iterable[Mapping[str, Any]]) -> None:
    temporario = caminho.with_suffix(".tmp")
    with temporario.open("w", encoding="utf-8") as arquivo:
        for registro in registros:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
    temporario.replace(caminho)
    if os.name != "nt":
        caminho.chmod(0o600)


def _ler_jsonl(caminho: Path) -> list[dict[str, Any]]:
    if not caminho.exists():
        return []
    with caminho.open(encoding="utf-8") as arquivo:
        return [json.loads(linha) for linha in arquivo if linha.strip()]


def _anexar(caminho: Path, registro: Mapping[str, Any]) -> None:
    with caminho.open("a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
        arquivo.flush()
        os.fsync(arquivo.fileno())
    if os.name != "nt":
        caminho.chmod(0o600)


def ler_amostra(pasta: Path) -> list[dict[str, Any]]:
    amostra = _ler_jsonl(pasta / AMOSTRA)
    if not amostra:
        raise ErroRevisao(f"nenhuma amostra em {pasta}: rode `buscajus revisao amostrar`")
    return amostra


def ler_respostas(pasta: Path) -> dict[str, dict[str, Any]]:
    """Última resposta de cada item da amostra corrente."""
    return {r["id_amostra"]: r for r in _ler_jsonl(pasta / RESPOSTAS)}


def _ler_historico(pasta: Path) -> list[dict[str, Any]]:
    caminho = pasta / HISTORICO
    if not caminho.exists():
        return []
    dados: list[dict[str, Any]] = json.loads(caminho.read_text(encoding="utf-8"))
    return dados


def _gravar_historico(pasta: Path, historico: Sequence[Mapping[str, Any]]) -> None:
    (pasta / HISTORICO).write_text(
        json.dumps(list(historico), ensure_ascii=False, indent=2), encoding="utf-8"
    )


# --- Amostragem ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidato:
    acordao_id: int
    tribunal: str
    estrato: str


def _cotas(n: int, fracao_tjdft: float, disponiveis: Counter[tuple[str, str]]) -> dict[str, int]:
    """Quantidade por tribunal; a falta de um tribunal passa para o outro."""
    tribunais = {t for t, _ in disponiveis}
    tjdft = round(n * fracao_tjdft) if "TJDFT" in tribunais else 0
    cotas = {"TJDFT": tjdft, "TJPR": n - tjdft}
    for tribunal, outro in (("TJDFT", "TJPR"), ("TJPR", "TJDFT")):
        total = sum(v for (t, _), v in disponiveis.items() if t == tribunal)
        if cotas[tribunal] > total:
            cotas[outro] += cotas[tribunal] - total
            cotas[tribunal] = total
    return cotas


def sortear(
    candidatos: Sequence[Candidato], n: int, fracao_tjdft: float, sorteio: random.Random
) -> list[Candidato]:
    """Amostra estratificada; estratos sem itens suficientes cedem a cota aos demais."""
    por_estrato: dict[tuple[str, str], list[Candidato]] = {}
    for c in candidatos:
        por_estrato.setdefault((c.tribunal, c.estrato), []).append(c)
    disponiveis = Counter({k: len(v) for k, v in por_estrato.items()})
    escolhidos: list[Candidato] = []
    for tribunal, cota in _cotas(n, fracao_tjdft, disponiveis).items():
        proporcoes = PROPORCOES.get(tribunal, {"civel": 1.0})
        restantes = cota
        grupos = sorted(proporcoes.items(), key=lambda kv: -kv[1])
        quotas = {e: round(cota * p) for e, p in grupos}
        quotas[grupos[0][0]] += cota - sum(quotas.values())
        sobra: list[Candidato] = []
        for nome, quota in quotas.items():
            itens = list(por_estrato.get((tribunal, nome), []))
            sorteio.shuffle(itens)
            escolhidos += itens[:quota]
            restantes -= min(quota, len(itens))
            sobra += itens[quota:]
        # Estratos de outros nomes (ex.: família no TJDFT não existe) entram na sobra.
        for (t, nome), itens in por_estrato.items():
            if t == tribunal and nome not in quotas:
                sobra += itens
        sorteio.shuffle(sobra)
        escolhidos += sobra[:restantes]
    sorteio.shuffle(escolhidos)
    return escolhidos


def _candidatos(engine: Engine, desde: date | None, excluir: set[int]) -> list[Candidato]:
    with engine.connect() as conexao:
        linhas = conexao.execute(
            text("""
                SELECT id, tribunal, orgao_julgador FROM acordao
                WHERE situacao = 'ativo'
                  AND (CAST(:desde AS date) IS NULL OR primeira_coleta_em >= CAST(:desde AS date))
            """),
            {"desde": desde},
        ).all()
    return [
        Candidato(int(c.id), str(c.tribunal), estrato(str(c.tribunal), c.orgao_julgador))
        for c in linhas
        if int(c.id) not in excluir
    ]


def _arquivar_rodada(pasta: Path) -> None:
    """A rodada anterior vai para ``rodadas/N`` (os trechos servem ao ``verificar``)."""
    if not (pasta / AMOSTRA).exists():
        return
    destino_base = pasta / RODADAS
    destino_base.mkdir(exist_ok=True, mode=0o700)
    numero = len([p for p in destino_base.iterdir() if p.is_dir()]) + 1
    destino = destino_base / f"{numero:02d}"
    destino.mkdir(mode=0o700)
    for nome in (AMOSTRA, RESPOSTAS):
        if (pasta / nome).exists():
            shutil.move(str(pasta / nome), str(destino / nome))


def _ids_ja_amostrados(pasta: Path) -> set[int]:
    ids = {int(r["acordao_id"]) for r in _ler_jsonl(pasta / AMOSTRA)}
    base = pasta / RODADAS
    if base.exists():
        for rodada in base.iterdir():
            ids |= {int(r["acordao_id"]) for r in _ler_jsonl(rodada / AMOSTRA)}
    return ids


def amostrar(
    engine: Engine,
    pasta: Path,
    *,
    n: int,
    fracao_tjdft: float = FRACAO_TJDFT,
    desde: date | None = None,
    nova_rodada: bool = False,
    semente: int | None = None,
) -> dict[str, Any]:
    """Grava a amostra na pasta privada; devolve só contagens."""
    preparar_pasta(pasta)
    respostas = ler_respostas(pasta)
    if (pasta / AMOSTRA).exists() and not nova_rodada:
        raise ErroRevisao(
            "já existe uma amostra na pasta; use --nova-rodada para arquivá-la e sortear outra"
        )
    rodada_corrente = len(_rodadas_arquivadas(pasta)) + 1
    registrada = any(h["rodada"] == rodada_corrente for h in _ler_historico(pasta))
    if respostas and not registrada:
        raise ErroRevisao("rode `buscajus revisao resultado` antes de abrir uma nova rodada")
    excluir = _ids_ja_amostrados(pasta)
    candidatos = _candidatos(engine, desde, excluir)
    sorteio = random.Random(semente if semente is not None else random.SystemRandom().random())  # noqa: S311
    escolhidos = sortear(candidatos, n, fracao_tjdft, sorteio)
    if nova_rodada:
        _arquivar_rodada(pasta)
    ids = [c.acordao_id for c in escolhidos]
    with engine.connect() as conexao:
        linhas = {
            int(linha.id): linha
            for linha in conexao.execute(
                text("""
                    SELECT id, fonte::text AS fonte, tribunal, ementa, anonimizacao_versao
                    FROM acordao WHERE id = ANY(:ids)
                """),
                {"ids": ids},
            )
        }
    registros = [
        {
            "id_amostra": f"r{i:03d}",
            "acordao_id": c.acordao_id,
            "tribunal": c.tribunal,
            "estrato": c.estrato,
            "anonimizacao_versao": linhas[c.acordao_id].anonimizacao_versao,
            "ementa": linhas[c.acordao_id].ementa,
        }
        for i, c in enumerate(escolhidos, start=1)
    ]
    _gravar_jsonl(pasta / AMOSTRA, registros)
    return {
        "amostra": len(registros),
        "pedida": n,
        "disponiveis": len(candidatos),
        "por_estrato": dict(Counter(f"{r['tribunal']}/{r['estrato']}" for r in registros)),
    }


# --- Revisão interativa --------------------------------------------------------------------


@dataclass
class Terminal:
    """Entrada e saída da revisão (substituíveis nos testes)."""

    ler: Callable[[str], str] = input
    escrever: Callable[[str], None] = print
    largura: int = field(default_factory=lambda: min(shutil.get_terminal_size().columns, 100))


def _normalizado(texto: str) -> str:
    return " ".join(alinhado(texto).split())


def trecho_no_texto(trecho: str, texto: str) -> bool:
    """O trecho aparece no texto (sem diferença de acento, caixa e espaços)?"""
    return bool(trecho.strip()) and _normalizado(trecho) in _normalizado(texto)


def revisar(engine: Engine, pasta: Path, terminal: Terminal | None = None) -> dict[str, int]:
    """Laço da revisão. Devolve só as contagens da sessão."""
    term = terminal or Terminal()
    amostra = ler_amostra(pasta)
    respostas = ler_respostas(pasta)
    pendentes = [r for r in amostra if r["id_amostra"] not in respostas]
    sessao: Counter[str] = Counter()
    for item in pendentes:
        feitas = len(respostas) + sessao["ok"] + sessao["vazou"]
        term.escrever("\n" + "=" * term.largura)
        term.escrever(f"[{feitas + 1}/{len(amostra)}] {item['tribunal']} · {item['estrato']}")
        term.escrever("-" * term.largura)
        for paragrafo in str(item["ementa"]).splitlines():
            term.escrever(textwrap.fill(paragrafo, term.largura) if paragrafo.strip() else "")
        term.escrever("-" * term.largura)
        while True:
            opcao = term.ler("ok, vazou ou sair? [o/v/s]: ").strip().lower()
            if opcao in ("o", "ok", "v", "vazou", "s", "sair"):
                break
        if opcao.startswith("s"):
            break
        registro: dict[str, Any] = {
            "id_amostra": item["id_amostra"],
            "acordao_id": item["acordao_id"],
            "em": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        if opcao.startswith("o"):
            registro["resultado"] = "ok"
        else:
            while True:
                trecho = term.ler("Digite o trecho que escapou (como aparece no texto): ")
                if trecho_no_texto(trecho, str(item["ementa"])):
                    break
                term.escrever("O trecho não foi encontrado nesta ementa; digite de novo.")
            registro |= {"resultado": "vazou", "trecho": trecho.strip()}
            with engine.begin() as conexao:
                marcar_vazamento(conexao, int(item["acordao_id"]))
            term.escrever("Acórdão posto em quarentena (fora da busca).")
        _anexar(pasta / RESPOSTAS, registro)
        sessao[registro["resultado"]] += 1
    restantes = len(amostra) - len(ler_respostas(pasta))
    return {"ok": sessao["ok"], "vazou": sessao["vazou"], "restantes": restantes}


# --- Resultado -------------------------------------------------------------------------------


def limite_superior(vazamentos: int, revisadas: int, confianca: float = CONFIANCA) -> float:
    """Limite superior unilateral (Clopper-Pearson) da taxa de vazamento.

    Com 0 em n, é ``1 - (1 - confianca)^(1/n)`` (~3/n, a "regra de três").
    """
    if revisadas == 0:
        return 1.0
    if vazamentos >= revisadas:
        return 1.0
    alfa = 1 - confianca

    def cauda(p: float) -> float:  # P(X ≤ vazamentos | p)
        return sum(
            math.comb(revisadas, k) * p**k * (1 - p) ** (revisadas - k)
            for k in range(vazamentos + 1)
        )

    baixo, alto = vazamentos / revisadas, 1.0
    for _ in range(100):
        meio = (baixo + alto) / 2
        if cauda(meio) > alfa:
            baixo = meio
        else:
            alto = meio
    return alto


def _situacao(revisadas: int, total: int, vazamentos: int, meta: int) -> str:
    if vazamentos:
        return "reprovada: corrigir as regras, reprocessar e sortear nova amostra"
    if revisadas < total:
        return "em andamento"
    if revisadas >= meta:
        return "aprovada: 0 vazamentos"
    return f"incompleta: menos de {meta} ementas revisadas"


def resultado(pasta: Path, relatorio: Path | None, *, meta: int = META_APROVACAO) -> dict[str, Any]:
    """Agregados da rodada corrente; atualiza o histórico e o relatório em ``docs/``."""
    amostra = ler_amostra(pasta)
    respostas = ler_respostas(pasta)
    estratos = {r["id_amostra"]: f"{r['tribunal']}/{r['estrato']}" for r in amostra}
    revisadas = len(respostas)
    vazamentos = sum(1 for r in respostas.values() if r["resultado"] == "vazou")
    por_estrato: dict[str, dict[str, int]] = {}
    for id_amostra, nome in estratos.items():
        linha = por_estrato.setdefault(nome, {"amostra": 0, "revisadas": 0, "vazamentos": 0})
        linha["amostra"] += 1
        if id_amostra in respostas:
            linha["revisadas"] += 1
            linha["vazamentos"] += respostas[id_amostra]["resultado"] == "vazou"
    resumo = {
        "rodada": len(_rodadas_arquivadas(pasta)) + 1,
        "data": datetime.now(UTC).date().isoformat(),
        "amostra": len(amostra),
        "revisadas": revisadas,
        "vazamentos": vazamentos,
        "taxa": round(vazamentos / revisadas, 4) if revisadas else None,
        "limite_superior_95": round(limite_superior(vazamentos, revisadas), 4),
        "situacao": _situacao(revisadas, len(amostra), vazamentos, meta),
        "por_estrato": dict(sorted(por_estrato.items())),
    }
    historico = [h for h in _ler_historico(pasta) if h["rodada"] != resumo["rodada"]]
    historico.append(resumo)
    _gravar_historico(pasta, sorted(historico, key=lambda h: int(h["rodada"])))
    if relatorio is not None:
        relatorio.write_text(relatorio_markdown(historico, meta), encoding="utf-8")
    return resumo


def _rodadas_arquivadas(pasta: Path) -> list[Path]:
    base = pasta / RODADAS
    return sorted(p for p in base.iterdir() if p.is_dir()) if base.exists() else []


def relatorio_markdown(historico: Sequence[Mapping[str, Any]], meta: int) -> str:
    def pct(valor: object) -> str:
        return "-" if valor is None else f"{float(str(valor)) * 100:.1f}%"

    linhas = [
        "# Revisão por amostra da anonimização (F1-42)",
        "",
        "Gerado por `buscajus revisao resultado`. **Só agregados**: nenhum trecho de ementa, "
        "nome ou identificador de acórdão. A amostra e as marcações ficam só na pasta privada "
        "(`ner-avaliacao-privado/`) e são apagadas conforme o F1-40.",
        "",
        f"Critério (ARCHITECTURE.md, seção 6.7): 0 vazamentos em {meta} ementas revisadas "
        "libera as cargas no servidor de produção; qualquer vazamento leva a corrigir as "
        "regras, reprocessar e revisar uma nova amostra. Depois do lançamento, amostra mensal "
        "de 30 ementas novas. O limite superior é unilateral, de 95% (Clopper-Pearson).",
        "",
        "| Rodada | Data | Amostra | Revisadas | Vazamentos | Taxa | Limite superior (95%) "
        "| Situação |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for h in historico:
        linhas.append(
            f"| {h['rodada']} | {h['data']} | {h['amostra']} | {h['revisadas']} | "
            f"{h['vazamentos']} | {pct(h['taxa'])} | {pct(h['limite_superior_95'])} | "
            f"{h['situacao']} |"
        )
    if historico:
        ultimo = historico[-1]
        linhas += [
            "",
            f"## Rodada {ultimo['rodada']} por estrato",
            "",
            "| Estrato | Amostra | Revisadas | Vazamentos |",
            "|---|---|---|---|",
        ]
        for nome, dados in dict(ultimo["por_estrato"]).items():
            linhas.append(
                f"| {nome} | {dados['amostra']} | {dados['revisadas']} | {dados['vazamentos']} |"
            )
    return "\n".join(linhas) + "\n"


# --- Verificação das regras corrigidas -----------------------------------------------------


def _vazamentos(pasta: Path) -> list[tuple[str, str]]:
    """(ementa, trecho) de todas as rodadas, inclusive a corrente."""
    pares: list[tuple[str, str]] = []
    for base in [*_rodadas_arquivadas(pasta), pasta]:
        ementas = {r["id_amostra"]: str(r["ementa"]) for r in _ler_jsonl(base / AMOSTRA)}
        for r in _ler_jsonl(base / RESPOSTAS):
            if r.get("resultado") == "vazou" and r["id_amostra"] in ementas:
                pares.append((ementas[r["id_amostra"]], str(r["trecho"])))
    return pares


def aplicar_regras(texto: str, detector: c2.DetectorPessoas) -> str:
    """Camada 2, CPF e documentos sobre um texto já anonimizado (sem destinatários)."""
    texto, _ = c2.aplicar(texto, detector)
    texto, _ = mascarar_cpf(texto)
    texto, _ = mascarar_documentos(texto)
    return texto


def ainda_presente(trecho: str, texto: str) -> bool:
    """Algum token do trecho (palavra ou número) continua no texto?"""
    alvo = alinhado(texto)
    return any(re.search(rf"(?<![A-Z0-9]){re.escape(t)}(?![A-Z0-9])", alvo) for t in tokens(trecho))


def verificar(pasta: Path, detector: c2.DetectorPessoas) -> dict[str, int]:
    """Quantos trechos marcados as regras atuais pegam por inteiro. Só contagens."""
    pares = _vazamentos(pasta)
    escapam = sum(ainda_presente(t, aplicar_regras(e, detector)) for e, t in pares)
    return {"trechos": len(pares), "pegos": len(pares) - escapam, "escapam": escapam}
