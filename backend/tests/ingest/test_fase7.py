"""Fase 7: tribunais do DJEN por configuração (F7-01), perfis de parser (F7-02), registro de
fontes (F7-04), prioridade na dedup (F7-05) e senha padrão fora do desenvolvimento (F7-09)."""

import dataclasses
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import respx
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, text

from buscajus.core.config import Config, ConfigHttp
from buscajus.ingest.agendador import TAREFA_DJEN_DIARIO, Agendador
from buscajus.ingest.conector import Checkpoint
from buscajus.ingest.djen import fabrica
from buscajus.ingest.djen.conector import ConectorDjen
from buscajus.ingest.djen.parser import PERFIL_TJPR, PerfilParser, analisar, perfil_para
from buscajus.ingest.fontes import FONTES
from buscajus.ingest.http import ClienteHttp
from buscajus.ingest.modelos import AcordaoNormalizado
from buscajus.ingest.upsert import ordem_das_fontes, upsert
from fixtures.djen import PASTA, dados

from .conftest import RelogioFalso
from .djen_ajuda import DIA, HOJE, URL_API, AnonimizadorFalso, ler_json, url_metadados

FUSO = ZoneInfo("America/Sao_Paulo")


def _config_dois_tribunais(**extra: Any) -> Config:
    return Config(
        djen={
            "url_api": URL_API,
            "tribunais": ["TJPR", "tjxx"],
            "inicio_ementas": {"TJPR": "2025-07-23", "TJXX": "2026-10-01"},
            "ajustes": {
                "tjxx": {
                    "tipos_documento_aceitos": ["Ementa de Acórdão", "Acórdão"],
                    "requisicoes_por_segundo": 0.5,
                    "horario": "10:00",
                }
            },
        },
        **extra,
    )


# --- F7-01 ----------------------------------------------------------------------------


def test_segundo_tribunal_so_por_configuracao(relogio: RelogioFalso, tmp_path: Path) -> None:
    config = _config_dois_tribunais()
    assert config.djen.tribunais == ["TJPR", "TJXX"]
    assert config.djen.tipos_aceitos("TJXX") == ["Ementa de Acórdão", "Acórdão"]
    assert config.djen.tipos_aceitos("TJPR") == ["Ementa de Acórdão"]
    assert (config.djen.taxa("TJXX"), config.djen.taxa("TJPR"), config.djen.taxa(None)) == (
        0.5,
        1.0,
        1.0,
    )

    cliente = ClienteHttp(ConfigHttp(), 1000, relogio=relogio)
    conector = ConectorDjen(config.djen, cliente, AnonimizadorFalso(), tmp_path, hoje=lambda: HOJE)
    unidades = conector.planejar("tjxx", date(2026, 9, 20), date(2026, 10, 3))
    assert [u.data_inicio for u in unidades][-1] == date(2026, 10, 1)  # início das ementas
    assert {u.tribunal for u in unidades} == {"TJXX"}

    # O mesmo caderno sintético servido para os dois: o TJXX aceita também "Acórdão".
    meta = ler_json(f"metadados-{dados.DATA}-v1.json")
    zip_bytes = (PASTA / f"caderno-{dados.DATA}-v1.zip").read_bytes()
    aceitos = {}
    with respx.mock(assert_all_called=False) as roteador:
        for tribunal in ("TJPR", "TJXX"):
            roteador.get(url_metadados(DIA, tribunal)).respond(200, json=meta)
        roteador.get(meta["url"]).respond(200, content=zip_bytes)
        for tribunal in ("TJPR", "TJXX"):
            (unidade,) = conector.planejar(tribunal, DIA, DIA)
            (lote,) = conector.coletar(unidade, Checkpoint())
            aceitos[tribunal] = lote.contadores.aceitos
    assert aceitos == {"TJPR": 20, "TJXX": 21}


def test_taxa_do_tribunal_na_coleta() -> None:
    coleta = fabrica.criar_coleta(
        _config_dois_tribunais(),
        create_engine("sqlite://"),
        anonimizador=AnonimizadorFalso(),
        tribunal="TJXX",
    )
    try:
        assert coleta.cliente._balde._taxa == 0.5
    finally:
        coleta.fechar()


def test_ajuste_de_tribunal_desconhecido_e_recusado() -> None:
    with pytest.raises(ValidationError, match=r"fora de djen.tribunais"):
        Config(djen={"ajustes": {"TJZZ": {"horario": "10:00"}}})


@pytest.mark.banco
def test_horario_por_tribunal_no_agendador(banco: Engine) -> None:
    config = _config_dois_tribunais(agendador={"ativo": True, "horario_djen": time(9, 0)})
    vistos: list[dict[str, Any]] = []
    quando = [datetime(2026, 10, 20, 9, 30, tzinfo=FUSO)]
    agendador = Agendador(
        banco, config, {TAREFA_DJEN_DIARIO: vistos.append}, agora=lambda: quando[0]
    )
    agendador.ciclo()
    quando[0] = datetime(2026, 10, 20, 10, 30, tzinfo=FUSO)
    agendador.ciclo()
    assert [v["tribunal"] for v in vistos] == ["TJPR", "TJXX"]


# --- F7-02 ----------------------------------------------------------------------------

HTML = (
    "<table><tr><td>Processo:</td><td>0011412-20.2099.8.16.9999(Apelação)</td></tr>"
    "<tr><td>Magistrado:</td><td>Fulano de Tal</td></tr></table>"
    "<p>EMENTA: DIREITO CIVIL. PARTILHA DE BENS. Recurso conhecido e desprovido.</p>"
)


def test_perfil_padrao_e_perfil_proprio() -> None:
    assert perfil_para("tjpr") is PERFIL_TJPR
    assert perfil_para("TJXX") is PERFIL_TJPR  # sem perfil próprio: o padrão
    assert perfil_para(None) is PERFIL_TJPR
    # No perfil TJPR, "Magistrado" não é rótulo de relator.
    assert analisar(HTML).relator is None
    outro = PerfilParser(
        "tjxx", {**PERFIL_TJPR.rotulos, "magistrado": "relator"}, minimo_caracteres=10
    )
    analisado = analisar(HTML, outro)
    assert analisado.relator == "Fulano de Tal"
    assert analisado.classe == "Apelação"


# --- F7-04 ----------------------------------------------------------------------------


@pytest.mark.banco
def test_registro_de_fontes_bate_com_o_tipo_do_banco(banco: Engine) -> None:
    with banco.connect() as conexao:
        valores = conexao.scalar(text("SELECT enum_range(NULL::fonte)::text[]"))
    assert set(valores) == set(FONTES)
    assert all(f.nome and f.url.startswith("https://") for f in FONTES.values())


# --- F7-05 ----------------------------------------------------------------------------

BASE = AcordaoNormalizado(
    fonte="djen",
    id_fonte="900001",
    tribunal="TJDFT",
    numero_processo="00010011020998079999",
    numero_processo_mascara="0001001-10.2099.8.07.9999",
    numero_processo_valido=True,
    ementa="DIREITO CIVIL. PARTILHA DE BENS. Recurso desprovido.",
    link_oficial="https://exemplo.invalid/1",
    data_julgamento=date(2026, 10, 8),
)


def test_ordem_das_fontes() -> None:
    assert ordem_das_fontes("TJDFT") == ("tjdft", "djen")
    assert ordem_das_fontes("tjdft", {"TJDFT": ["djen"]}) == ("djen", "tjdft")
    assert ordem_das_fontes("TJPR", {"TJDFT": ["djen"]}) == ("tjdft", "djen")


@pytest.mark.banco
def test_prioridade_configurada_inverte_a_dedup(banco: Engine) -> None:
    prioridades = {"TJDFT": ["djen", "tjdft"]}
    tjdft = dataclasses.replace(BASE, fonte="tjdft", id_fonte="u1")
    with banco.begin() as conexao:
        upsert(conexao, tjdft, coleta_bruta_id=None, cancelado=False, prioridades=prioridades)
        upsert(conexao, BASE, coleta_bruta_id=None, cancelado=False, prioridades=prioridades)
        situacoes = dict(
            conexao.execute(text("SELECT fonte::text, situacao::text FROM acordao")).all()
        )
    assert situacoes == {"djen": "ativo", "tjdft": "duplicado"}


def test_prioridade_na_configuracao() -> None:
    assert Config(prioridade_fontes={"TJDFT": ["djen", "tjdft"]}).prioridade_fontes == {
        "TJDFT": ["djen", "tjdft"]
    }
    with pytest.raises(ValidationError):
        Config(prioridade_fontes={"TJDFT": ["stj"]})


# --- F7-09 ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://buscajus:buscajus@db:5432/buscajus",
        "postgresql+psycopg://buscajus@db:5432/buscajus",
    ],
)
def test_producao_recusa_senha_padrao_ou_ausente(url: str) -> None:
    with pytest.raises(ValidationError, match="senha padrão"):
        Config(ambiente="producao", database_url=url)


def test_senha_propria_em_producao_e_padrao_em_desenvolvimento() -> None:
    propria = "postgresql+psycopg://buscajus:Outra-Senha-Forte@db:5432/buscajus"
    assert Config(ambiente="producao", database_url=propria).ambiente == "producao"
    assert Config().ambiente == "desenvolvimento"  # padrão: senha de desenvolvimento aceita
    assert Config(ambiente="teste").database_url.endswith("/buscajus")


def test_ambiente_pela_variavel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUSCAJUS_AMBIENTE", "producao")
    with pytest.raises(ValidationError, match="senha padrão"):
        Config()
