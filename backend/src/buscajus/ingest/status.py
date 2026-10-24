"""Relatório de coleta (``buscajus ingest status``): estado e contagens por unidade."""

from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import Connection, text

COLUNAS_CADERNOS = (
    ("tribunal", "TRIBUNAL"),
    ("data", "DATA"),
    ("status", "STATUS"),
    ("versao", "VERSÃO"),
    ("comunicacoes_lidas", "COMUNICAÇÕES"),
    ("acordaos_aceitos", "ACEITOS"),
    ("rejeitados", "REJ. ANONIM."),
    ("quarentena", "QUARENTENA"),
    ("cancelados", "CANCELADOS"),
    ("anomalias", "ANOMALIAS"),
    ("falhas_parser", "FALHAS PARSER"),
    ("respostas_429", "429"),
    ("tentativas", "TENTATIVAS"),
)

COLUNAS_JANELAS = (
    ("fonte", "FONTE"),
    ("tribunal", "TRIBUNAL"),
    ("data_inicio", "INÍCIO"),
    ("data_fim", "FIM"),
    ("status", "STATUS"),
    ("ultima_pagina", "ÚLT. PÁGINA"),
    ("itens_recebidos", "RECEBIDOS"),
    ("itens_aceitos", "ACEITOS"),
    ("itens_descartados", "DESCARTADOS"),
    ("descartados_segredo", "SEGREDO"),
    ("rejeitados", "REJ. ANONIM."),
    ("quarentena", "QUARENTENA"),
    ("cancelados", "CANCELADOS"),
    ("anomalias", "ANOMALIAS"),
    ("falhas_parser", "FALHAS PARSER"),
    ("respostas_429", "429"),
    ("tentativas", "TENTATIVAS"),
)

# Colunas somadas na linha de total.
_SOMAVEIS = {
    "comunicacoes_lidas",
    "acordaos_aceitos",
    "itens_recebidos",
    "itens_aceitos",
    "itens_descartados",
    "descartados_segredo",
    "rejeitados",
    "quarentena",
    "cancelados",
    "anomalias",
    "falhas_parser",
    "respostas_429",
}


def _filtros(
    coluna_data: str, tribunal: str | None, de: date | None, ate: date | None
) -> tuple[str, dict[str, Any]]:
    condicoes = ["TRUE"]
    parametros: dict[str, Any] = {}
    if tribunal:
        condicoes.append("tribunal = :tribunal")
        parametros["tribunal"] = tribunal.upper()
    if de:
        condicoes.append(f"{coluna_data} >= :de")
        parametros["de"] = de
    if ate:
        condicoes.append(f"{coluna_data} <= :ate")
        parametros["ate"] = ate
    return " AND ".join(condicoes), parametros


def listar_cadernos(
    conexao: Connection,
    *,
    tribunal: str | None = None,
    de: date | None = None,
    ate: date | None = None,
) -> list[dict[str, Any]]:
    onde, parametros = _filtros("data", tribunal, de, ate)
    linhas = conexao.execute(
        text(f"""
            SELECT tribunal, data, status, versao, comunicacoes_lidas, acordaos_aceitos,
                cardinality(rejeitados_anonimizacao) AS rejeitados, quarentena, cancelados,
                anomalias, falhas_parser, respostas_429, tentativas, ultimo_erro
            FROM caderno_djen WHERE {onde}
            ORDER BY tribunal, data DESC
        """),  # noqa: S608 (interpola só constantes do módulo)
        parametros,
    )
    return [dict(linha._mapping) for linha in linhas]


def listar_janelas(
    conexao: Connection,
    *,
    fonte: str | None = None,
    tribunal: str | None = None,
    de: date | None = None,
    ate: date | None = None,
) -> list[dict[str, Any]]:
    onde, parametros = _filtros("data_inicio", tribunal, de, ate)
    if fonte:
        onde += " AND fonte = CAST(:fonte AS fonte)"
        parametros["fonte"] = fonte
    linhas = conexao.execute(
        text(f"""
            SELECT fonte::text AS fonte, tribunal, data_inicio, data_fim, status, ultima_pagina,
                itens_recebidos, itens_aceitos, itens_descartados, descartados_segredo,
                cardinality(rejeitados_anonimizacao) AS rejeitados, quarentena, cancelados,
                anomalias, falhas_parser, respostas_429, tentativas, ultimo_erro
            FROM coleta_janela WHERE {onde}
            ORDER BY fonte, tribunal, data_inicio DESC
        """),  # noqa: S608 (interpola só constantes do módulo)
        parametros,
    )
    return [dict(linha._mapping) for linha in linhas]


def formatar_tabela(
    linhas: Sequence[dict[str, Any]], colunas: Sequence[tuple[str, str]], titulo: str
) -> str:
    if not linhas:
        return f"{titulo}: nenhuma unidade registrada.\n"
    total = {
        chave: sum(linha[chave] or 0 for linha in linhas)
        for chave, _ in colunas
        if chave in _SOMAVEIS
    }
    rotulo_total = {colunas[0][0]: f"TOTAL ({len(linhas)})"}
    corpo = [[_celula(linha[chave]) for chave, _ in colunas] for linha in linhas] + [
        [
            rotulo_total.get(chave, _celula(total[chave]) if chave in _SOMAVEIS else "")
            for chave, _ in colunas
        ]
    ]
    cabecalho = [rotulo for _, rotulo in colunas]
    larguras = [max(len(c) for c in coluna) for coluna in zip(cabecalho, *corpo, strict=True)]

    def linha_texto(celulas: Sequence[str]) -> str:
        return "  ".join(c.ljust(w) for c, w in zip(celulas, larguras, strict=True)).rstrip()

    saida = [titulo, linha_texto(cabecalho)]
    saida += [linha_texto(celulas) for celulas in corpo[:-1]]
    saida += ["-" * len(linha_texto(cabecalho)), linha_texto(corpo[-1])]
    erros = [linha for linha in linhas if linha.get("ultimo_erro")]
    if erros:
        saida.append("")
        saida.append("Erros:")
        saida += [
            f"  {' '.join(_celula(linha[c]) for c, _ in colunas[:2])}: {linha['ultimo_erro']}"
            for linha in erros
        ]
    return "\n".join(saida) + "\n"


def _celula(valor: Any) -> str:
    if valor is None:
        return "-"
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)
