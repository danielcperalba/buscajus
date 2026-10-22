import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from buscajus.api import app as modulo_app
from buscajus.db.engine import obter_engine


@pytest.fixture
def cliente() -> TestClient:
    app = modulo_app.criar_app()
    app.dependency_overrides[obter_engine] = lambda: create_engine("sqlite://")
    return TestClient(app)


def test_saude_ok_com_banco_disponivel(cliente: TestClient) -> None:
    resposta = cliente.get("/api/v1/saude")
    assert resposta.status_code == 200
    assert resposta.json()["banco"] == "ok"


def test_saude_503_sem_banco(cliente: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(modulo_app, "banco_disponivel", lambda _engine: False)
    resposta = cliente.get("/api/v1/saude")
    assert resposta.status_code == 503
    assert resposta.json() == {"status": "erro", "banco": "erro", "versao": modulo_app.__version__}
