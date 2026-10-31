"""Ramo full-text (F4-04; ARCHITECTURE.md, seção 8.4).

A consulta vira uma ``tsquery`` com **OR** entre as palavras (AND seria restritivo demais para
consultas descritivas), respeitando:

- frases entre aspas: ``"partilha de bens"`` vira busca de frase (``phraseto_tsquery``);
- exclusão: ``-testamento`` tira os acórdãos com o termo (``&& !!``).

Ranking ``ts_rank_cd(busca_tsv, q, 32)``, top ``limite`` (100), com os filtros da busca.
O trecho destacado vem de ``ts_headline``, com ``<mark>`` em volta dos termos e o resto do
texto escapado (o único HTML do trecho é ``<mark>``).
"""

import html
import re
from typing import Any

from sqlalchemy import Connection, text

from buscajus.api.consulta import NumeroNaConsulta
from buscajus.api.esquemas import FiltrosBusca
from buscajus.busca.filtros import condicoes

# OR entre os lexemas já normalizados; 'simple' não refaz o radical, e quote_literal protege
# caracteres especiais.
_OR_LEXEMAS = """to_tsquery('simple', array_to_string(ARRAY(
    SELECT quote_literal(lexema) FROM unnest(tsvector_to_array(
        to_tsvector('pt_unaccent', {parametro}))) AS lexema
), ' | '))"""
_FRASE = re.compile(r'"([^"]+)"')
_EXCLUSAO = re.compile(r"(?:^|\s)-(\w[\w-]*)")
# Delimitadores do ts_headline: caracteres de uso privado, trocados por <mark> depois do escape.
_INICIO, _FIM = "", ""
_OPCOES_DESTAQUE = (
    f"StartSel={_INICIO}, StopSel={_FIM}, MaxFragments=2, MaxWords=35, MinWords=15, "
    'FragmentDelimiter=" … "'
)


def expressao_tsquery(consulta: str) -> tuple[str, dict[str, Any]] | None:
    """SQL da tsquery e parâmetros (prefixados com ``q_``); ``None`` se não há o que buscar."""
    frases = _FRASE.findall(consulta)
    resto = _FRASE.sub(" ", consulta)
    exclusoes = _EXCLUSAO.findall(resto)
    palavras = _EXCLUSAO.sub(" ", resto).replace('"', " ").strip()
    partes, parametros = [], {}
    if palavras:
        partes.append(_OR_LEXEMAS.format(parametro=":q_palavras"))
        parametros["q_palavras"] = palavras
    for i, frase in enumerate(frases):
        partes.append(f"phraseto_tsquery('pt_unaccent', :q_frase{i})")
        parametros[f"q_frase{i}"] = frase
    if not partes:
        return None
    expressao = "(" + " || ".join(partes) + ")"
    for i, termo in enumerate(exclusoes):
        expressao += f" && !! plainto_tsquery('pt_unaccent', :q_exclusao{i})"
        parametros[f"q_exclusao{i}"] = termo
    return expressao, parametros


def ramo_texto(
    conexao: Connection,
    consulta: str,
    filtros: FiltrosBusca,
    numero: NumeroNaConsulta | None = None,
    *,
    limite: int = 100,
) -> list[tuple[int, float]]:
    """(id, pontuação) dos melhores acórdãos ativos, do mais relevante ao menos."""
    tsquery = expressao_tsquery(consulta)
    if tsquery is None:
        return []
    expressao, parametros = tsquery
    onde, parametros_filtro = condicoes(filtros, numero)
    linhas = conexao.execute(
        text(f"""
            WITH q AS (SELECT {expressao} AS q)
            SELECT a.id, ts_rank_cd(a.busca_tsv, q.q, 32) AS pontuacao
            FROM acordao a, q
            WHERE {onde} AND a.busca_tsv @@ q.q
            ORDER BY pontuacao DESC, a.id
            LIMIT :limite
        """),  # noqa: S608 (interpola só SQL montado aqui, com parâmetros)
        parametros | parametros_filtro | {"limite": limite},
    ).all()
    return [(linha.id, float(linha.pontuacao)) for linha in linhas]


def destaques(conexao: Connection, consulta: str, ids: list[int]) -> dict[int, str]:
    """Trecho da ementa com ``<mark>`` nos termos da consulta, por id."""
    tsquery = expressao_tsquery(consulta)
    if tsquery is None or not ids:
        return {}
    expressao, parametros = tsquery
    linhas = conexao.execute(
        text(f"""
            WITH q AS (SELECT {expressao} AS q)
            SELECT a.id, ts_headline('pt_unaccent', a.ementa, q.q, :opcoes) AS trecho
            FROM acordao a, q WHERE a.id = ANY(:ids)
        """),  # noqa: S608
        parametros | {"ids": ids, "opcoes": _OPCOES_DESTAQUE},
    ).all()
    return {linha.id: marcar(linha.trecho) for linha in linhas if _INICIO in linha.trecho}


def marcar(trecho: str) -> str:
    """Escapa o texto e troca os delimitadores do ts_headline por ``<mark>``."""
    escapado = html.escape(trecho)
    return escapado.replace(_INICIO, "<mark>").replace(_FIM, "</mark>")


def inicio_da_ementa(ementa: str, tamanho: int = 300) -> str:
    """Trecho para resultados sem termo destacado: o começo da ementa, escapado."""
    resumo = " ".join(ementa.split())
    if len(resumo) > tamanho:
        resumo = resumo[:tamanho].rsplit(" ", 1)[0] + " …"
    return html.escape(resumo)
