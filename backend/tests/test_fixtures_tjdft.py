"""As fixtures sintéticas do TJDFT (F2-02) estão em dia e cobrem os casos previstos."""

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine

from buscajus.db.classes_cnj import ler_tpu, nomes_por_codigo
from fixtures.tjdft import PASTA, arquivos, carregar, dados

FUSO = ZoneInfo("America/Sao_Paulo")


def registros(dia: str) -> list[dict[str, Any]]:
    return [
        r
        for p in sorted(PASTA.glob(f"pesquisa-{dia}-p?.json"))
        for r in carregar(p.name)["registros"]
    ]


def todos() -> list[dict[str, Any]]:
    return [r for nome in arquivos() for r in carregar(nome)["registros"]]


def test_arquivos_versionados_batem_com_o_gerador() -> None:
    esperados = arquivos()
    presentes = {p.name for p in PASTA.iterdir() if p.suffix == ".json"}
    assert presentes == set(esperados)
    divergentes = [n for n, c in esperados.items() if (PASTA / n).read_bytes() != c]
    assert divergentes == [], "rode `uv run python -m fixtures.tjdft` em backend/tests"


def test_estrutura_da_resposta() -> None:
    for nome in arquivos():
        resposta = carregar(nome)
        assert set(resposta) == {"hits", "agregacoes", "paginacao", "registros"}
        assert set(resposta["hits"]) == {"value"}
        assert set(resposta["paginacao"]) == {"pagina", "tamanho"}
        assert resposta["paginacao"]["tamanho"] == 40


def test_paginas_cheia_parcial_e_vazia() -> None:
    p0, p1, p2 = (carregar(f"pesquisa-{dados.DIA}-p{p}.json") for p in range(3))
    assert [len(p["registros"]) for p in (p0, p1, p2)] == [40, 5, 0]
    assert {p["hits"]["value"] for p in (p0, p1, p2)} == {45}
    assert len({r["uuid"] for r in registros(dados.DIA)}) == 45
    vazio = carregar(f"pesquisa-{dados.DIA_VAZIO}-p0.json")
    assert vazio["hits"]["value"] == 0 and vazio["registros"] == []


def test_pagina_repetida_quebra_a_integridade() -> None:
    p0 = carregar(f"pesquisa-{dados.DIA_REPETIDO}-p0.json")["registros"]
    certa = carregar(f"pesquisa-{dados.DIA_REPETIDO}-p1.json")["registros"]
    repetida = carregar(f"pesquisa-{dados.DIA_REPETIDO}-p1-repetida.json")["registros"]
    assert len({r["uuid"] for r in p0 + certa}) == 41
    assert len({r["uuid"] for r in p0 + repetida}) == 40
    assert repetida[0]["uuid"] in {r["uuid"] for r in p0}


def test_turma_recursal_e_segredo() -> None:
    regs = registros(dados.DIA)
    recursais = [r for r in regs if r["turmaRecursal"]]
    assert recursais and all(r["subbase"] == "acordaos-tr" for r in recursais)
    assert all(r["base"] == "acordaos" for r in regs)
    segredo = [r for r in regs if r["segredoJustica"] is not False]
    assert len(segredo) == 1 and segredo[0]["segredoJustica"] is True
    assert segredo[0]["possuiInteiroTeor"] is False
    assert dados.MARCADOR_SEGREDO in segredo[0]["ementa"]


def test_registro_na_virada_do_dia_utc() -> None:
    for dia in (dados.DIA, dados.DIA_VIRADA):
        for r in registros(dia):
            utc = datetime.fromisoformat(r["dataPublicacao"].replace("Z", "+00:00"))
            # A API filtra pela data UTC (spike F2-02).
            assert utc.date().isoformat() == dia
    sp = [
        datetime.fromisoformat(r["dataPublicacao"].replace("Z", "+00:00")).astimezone(FUSO)
        for r in registros(dados.DIA_VIRADA)
    ]
    assert any(d.date().isoformat() == dados.DIA for d in sp)


def test_campos_opcionais_e_fora_da_lista_branca() -> None:
    regs = registros(dados.DIA)
    assert any("nomeRelatorDesignado" in r and "nomeRevisor" in r for r in regs)
    assert any("inteiroTeorHtml" in r and "jurisprudenciaEmFoco" in r for r in regs)
    assert {r["localDePublicacao"] for r in regs} == {"DJE", "PJe"}
    assert {type(r["versao"]) for r in regs} == {str}


def test_dados_sinteticos() -> None:
    processo = re.compile(r"^\d{7}-\d{2}\.2099\.8\.07\.9999$")
    for r in todos():
        assert processo.match(r["processo"])
        assert r["uuid"].startswith("0f1c7e00-2099-")
        assert r["uf"] == "DF"


def test_classes_das_fixtures_estao_na_tpu() -> None:
    tpu = {c["codigo"]: c["nome"] for c in ler_tpu().classes}
    assert {r["codigoClasseCnj"] for r in todos()} <= set(tpu)


@pytest.mark.banco
def test_classes_das_fixtures_resolvem_no_banco(banco: Engine) -> None:
    with banco.connect() as conexao:
        nomes = nomes_por_codigo(conexao)
    assert nomes[dados.APELACAO_CIVEL] == "Apelação Cível"
    assert nomes[dados.RECURSO_INOMINADO] == "Recurso Inominado Cível"
    assert all(nomes.get(r["codigoClasseCnj"]) for r in todos())
