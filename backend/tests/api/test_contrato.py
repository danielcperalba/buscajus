"""Contrato da API (F4-01): OpenAPI versionado, 501 sem busca e respostas do mock."""

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from buscajus.api import app as modulo_app
from buscajus.api.mock import EXEMPLOS

OPENAPI = Path(__file__).parents[3] / "frontend" / "openapi.json"


@pytest.fixture
def mock(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("BUSCAJUS_API__MOCK", "true")
    return TestClient(modulo_app.criar_app())


@pytest.fixture
def sem_busca() -> TestClient:
    return TestClient(modulo_app.criar_app())


def test_openapi_versionado_esta_em_dia() -> None:
    atual = modulo_app.openapi_json(modulo_app.criar_app())
    assert OPENAPI.read_text(encoding="utf-8") == atual, (
        "rode `uv run buscajus api openapi > ../frontend/openapi.json` em backend/"
    )


def test_cli_imprime_so_o_openapi() -> None:
    saida = subprocess.run(
        [sys.executable, "-m", "buscajus.cli", "api", "openapi"],
        capture_output=True,
        check=True,
    )
    # Bytes: UTF-8 e LF também no Windows (o arquivo é gerado por redirecionamento).
    assert saida.stdout == OPENAPI.read_bytes()


@pytest.mark.parametrize(
    ("metodo", "rota"),
    [
        ("get", "/api/v1/busca?q=heranca"),
        ("get", "/api/v1/acordaos/1"),
        ("get", "/api/v1/processos/0011412-20.2099"),
        ("get", "/api/v1/filtros"),
        ("get", "/api/v1/relatores?prefixo=ful"),
    ],
)
def test_sem_busca_responde_501(sem_busca: TestClient, metodo: str, rota: str) -> None:
    resposta = getattr(sem_busca, metodo)(rota)
    assert resposta.status_code == 501
    assert resposta.json() == {
        "erro": "nao_implementado",
        "mensagem": "a busca ainda não está disponível",
    }


def test_busca_hibrida_com_destaque(mock: TestClient) -> None:
    corpo = mock.get("/api/v1/busca", params={"q": "disputa por herança familiar"}).json()
    assert (corpo["tipo"], corpo["numero_processo"], corpo["pagina"]) == ("hibrida", None, 1)
    assert corpo["total"] == 1
    (resultado,) = corpo["resultados"]
    assert resultado["tribunal"] == "TJDFT"
    assert "<mark>HERANÇA</mark>" in resultado["trecho"]
    assert resultado["citacao"].endswith("publ. PJe 21/10/2026.")
    assert resultado["aviso"].startswith("Texto reproduzido da fonte oficial")
    assert {"ementa", "decisao"}.isdisjoint(resultado)


def test_busca_por_numero_e_prefixo(mock: TestClient) -> None:
    exemplo = EXEMPLOS[0].detalhe.numero_processo
    corpo = mock.get("/api/v1/busca", params={"q": f"processo {exemplo}"}).json()
    assert (corpo["tipo"], corpo["numero_processo"], corpo["total"]) == ("processo", exemplo, 1)
    prefixo = exemplo[:15]
    corpo = mock.get("/api/v1/busca", params={"q": prefixo}).json()
    assert corpo["tipo"] == "processo" and corpo["total"] == 1
    assert corpo["numero_processo"] == "".join(c for c in prefixo if c.isdigit())


def test_filtros_da_busca(mock: TestClient) -> None:
    corpo = mock.get("/api/v1/busca", params={"q": "a", "tribunal": "tjpr"}).json()
    assert {r["tribunal"] for r in corpo["resultados"]} == {"TJPR"}
    assert corpo["filtros"]["tribunal"] == "tjpr"
    corpo = mock.get("/api/v1/busca", params={"q": "penal", "data_inicio": "2026-10-05"}).json()
    assert corpo["total"] == 0  # julgado em 02/10


@pytest.mark.parametrize(
    "parametros",
    [{"q": ""}, {"q": "   "}, {"q": "x", "pagina": 0}, {"q": "x", "pagina": 11}, {}],
)
def test_busca_invalida_e_422(mock: TestClient, parametros: dict[str, object]) -> None:
    assert mock.get("/api/v1/busca", params=parametros).status_code == 422


def test_detalhe(mock: TestClient) -> None:
    corpo = mock.get("/api/v1/acordaos/3").json()
    assert corpo["relator_designado"] == "Beltrana de Tal"
    assert "Rel. p/ acórdão Beltrana de Tal" in corpo["citacao"]
    assert corpo["ementa"] and corpo["decisao"]
    removido = mock.get("/api/v1/acordaos/4")
    assert removido.status_code == 410
    assert removido.json()["erro"] == "removido"
    assert mock.get("/api/v1/acordaos/5").json()["erro"] == "cancelado"
    ausente = mock.get("/api/v1/acordaos/99")
    assert (ausente.status_code, ausente.json()["erro"]) == (404, "nao_encontrado")


def test_processo(mock: TestClient) -> None:
    numero = EXEMPLOS[1].detalhe.numero_processo
    for forma in (numero, "".join(c for c in numero if c.isdigit())):
        corpo = mock.get(f"/api/v1/processos/{forma}").json()
        assert corpo["numero_processo"] == numero
        assert [a["id"] for a in corpo["acordaos"]] == [2]
    assert mock.get("/api/v1/processos/9999999-99.2099").status_code == 404
    assert mock.get("/api/v1/processos/123").status_code == 422


def test_filtros_e_relatores(mock: TestClient) -> None:
    filtros = mock.get("/api/v1/filtros").json()
    assert [t["valor"] for t in filtros["tribunais"]] == ["TJDFT", "TJPR"]
    assert {"valor": "198", "rotulo": "Apelação Cível", "total": 1} in filtros["classes"]
    relatores = mock.get("/api/v1/relatores", params={"prefixo": "fula"}).json()
    assert relatores == [{"nome": "Fulano de Tal", "chave": "fulano de tal"}]
    assert mock.get("/api/v1/relatores", params={"prefixo": "f"}).status_code == 422


def test_remocao(mock: TestClient) -> None:
    pedido = {
        "referencia": EXEMPLOS[0].detalhe.numero_processo,
        "motivo": "Meu nome aparece no texto da ementa.",
        "email": "pessoa@exemplo.invalid",
    }
    resposta = mock.post("/api/v1/remocao", json=pedido)
    assert resposta.status_code == 201
    assert resposta.json()["status"] == "pendente"
    assert mock.post("/api/v1/remocao", json=pedido | {"email": "sem-arroba"}).status_code == 422
    assert mock.post("/api/v1/remocao", json=pedido | {"extra": 1}).status_code == 422
