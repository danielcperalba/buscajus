"""Filtros da busca (F4-07; ARCHITECTURE.md, seção 8.6), iguais nos dois ramos.

Tribunal, órgão julgador, classe (código da TPU), relator (``relator_chave``, também o do
relator designado), período sobre ``data_referencia`` e, quando a consulta traz um número de
processo, o número (exato ou prefixo). Só acórdãos ``ativo`` entram na busca.
"""

from typing import Any

from buscajus.api.consulta import NumeroNaConsulta
from buscajus.api.esquemas import FiltrosBusca
from buscajus.ingest.texto import chave


def condicoes(
    filtros: FiltrosBusca, numero: NumeroNaConsulta | None = None, *, alias: str = "a"
) -> tuple[str, dict[str, Any]]:
    """Trecho de ``WHERE`` e os parâmetros (prefixados com ``f_``)."""
    a = alias
    partes = [f"{a}.situacao = 'ativo'"]
    parametros: dict[str, Any] = {}
    if filtros.tribunal:
        partes.append(f"{a}.tribunal = :f_tribunal")
        parametros["f_tribunal"] = filtros.tribunal.strip().upper()
    if filtros.orgao:
        partes.append(f"{a}.orgao_julgador = :f_orgao")
        parametros["f_orgao"] = " ".join(filtros.orgao.split())
    if filtros.classe is not None:
        partes.append(f"{a}.classe_codigo_cnj = :f_classe")
        parametros["f_classe"] = filtros.classe
    if filtros.relator:
        partes.append(
            f"({a}.relator_chave = :f_relator OR {a}.relator_designado_chave = :f_relator)"
        )
        parametros["f_relator"] = chave(filtros.relator)
    if filtros.data_inicio:
        partes.append(f"{a}.data_referencia >= :f_inicio")
        parametros["f_inicio"] = filtros.data_inicio
    if filtros.data_fim:
        partes.append(f"{a}.data_referencia <= :f_fim")
        parametros["f_fim"] = filtros.data_fim
    if numero is not None and numero.completo:
        partes.append(f"{a}.numero_processo = :f_numero")
        parametros["f_numero"] = numero.digitos
    elif numero is not None:
        partes.append(f"{a}.numero_processo LIKE :f_prefixo")
        parametros["f_prefixo"] = numero.digitos + "%"
    return " AND ".join(partes), parametros
