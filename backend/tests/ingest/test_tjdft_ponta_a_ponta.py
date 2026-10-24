"""Coleta do TJDFT até o banco: F2-04 a F2-08, com as fixtures sintéticas."""

import gzip
import json
import logging
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import respx
from sqlalchemy import Engine, text

from buscajus.core.config import ConfigHttp
from buscajus.db.classes_cnj import nomes_por_codigo
from buscajus.ingest import status
from buscajus.ingest.bruto import ArmazenamentoBruto
from buscajus.ingest.http import ClienteHttp
from buscajus.ingest.runner import Orquestrador, Resultado
from buscajus.ingest.tjdft.campos import LISTA_BRANCA
from buscajus.ingest.tjdft.conector import ConectorTjdft
from buscajus.ingest.tjdft.normalizacao import VERSAO_NORMALIZACAO, NormalizadorTjdft
from buscajus.ingest.tjdft.processamento import MOTIVO_SEGREDO, ProcessadorTjdft
from fixtures.tjdft import dados

from .conftest import RelogioFalso
from .tjdft_ajuda import (
    DIA,
    DIA_REPETIDO,
    DIA_VIRADA,
    HOJE,
    AnonimizadorFalso,
    ServidorTjdft,
    alterar_registro,
    config_tjdft,
    fixture,
    uuid,
)

pytestmark = pytest.mark.banco


@pytest.fixture
def servidor() -> Iterator[ServidorTjdft]:
    with respx.mock(assert_all_called=False) as roteador:
        yield ServidorTjdft(roteador)


@pytest.fixture
def raw(tmp_path: Path) -> Path:
    return tmp_path / "raw"


@pytest.fixture
def orquestrador(banco: Engine, raw: Path, relogio: RelogioFalso) -> Iterator[Orquestrador]:
    with banco.connect() as conexao:
        classes = nomes_por_codigo(conexao)
    with ClienteHttp(ConfigHttp(), 1.0, relogio=relogio) as cliente:
        conector = ConectorTjdft(config_tjdft(), cliente, AnonimizadorFalso(), hoje=lambda: HOJE)
        yield Orquestrador(
            banco,
            conector,
            ArmazenamentoBruto(raw),
            processar=ProcessadorTjdft(NormalizadorTjdft(classes)),
            estatisticas_http=cliente.estatisticas,
            versao_parser=VERSAO_NORMALIZACAO,
        )


def _coletar(orquestrador: Orquestrador, dia: date, *, forcar: bool = False) -> Resultado:
    unidade = orquestrador._conector.planejar("TJDFT", dia, dia)[0]
    return orquestrador.executar_unidade(unidade, forcar=forcar).resultado


def _acordaos(banco: Engine) -> dict[str, Any]:
    with banco.connect() as conexao:
        linhas = conexao.execute(
            text("SELECT * FROM acordao WHERE fonte = 'tjdft' ORDER BY id_fonte")
        ).all()
    return {linha.id_fonte: linha for linha in linhas}


def _janela(banco: Engine, dia: date) -> Any:
    with banco.connect() as conexao:
        return conexao.execute(
            text("SELECT * FROM coleta_janela WHERE fonte = 'tjdft' AND data_inicio = :dia"),
            {"dia": dia},
        ).one()


def _banco_inteiro(banco: Engine) -> str:
    with banco.connect() as conexao:
        tabelas = conexao.scalars(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "AND tablename NOT IN ('alembic_version', 'classe_cnj')"
            )
        ).all()
        partes = [
            str(conexao.scalar(text(f"SELECT coalesce(json_agg(t)::text, '') FROM {t} t")))  # noqa: S608
            for t in tabelas
        ]
    return "\n".join(partes)


def _brutos(raw: Path) -> list[dict[str, Any]]:
    itens = []
    for arquivo in sorted(raw.rglob("*.jsonl.gz")):
        with gzip.open(arquivo, "rt", encoding="utf-8") as entrada:
            itens += [json.loads(linha) for linha in entrada]
    return itens


def test_dia_completo_ate_o_banco(
    banco: Engine,
    orquestrador: Orquestrador,
    servidor: ServidorTjdft,
    raw: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    assert _coletar(orquestrador, DIA) is Resultado.CONCLUIDA

    acordaos = _acordaos(banco)
    assert len(acordaos) == 44
    assert uuid(3) not in acordaos  # segredo de justiça

    recursal = acordaos[uuid(2)]
    assert recursal.turma_recursal is True
    assert recursal.classe_nome == "Recurso Inominado Cível"
    assert recursal.orgao_julgador == "PRIMEIRA TURMA RECURSAL"
    assert recursal.situacao == "ativo"

    designado = acordaos[uuid(5)]
    assert designado.relator == "Hermenegildo Soutelo Vilarongo"
    assert designado.relator_designado == "Leopoldina Arrudão Cambraieta"
    assert designado.local_publicacao == "DJE"
    assert str(designado.data_publicacao) == "2026-10-14"

    virada = acordaos[uuid(4)]
    assert (str(virada.data_publicacao), str(virada.data_julgamento)) == (
        "2026-10-13",
        "2026-10-07",
    )
    assert acordaos[uuid(7)].situacao == "quarentena"  # e-mail na ementa
    # O anonimizador falso não mascara CPF; a verificação de PII residual segura o registro.
    assert acordaos[uuid(5)].situacao == "quarentena"
    assert acordaos[uuid(1)].link_oficial == f"https://jurisdf.tjdft.jus.br/acordaos/{uuid(1)}"

    janela = _janela(banco, DIA)
    assert janela.status == "concluida"
    assert (janela.total_fonte, janela.ultima_pagina) == (45, 1)
    assert (janela.itens_recebidos, janela.itens_aceitos) == (45, 44)
    assert (janela.itens_descartados, janela.descartados_segredo) == (1, 1)
    assert janela.quarentena == 2
    assert janela.versao_parser == VERSAO_NORMALIZACAO

    brutos = _brutos(raw)
    assert len(brutos) == 44
    assert {campo for item in brutos for campo in item} <= LISTA_BRANCA
    assert sorted(p.name for p in raw.rglob("*.jsonl.gz")) == ["p00000.jsonl.gz", "p00001.jsonl.gz"]

    # Nada do registro em segredo nem dos campos fora da lista branca chega a lugar nenhum.
    gravado = _banco_inteiro(banco) + json.dumps(brutos, ensure_ascii=False) + caplog.text
    for marcador in dados.NUNCA:
        assert marcador not in gravado
    assert uuid(3) not in gravado


def test_reconsulta_e_virada_do_dia_nao_duplicam(
    banco: Engine, orquestrador: Orquestrador, servidor: ServidorTjdft
) -> None:
    assert _coletar(orquestrador, DIA) is Resultado.CONCLUIDA
    assert _coletar(orquestrador, DIA) is Resultado.PULADA
    assert _coletar(orquestrador, DIA, forcar=True) is Resultado.CONCLUIDA
    assert _coletar(orquestrador, DIA_VIRADA) is Resultado.CONCLUIDA
    acordaos = _acordaos(banco)
    assert len(acordaos) == 47
    assert {a.versao for a in acordaos.values()} == {1}
    # Veio na consulta de 15/10 (data UTC), mas foi publicado em 14/10 em São Paulo.
    assert str(acordaos[uuid(46)].data_publicacao) == "2026-10-14"
    assert _janela(banco, DIA).tentativas == 2


def test_segredo_superveniente_remove_e_recoleta_nao_desfaz(
    banco: Engine, orquestrador: Orquestrador, servidor: ServidorTjdft, raw: Path
) -> None:
    assert _coletar(orquestrador, DIA) is Resultado.CONCLUIDA
    assert _acordaos(banco)[uuid(1)].situacao == "ativo"

    sigiloso = alterar_registro(fixture(DIA, 0), 1, lambda r: r.update(segredoJustica=True))
    servidor.servir(DIA, 0, sigiloso)
    assert _coletar(orquestrador, DIA, forcar=True) is Resultado.CONCLUIDA
    removido = _acordaos(banco)[uuid(1)]
    assert (removido.situacao, removido.motivo_situacao) == ("removido", MOTIVO_SEGREDO)
    assert all(item["uuid"] != uuid(1) for item in _brutos(raw))
    assert _janela(banco, DIA).descartados_segredo == 2

    servidor.servir(DIA, 0, fixture(DIA, 0))
    assert _coletar(orquestrador, DIA, forcar=True) is Resultado.CONCLUIDA
    assert _acordaos(banco)[uuid(1)].situacao == "removido"


def test_paginacao_inconsistente_marca_erro_sem_gravar(
    banco: Engine, orquestrador: Orquestrador, servidor: ServidorTjdft, raw: Path
) -> None:
    servidor.servir(DIA_REPETIDO, 1, fixture(DIA_REPETIDO, 1, "-repetida"))
    assert _coletar(orquestrador, DIA_REPETIDO) is Resultado.ERRO
    janela = _janela(banco, DIA_REPETIDO)
    assert janela.status == "erro"
    assert "paginação inconsistente após 3 leituras" in janela.ultimo_erro
    assert janela.ultima_pagina is None
    assert _acordaos(banco) == {}
    assert not raw.exists() or not any(raw.rglob("*.jsonl.gz"))
    assert len(servidor.pedidos) == 6


def test_relatorio_mostra_os_descartados_por_segredo(
    banco: Engine, orquestrador: Orquestrador, servidor: ServidorTjdft
) -> None:
    _coletar(orquestrador, DIA)
    with banco.connect() as conexao:
        janelas = status.listar_janelas(conexao, fonte="tjdft")
    assert janelas[0]["descartados_segredo"] == 1
    tabela = status.formatar_tabela(janelas, status.COLUNAS_JANELAS, "Janelas")
    assert "SEGREDO" in tabela
