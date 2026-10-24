import logging
from pathlib import Path

import httpx
import pytest
import respx

from buscajus.core.config import ConfigHttp
from buscajus.ingest.http import (
    BaldeDeFichas,
    ClienteHttp,
    ErroHttp,
    RespostaGrandeDemais,
    TentativasEsgotadas,
    user_agent,
)

from .conftest import RelogioFalso

URL = "https://fonte.exemplo/api/v1/recurso"
URL_TEMPORARIA = "https://s3.exemplo/caderno.zip?X-Amz-Signature=segredo"


@pytest.fixture
def cliente(config_http: ConfigHttp, relogio: RelogioFalso) -> ClienteHttp:
    return ClienteHttp(config_http, requisicoes_por_segundo=1.0, relogio=relogio)


# --- F1-06: taxa, User-Agent e cabeçalhos de limite ---------------------------------


def test_balde_sem_rajada_espaca_as_chamadas(relogio: RelogioFalso) -> None:
    balde = BaldeDeFichas(2.0, relogio)
    for _ in range(5):
        balde.adquirir()
    assert relogio.esperas == [0.5, 0.5, 0.5, 0.5]


def test_balde_nao_espera_se_o_intervalo_ja_passou(relogio: RelogioFalso) -> None:
    balde = BaldeDeFichas(1.0, relogio)
    balde.adquirir()
    relogio.tempo += 3
    balde.adquirir()
    assert relogio.esperas == []


@respx.mock
def test_chamadas_respeitam_a_taxa(cliente: ClienteHttp, relogio: RelogioFalso) -> None:
    respx.get(URL).respond(200, json={})
    for _ in range(3):
        cliente.requisitar("GET", URL, rotulo="teste")
    assert relogio.esperas == [1.0, 1.0]
    assert cliente.estatisticas.requisicoes == 3


@respx.mock
def test_envia_user_agent_identificavel(config_http: ConfigHttp, relogio: RelogioFalso) -> None:
    rota = respx.get(URL).respond(200)
    config = config_http.model_copy(update={"contato": "contato@exemplo.org"})
    ClienteHttp(config, 1.0, relogio=relogio).requisitar("GET", URL, rotulo="teste")
    enviado = rota.calls.last.request.headers["user-agent"]
    assert enviado == user_agent("contato@exemplo.org")
    assert enviado.startswith("BuscaJus/")
    assert "github.com/danielcperalba/buscajus" in enviado


@respx.mock
def test_pausa_quando_o_limite_restante_chega_a_zero(
    cliente: ClienteHttp, relogio: RelogioFalso
) -> None:
    respx.get(URL).mock(
        side_effect=[
            httpx.Response(200, headers={"x-ratelimit-limit": "20", "x-ratelimit-remaining": "1"}),
            httpx.Response(200, headers={"x-ratelimit-limit": "20", "x-ratelimit-remaining": "0"}),
            httpx.Response(200, headers={"x-ratelimit-limit": "20", "x-ratelimit-remaining": "19"}),
        ]
    )
    for _ in range(3):
        cliente.requisitar("GET", URL, rotulo="teste")
    # 1 s entre a 1ª e a 2ª (taxa); 60 s de pausa preventiva antes da 3ª.
    assert relogio.esperas == [1.0, 60.0]
    assert cliente.estatisticas.pausas_limite == 1


@respx.mock
def test_devolve_404_sem_tentar_de_novo(cliente: ClienteHttp) -> None:
    rota = respx.get(URL).respond(404)
    assert cliente.requisitar("GET", URL, rotulo="teste").status_code == 404
    assert rota.call_count == 1


# --- F1-07: 429, 5xx e timeouts -------------------------------------------------------


@respx.mock
def test_429_com_retry_after(cliente: ClienteHttp, relogio: RelogioFalso) -> None:
    respx.get(URL).mock(
        side_effect=[httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200)]
    )
    assert cliente.requisitar("GET", URL, rotulo="teste").status_code == 200
    assert relogio.esperas == [7.0]
    assert cliente.estatisticas.respostas_429 == 1


@respx.mock
def test_429_sem_retry_after_espera_60s(cliente: ClienteHttp, relogio: RelogioFalso) -> None:
    respx.get(URL).mock(side_effect=[httpx.Response(429), httpx.Response(200)])
    cliente.requisitar("GET", URL, rotulo="teste")
    assert relogio.esperas == [60.0]


@respx.mock
def test_retry_after_exagerado_e_limitado(cliente: ClienteHttp, relogio: RelogioFalso) -> None:
    respx.get(URL).mock(
        side_effect=[httpx.Response(429, headers={"Retry-After": "86400"}), httpx.Response(200)]
    )
    cliente.requisitar("GET", URL, rotulo="teste")
    assert relogio.esperas == [600.0]


@respx.mock
def test_retry_after_como_data_http(cliente: ClienteHttp, relogio: RelogioFalso) -> None:
    respx.get(URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}),
            httpx.Response(200),
        ]
    )
    cliente.requisitar("GET", URL, rotulo="teste")
    # Data no passado: tenta de novo sem esperar (além do 1 s da taxa).
    assert relogio.esperas == [1.0]


@respx.mock
def test_503_usa_backoff_curto(cliente: ClienteHttp, relogio: RelogioFalso) -> None:
    respx.get(URL).mock(side_effect=[httpx.Response(503), httpx.Response(503), httpx.Response(200)])
    assert cliente.requisitar("GET", URL, rotulo="teste").status_code == 200
    assert relogio.esperas == [5.0, 15.0]


@respx.mock
def test_timeout_usa_backoff_curto(cliente: ClienteHttp, relogio: RelogioFalso) -> None:
    respx.get(URL).mock(
        side_effect=[httpx.ReadTimeout("lento"), httpx.ConnectError("caiu"), httpx.Response(200)]
    )
    assert cliente.requisitar("GET", URL, rotulo="teste").status_code == 200
    assert relogio.esperas == [5.0, 15.0]


@respx.mock
def test_backoff_repete_o_ultimo_valor(cliente: ClienteHttp, relogio: RelogioFalso) -> None:
    respx.get(URL).mock(side_effect=[httpx.Response(500)] * 4 + [httpx.Response(200)])
    cliente.requisitar("GET", URL, rotulo="teste")
    assert relogio.esperas == [5.0, 15.0, 45.0, 45.0]


@respx.mock
def test_backoff_recomeca_a_cada_requisicao(cliente: ClienteHttp, relogio: RelogioFalso) -> None:
    respx.get(URL).mock(
        side_effect=[httpx.Response(500), httpx.Response(200)] * 2,
    )
    cliente.requisitar("GET", URL, rotulo="teste")
    cliente.requisitar("GET", URL, rotulo="teste")
    # 5 s de backoff em cada requisição; 1 s de taxa entre elas.
    assert relogio.esperas == [5.0, 1.0, 5.0]


@respx.mock
def test_esgota_tentativas(cliente: ClienteHttp, relogio: RelogioFalso) -> None:
    rota = respx.get(URL).respond(503)
    with pytest.raises(TentativasEsgotadas, match="HTTP 503 após 5 tentativas"):
        cliente.requisitar("GET", URL, rotulo="metadados")
    assert rota.call_count == 5
    assert relogio.esperas == [5.0, 15.0, 45.0, 45.0]


@respx.mock
def test_429_conta_no_maximo_de_tentativas(cliente: ClienteHttp) -> None:
    rota = respx.get(URL).respond(429)
    with pytest.raises(TentativasEsgotadas, match="HTTP 429"):
        cliente.requisitar("GET", URL, rotulo="teste")
    assert rota.call_count == 5
    assert cliente.estatisticas.respostas_429 == 5


# --- Download em streaming ------------------------------------------------------------


@respx.mock
def test_baixa_em_streaming(cliente: ClienteHttp, tmp_path: Path) -> None:
    respx.get(URL_TEMPORARIA).respond(200, content=b"x" * 5000)
    destino = tmp_path / "caderno.zip"
    assert cliente.baixar(URL_TEMPORARIA, destino, rotulo="download", limite_bytes=10_000) == 5000
    assert destino.read_bytes() == b"x" * 5000


@respx.mock
def test_download_acima_do_limite_apaga_o_parcial(cliente: ClienteHttp, tmp_path: Path) -> None:
    respx.get(URL_TEMPORARIA).respond(200, content=b"x" * 5000)
    destino = tmp_path / "caderno.zip"
    with pytest.raises(RespostaGrandeDemais):
        cliente.baixar(URL_TEMPORARIA, destino, rotulo="download", limite_bytes=100)
    assert not destino.exists()


@respx.mock
def test_download_tenta_de_novo_apos_503(
    cliente: ClienteHttp, relogio: RelogioFalso, tmp_path: Path
) -> None:
    respx.get(URL_TEMPORARIA).mock(
        side_effect=[httpx.Response(503), httpx.Response(200, content=b"zip")]
    )
    destino = tmp_path / "caderno.zip"
    assert cliente.baixar(URL_TEMPORARIA, destino, rotulo="download", limite_bytes=100) == 3
    assert relogio.esperas == [5.0]


@respx.mock
def test_download_com_erro_definitivo_apaga_o_parcial(cliente: ClienteHttp, tmp_path: Path) -> None:
    respx.get(URL_TEMPORARIA).respond(403)
    destino = tmp_path / "caderno.zip"
    with pytest.raises(ErroHttp, match="download: HTTP 403"):
        cliente.baixar(URL_TEMPORARIA, destino, rotulo="download", limite_bytes=100)
    assert not destino.exists()


@respx.mock
def test_erros_e_logs_nao_trazem_a_url(
    cliente: ClienteHttp, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    respx.get(URL_TEMPORARIA).respond(503)
    caplog.set_level(logging.DEBUG)
    with pytest.raises(TentativasEsgotadas) as erro:
        cliente.baixar(URL_TEMPORARIA, tmp_path / "c.zip", rotulo="download", limite_bytes=10)
    textos = [str(erro.value)] + [
        f"{registro.getMessage()} {vars(registro)}" for registro in caplog.records
    ]
    assert not any("s3.exemplo" in t or "segredo" in t for t in textos)
