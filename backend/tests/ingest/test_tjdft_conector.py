"""Conector TJDFT sem banco: requisição, paginação e integridade (F2-04), dias (F2-05) e
filtro de segredo, base e lista branca (F2-06)."""

import json
from collections.abc import Iterator
from datetime import date
from typing import Any

import httpx
import pytest
import respx
from pydantic import ValidationError

from buscajus.core.config import ConfigHttp, ConfigTjdft
from buscajus.ingest.conector import Checkpoint, ErroColeta, UnidadeColeta, UnidadeSemDados
from buscajus.ingest.http import ClienteHttp
from buscajus.ingest.tjdft.campos import LISTA_BRANCA, Descarte, descarte
from buscajus.ingest.tjdft.conector import ConectorTjdft
from fixtures.tjdft import dados

from .conftest import RelogioFalso
from .tjdft_ajuda import (
    DIA,
    DIA_REPETIDO,
    DIA_VAZIO,
    HOJE,
    AnonimizadorFalso,
    ServidorTjdft,
    alterar_registro,
    config_tjdft,
    fixture,
    uuid,
)


@pytest.fixture
def cliente(relogio: RelogioFalso) -> Iterator[ClienteHttp]:
    with ClienteHttp(ConfigHttp(), 1.0, relogio=relogio) as cliente:
        yield cliente


@pytest.fixture
def anonimizador() -> AnonimizadorFalso:
    return AnonimizadorFalso()


@pytest.fixture
def conector(cliente: ClienteHttp, anonimizador: AnonimizadorFalso) -> ConectorTjdft:
    return ConectorTjdft(config_tjdft(), cliente, anonimizador, hoje=lambda: HOJE)


@pytest.fixture
def servidor() -> Iterator[ServidorTjdft]:
    with respx.mock(assert_all_called=False) as roteador:
        yield ServidorTjdft(roteador)


def _unidade(dia: date = DIA) -> UnidadeColeta:
    return UnidadeColeta("tjdft", "TJDFT", dia, dia, paginada=True)


# --- F2-04: requisição e paginação ------------------------------------------------


def test_corpo_da_requisicao(conector: ConectorTjdft, servidor: ServidorTjdft) -> None:
    list(conector.coletar(_unidade(), Checkpoint()))
    assert servidor.corpos[0] == {
        "query": "",
        "pagina": 0,
        "tamanho": 40,
        "termosAcessorios": [
            {"campo": "base", "valor": "acordaos"},
            {"campo": "dataPublicacao", "valor": dados.DIA},
        ],
    }


def test_percorre_todas_as_paginas(
    conector: ConectorTjdft, servidor: ServidorTjdft, anonimizador: AnonimizadorFalso
) -> None:
    lotes = list(conector.coletar(_unidade(), Checkpoint()))
    assert servidor.pedidos == [(dados.DIA, 0), (dados.DIA, 1)]
    assert [lote.pagina for lote in lotes] == [0, 1]
    assert [lote.contadores.recebidos for lote in lotes] == [40, 5]
    assert sum(lote.contadores.aceitos for lote in lotes) == 44
    assert {lote.total_fonte for lote in lotes} == {45}
    assert [lote.caminho_bruto for lote in lotes] == [
        f"tjdft/TJDFT/{dados.DIA}/p00000.jsonl.gz",
        f"tjdft/TJDFT/{dados.DIA}/p00001.jsonl.gz",
    ]
    assert len(anonimizador.vistos) == 44


def test_retomada_rele_o_dia_e_devolve_so_as_paginas_seguintes(
    conector: ConectorTjdft, servidor: ServidorTjdft
) -> None:
    lotes = list(conector.coletar(_unidade(), Checkpoint(ultima_pagina=0)))
    # Relê o dia inteiro para conferir a integridade, mas só devolve a página 1.
    assert servidor.pedidos == [(dados.DIA, 0), (dados.DIA, 1)]
    assert [lote.pagina for lote in lotes] == [1]


def test_pagina_repetida_refaz_o_dia(conector: ConectorTjdft, servidor: ServidorTjdft) -> None:
    servidor.servir(
        DIA_REPETIDO,
        1,
        fixture(DIA_REPETIDO, 1, "-repetida"),
        fixture(DIA_REPETIDO, 1),
    )
    lotes = list(conector.coletar(_unidade(DIA_REPETIDO), Checkpoint()))
    dia = dados.DIA_REPETIDO
    assert servidor.pedidos == [(dia, 0), (dia, 1), (dia, 0), (dia, 1)]
    assert sum(lote.contadores.recebidos for lote in lotes) == 41


def test_pagina_sempre_repetida_vira_erro_depois_de_3_leituras(
    conector: ConectorTjdft, servidor: ServidorTjdft, anonimizador: AnonimizadorFalso
) -> None:
    servidor.servir(DIA_REPETIDO, 1, fixture(DIA_REPETIDO, 1, "-repetida"))
    lotes = conector.coletar(_unidade(DIA_REPETIDO), Checkpoint())
    with pytest.raises(ErroColeta, match=r"40 uuids únicos em 41 registros; hits\.value = 41"):
        next(lotes)
    assert len(servidor.pedidos) == 6


def test_tentativas_de_integridade_configuraveis(
    cliente: ClienteHttp, anonimizador: AnonimizadorFalso, servidor: ServidorTjdft
) -> None:
    servidor.servir(DIA_REPETIDO, 1, fixture(DIA_REPETIDO, 1, "-repetida"))
    conector = ConectorTjdft(config_tjdft(tentativas_integridade=1), cliente, anonimizador)
    with pytest.raises(ErroColeta):
        list(conector.coletar(_unidade(DIA_REPETIDO), Checkpoint()))
    assert len(servidor.pedidos) == 2


def test_hits_value_que_muda_entre_paginas_e_divergencia(
    conector: ConectorTjdft, servidor: ServidorTjdft
) -> None:
    p1 = fixture(DIA, 1)
    p1["hits"]["value"] = 46
    servidor.servir(DIA, 1, p1)
    with pytest.raises(ErroColeta, match=r"hits\.value mudou"):
        list(conector.coletar(_unidade(), Checkpoint()))


def test_pagina_vazia_antes_do_fim_e_divergencia(
    conector: ConectorTjdft, servidor: ServidorTjdft
) -> None:
    servidor.servir(DIA, 1, fixture(DIA, 2))  # página vazia no lugar da última
    with pytest.raises(ErroColeta, match="página 1 vazia"):
        list(conector.coletar(_unidade(), Checkpoint()))


def test_dia_sem_registros(conector: ConectorTjdft, servidor: ServidorTjdft) -> None:
    with pytest.raises(UnidadeSemDados):
        list(conector.coletar(_unidade(DIA_VAZIO), Checkpoint()))
    assert servidor.pedidos == [(dados.DIA_VAZIO, 0)]


@pytest.mark.parametrize(
    "resposta",
    [
        httpx.Response(400, json={"erro": "tamanho"}),
        httpx.Response(200, text="<html>"),
        httpx.Response(200, json={"registros": []}),
        httpx.Response(200, json={"hits": {"value": "45"}, "registros": []}),
        httpx.Response(200, json={"hits": {"value": 1}, "registros": ["x"]}),
    ],
)
def test_resposta_inesperada_e_erro(
    conector: ConectorTjdft, servidor: ServidorTjdft, resposta: httpx.Response
) -> None:
    servidor.servir(DIA, 0, resposta)
    with pytest.raises(ErroColeta, match="pesquisa do TJDFT"):
        list(conector.coletar(_unidade(), Checkpoint()))


def test_429_espera_e_tenta_de_novo(
    conector: ConectorTjdft, servidor: ServidorTjdft, relogio: RelogioFalso
) -> None:
    servidor.servir(DIA, 0, httpx.Response(429, headers={"Retry-After": "7"}), fixture(DIA, 0))
    lotes = list(conector.coletar(_unidade(), Checkpoint()))
    assert len(lotes) == 2
    assert 7.0 in relogio.esperas


def test_tamanho_acima_de_40_e_rejeitado_na_configuracao() -> None:
    with pytest.raises(ValidationError):
        ConfigTjdft(tamanho_pagina=50)


# --- F2-05: unidades por dia ------------------------------------------------------


def test_planejar_um_dia_por_unidade_do_mais_recente(conector: ConectorTjdft) -> None:
    unidades = conector.planejar("tjdft", date(2026, 10, 16), date(2026, 10, 30))
    assert [u.data_inicio for u in unidades] == [date(2026, 10, d) for d in (20, 19, 18, 17, 16)]
    assert all(u.paginada and u.data_inicio == u.data_fim for u in unidades)
    assert {(u.fonte, u.tribunal) for u in unidades} == {("tjdft", "TJDFT")}


def test_planejar_outro_tribunal_e_erro(conector: ConectorTjdft) -> None:
    with pytest.raises(ValueError, match="TJDFT"):
        conector.planejar("TJPR", DIA, DIA)


# --- F2-06: segredo, base e lista branca --------------------------------------------


@pytest.mark.parametrize("valor", [True, None, 1, 0, "S", "N", "false", "true", [], {}], ids=repr)
def test_segredo_que_nao_e_exatamente_false_e_descartado(valor: Any) -> None:
    assert descarte({"base": "acordaos", "segredoJustica": valor}) is Descarte.SEGREDO


def test_segredo_ausente_e_descartado() -> None:
    assert descarte({"base": "acordaos"}) is Descarte.SEGREDO


def test_base_diferente_e_descartada() -> None:
    assert descarte({"base": "decisoes", "segredoJustica": False}) is Descarte.BASE
    assert descarte({"segredoJustica": False}) is Descarte.BASE
    assert descarte({"base": "acordaos", "segredoJustica": False}) is None


@pytest.mark.parametrize("valor", [True, None, 1, "S", "ausente"], ids=repr)
def test_registro_em_segredo_nao_chega_ao_anonimizador_nem_ao_lote(
    conector: ConectorTjdft,
    servidor: ServidorTjdft,
    anonimizador: AnonimizadorFalso,
    valor: Any,
) -> None:
    def mudar(registro: dict[str, Any]) -> None:
        if valor == "ausente":
            del registro["segredoJustica"]
        else:
            registro["segredoJustica"] = valor

    servidor.servir(DIA, 0, alterar_registro(fixture(DIA, 0), 1, mudar))
    lotes = list(conector.coletar(_unidade(), Checkpoint()))
    alvo = uuid(1)
    assert alvo not in anonimizador.vistos
    assert all(item["uuid"] != alvo for lote in lotes for item in lote.itens)
    assert lotes[0].contadores.segredo == 2  # o registro 3 já vem em segredo
    assert alvo in lotes[0].ids_segredo and uuid(3) in lotes[0].ids_segredo


def test_registro_de_outra_base_e_descartado_sem_contar_como_segredo(
    conector: ConectorTjdft, servidor: ServidorTjdft
) -> None:
    servidor.servir(
        DIA, 0, alterar_registro(fixture(DIA, 0), 1, lambda r: r.update(base="decisoes"))
    )
    lote = next(iter(conector.coletar(_unidade(), Checkpoint())))
    assert lote.contadores.descartados == 2
    assert lote.contadores.segredo == 1
    assert uuid(1) not in lote.ids_segredo


def test_turma_recursal_e_aceita(conector: ConectorTjdft, servidor: ServidorTjdft) -> None:
    lote = next(iter(conector.coletar(_unidade(), Checkpoint())))
    recursal = next(i for i in lote.itens if i["uuid"] == uuid(2))
    assert recursal["subbase"] == "acordaos-tr"
    assert recursal["turmaRecursal"] is True


def test_lote_so_tem_campos_da_lista_branca(
    conector: ConectorTjdft, servidor: ServidorTjdft
) -> None:
    lotes = list(conector.coletar(_unidade(), Checkpoint()))
    campos = {campo for lote in lotes for item in lote.itens for campo in item}
    assert campos <= LISTA_BRANCA
    for proibido in ("inteiroTeorHtml", "jurisprudenciaEmFoco", "marcadores", "sequencial"):
        assert proibido not in campos
    serializado = json.dumps([lote.itens for lote in lotes], ensure_ascii=False)
    for marcador in dados.NUNCA:
        assert marcador not in serializado


def test_rejeicao_do_anonimizador_e_contada_so_pelo_uuid(
    cliente: ClienteHttp, servidor: ServidorTjdft
) -> None:
    anonimizador = AnonimizadorFalso(rejeitar={uuid(5)})
    conector = ConectorTjdft(config_tjdft(), cliente, anonimizador)
    lote = next(iter(conector.coletar(_unidade(), Checkpoint())))
    assert lote.contadores.rejeitados_anonimizacao == [uuid(5)]
    assert all(item["uuid"] != uuid(5) for item in lote.itens)
