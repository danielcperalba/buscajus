"""Controle de versão dos cadernos (F1-16, ARCHITECTURE.md, seção 3.2).

Para cada caderno processado nos últimos N dias, consulta só os metadados (~750 bytes). Se
``versao`` ou ``hash`` mudaram, reprocessa o dia inteiro. Acórdãos do dia que não estão na
nova versão são conferidos um a um via ``/api/v1/comunicacao`` (F1-17); cancelados ou não
encontrados ficam ``cancelado``.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import Engine, text

from buscajus.ingest.bruto import ArmazenamentoBruto, caminho_caderno
from buscajus.ingest.conector import UnidadeColeta
from buscajus.ingest.djen import caderno
from buscajus.ingest.djen.campos import EstadoFonte, RegraEstado
from buscajus.ingest.djen.comunicacao import checar_comunicacao
from buscajus.ingest.http import ClienteHttp
from buscajus.ingest.runner import Orquestrador, Resultado
from buscajus.ingest.upsert import MOTIVO_ANOMALIA, marcar_situacao

log = logging.getLogger(__name__)


@dataclass
class VerificacaoCaderno:
    data: date
    versao_anterior: int | None
    versao_atual: int | None
    reprocessado: bool = False
    ausentes: int = 0
    cancelados: int = 0
    anomalias: int = 0
    erro: str | None = None


def verificar_versoes(
    engine: Engine,
    orquestrador: Orquestrador,
    cliente: ClienteHttp,
    bruto: ArmazenamentoBruto,
    *,
    url_api: str,
    regra: RegraEstado,
    tribunal: str,
    hoje: date,
    dias: int = 30,
) -> list[VerificacaoCaderno]:
    with engine.connect() as conexao:
        cadernos = conexao.execute(
            text("""
                SELECT id, data, versao, hash FROM caderno_djen
                WHERE tribunal = :tribunal AND status = 'processado' AND data >= :desde
                ORDER BY data DESC
            """),
            {"tribunal": tribunal, "desde": hoje - timedelta(days=dias)},
        ).all()

    resultados = []
    for linha in cadernos:
        resultado = VerificacaoCaderno(linha.data, linha.versao, None)
        resultados.append(resultado)
        meta = caderno.obter_metadados(cliente, url_api, tribunal, linha.data)
        with engine.begin() as conexao:
            conexao.execute(
                text("UPDATE caderno_djen SET verificado_em = now() WHERE id = :id"),
                {"id": linha.id},
            )
        if meta is None or meta.status != caderno.STATUS_PRONTO:
            log.warning(
                "caderno já processado sem metadados prontos",
                extra={"tribunal": tribunal, "data": linha.data.isoformat()},
            )
            continue
        resultado.versao_atual = meta.versao
        if (meta.versao, meta.hash) == (linha.versao, linha.hash):
            continue

        log.info(
            "nova versão do caderno, reprocessando",
            extra={"tribunal": tribunal, "data": linha.data.isoformat(), "versao": meta.versao},
        )
        unidade = UnidadeColeta("djen", tribunal, linha.data, linha.data, paginada=False)
        resumo = orquestrador.executar_unidade(unidade, forcar=True)
        if resumo.resultado is not Resultado.CONCLUIDA:
            resultado.erro = resumo.erro or str(resumo.resultado)
            continue
        resultado.reprocessado = True
        _conferir_ausentes(
            engine,
            cliente,
            bruto,
            url_api,
            regra,
            tribunal,
            linha.id,
            linha.data,
            resultado,
        )
    return resultados


def _conferir_ausentes(
    engine: Engine,
    cliente: ClienteHttp,
    bruto: ArmazenamentoBruto,
    url_api: str,
    regra: RegraEstado,
    tribunal: str,
    id_caderno: int,
    data: date,
    resultado: VerificacaoCaderno,
) -> None:
    with engine.connect() as conexao:
        estado = conexao.execute(
            text("SELECT versao, rejeitados_anonimizacao FROM caderno_djen WHERE id = :id"),
            {"id": id_caderno},
        ).one()
    # Presentes na nova versão: os gravados no bruto e os recusados pela anonimização.
    presentes = {
        str(item["id"]) for item in bruto.ler(caminho_caderno(tribunal, data, estado.versao))
    }
    presentes |= set(estado.rejeitados_anonimizacao)

    with engine.connect() as conexao:
        ausentes = conexao.execute(
            text("""
                SELECT id, id_fonte, numero_processo FROM acordao
                WHERE fonte = 'djen' AND tribunal = :tribunal AND data_disponibilizacao = :data
                  AND situacao NOT IN ('cancelado', 'removido', 'duplicado')
                  AND NOT (id_fonte = ANY(CAST(:presentes AS text[])))
            """),
            {"tribunal": tribunal, "data": data, "presentes": sorted(presentes)},
        ).all()

    resultado.ausentes = len(ausentes)
    for acordao in ausentes:
        situacao = checar_comunicacao(
            cliente,
            url_api,
            tribunal=tribunal,
            numero_processo=acordao.numero_processo,
            data_disponibilizacao=data,
            id_comunicacao=acordao.id_fonte,
        )
        match situacao.estado(regra):
            case EstadoFonte.CANCELADA:
                with engine.begin() as conexao:
                    marcar_situacao(
                        conexao,
                        acordao.id,
                        "cancelado",
                        f"ausente na versão {estado.versao} do caderno",
                    )
                resultado.cancelados += 1
            case EstadoFonte.ANOMALA:
                # Falha fechada: sai do índice, sem ser tratado como cancelamento.
                with engine.begin() as conexao:
                    marcar_situacao(conexao, acordao.id, "quarentena", MOTIVO_ANOMALIA)
                resultado.anomalias += 1
            case EstadoFonte.ATIVA:
                pass
