"""Checagem pontual via /api/v1/comunicacao (F1-17)."""

import pytest
import respx

from buscajus.core.config import ConfigHttp
from buscajus.ingest.conector import ErroColeta
from buscajus.ingest.djen.campos import EstadoFonte, RegraEstado
from buscajus.ingest.djen.comunicacao import EstadoComunicacao, checar_comunicacao
from buscajus.ingest.http import ClienteHttp
from fixtures.djen import dados, numero_cnj

from .conftest import RelogioFalso
from .djen_ajuda import DIA, URL_API, ler_json

URL = f"{URL_API}/api/v1/comunicacao"


@pytest.fixture
def cliente(relogio: RelogioFalso) -> ClienteHttp:
    return ClienteHttp(ConfigHttp(), 1.0, relogio=relogio)


def _checar(cliente: ClienteHttp, id_comunicacao: int, sequencial: int) -> EstadoComunicacao:
    _, mascara = numero_cnj(sequencial)
    return checar_comunicacao(
        cliente,
        URL_API,
        tribunal="TJPR",
        numero_processo=mascara,
        data_disponibilizacao=DIA,
        id_comunicacao=str(id_comunicacao),
    )


def _ementa(id_comunicacao: int) -> dados.Ementa:
    return next(e for e in dados.EMENTAS if e.id == id_comunicacao)


@respx.mock
def test_marca_cancelada(cliente: ClienteHttp) -> None:
    rota = respx.get(URL).respond(200, json=ler_json("comunicacao-900020-cancelada.json"))
    estado = _checar(cliente, 900020, _ementa(900020).sequencial)
    assert estado.encontrada
    assert estado.ativo is False
    assert estado.estado(RegraEstado()) is EstadoFonte.CANCELADA
    params = rota.calls.last.request.url.params
    assert params["siglaTribunal"] == "TJPR"
    assert params["numeroProcesso"] == numero_cnj(_ementa(900020).sequencial)[0]
    assert params["dataDisponibilizacaoInicio"] == params["dataDisponibilizacaoFim"] == "2026-10-15"
    # numeroComunicacao não é único no DJEN (F1-01): não é usado.
    assert "numeroComunicacao" not in params


@respx.mock
def test_ativa_nao_e_cancelada(cliente: ClienteHttp) -> None:
    respx.get(URL).respond(200, json=ler_json("comunicacao-900001-ativa.json"))
    estado = _checar(cliente, 900001, _ementa(900001).sequencial)
    assert estado == EstadoComunicacao(encontrada=True, ativo=True, status="P")
    assert estado.estado(RegraEstado()) is EstadoFonte.ATIVA


@respx.mock
def test_le_so_os_campos_de_estado(cliente: ClienteHttp) -> None:
    respx.get(URL).respond(200, json=ler_json("comunicacao-900001-ativa.json"))
    estado = _checar(cliente, 900001, _ementa(900001).sequencial)
    # Nada do texto nem dos destinatários sai da checagem.
    assert set(vars(estado)) == {"encontrada", "ativo", "status", "data_cancelamento"}


@respx.mock
@pytest.mark.parametrize(
    "resposta", ["comunicacao-nao-encontrada.json", "comunicacao-900001-ativa.json"]
)
def test_nao_encontrada_conta_como_cancelada(cliente: ClienteHttp, resposta: str) -> None:
    respx.get(URL).respond(200, json=ler_json(resposta))
    # Pede um id que não está na resposta.
    estado = _checar(cliente, 999999, 1)
    assert estado == EstadoComunicacao(encontrada=False)
    assert estado.estado(RegraEstado()) is EstadoFonte.CANCELADA


def test_status_desconhecido_e_anomalia() -> None:
    estado = EstadoComunicacao(encontrada=True, ativo=True, status="X")
    assert estado.estado(RegraEstado()) is EstadoFonte.ANOMALA


@respx.mock
def test_404_conta_como_nao_encontrada(cliente: ClienteHttp) -> None:
    respx.get(URL).respond(404)
    assert _checar(cliente, 900001, 1001) == EstadoComunicacao(encontrada=False)


@respx.mock
def test_erro_http(cliente: ClienteHttp) -> None:
    respx.get(URL).respond(400)
    with pytest.raises(ErroColeta, match="HTTP 400"):
        _checar(cliente, 900001, 1001)
