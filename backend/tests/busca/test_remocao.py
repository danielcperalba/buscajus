"""Pedidos de remoção (F4-12): API, decisão administrativa e apagamento (F2-13)."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from buscajus import cli
from buscajus.busca import pedidos
from buscajus.db.engine import obter_engine
from buscajus.ingest.bruto import ArmazenamentoBruto
from buscajus.ingest.upsert import Resultado, upsert

from .conftest import acordao, numero

pytestmark = pytest.mark.banco

PEDIDO = {"motivo": "Meu nome aparece no texto da ementa.", "email": "pessoa@exemplo.invalid"}


def _pedir(cliente: TestClient, referencia: str) -> Any:
    return cliente.post("/api/v1/remocao", json=PEDIDO | {"referencia": referencia})


def _pedido(banco: Engine, pedido_id: int) -> Any:
    with banco.connect() as conexao:
        return conexao.execute(
            text("SELECT * FROM pedido_remocao WHERE id = :id"), {"id": pedido_id}
        ).one()


def _acordao(banco: Engine, acordao_id: int) -> Any:
    with banco.connect() as conexao:
        return conexao.execute(
            text("SELECT situacao::text AS sit, ementa, decisao FROM acordao WHERE id = :id"),
            {"id": acordao_id},
        ).one()


@pytest.fixture
def bruto(tmp_path: Path) -> ArmazenamentoBruto:
    return ArmazenamentoBruto(tmp_path / "raw")


def test_pedido_por_numero_e_por_link(
    cliente: TestClient, banco: Engine, ids: dict[str, int]
) -> None:
    _, mascara = numero(10)
    resposta = _pedir(cliente, f"processo {mascara}")
    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["status"] == "pendente" and corpo["protocolo"] >= 1
    pedido = _pedido(banco, corpo["protocolo"])
    assert (pedido.acordao_id, pedido.numero_processo) == (None, numero(10)[0])
    assert pedido.contato == "pessoa@exemplo.invalid"

    link = f"https://buscajus.exemplo/acordao/{ids['companheira']}?origem=busca"
    pedido = _pedido(banco, _pedir(cliente, link).json()["protocolo"])
    assert (pedido.acordao_id, pedido.numero_processo) == (ids["companheira"], None)


@pytest.mark.parametrize("referencia", ["0011412-20.2099", "qualquer coisa", "/acordao/999999"])
def test_referencia_invalida(cliente: TestClient, ids: dict[str, int], referencia: str) -> None:
    resposta = _pedir(cliente, referencia)
    assert (resposta.status_code, resposta.json()["erro"]) == (422, "referencia_invalida")


def test_aceitar_por_acordao(
    cliente: TestClient, banco: Engine, ids: dict[str, int], bruto: ArmazenamentoBruto
) -> None:
    protocolo = _pedir(cliente, f"/acordao/{ids['companheira']}").json()["protocolo"]
    assert pedidos.listar(banco)[0].id == protocolo
    removidos = pedidos.aceitar(banco, bruto, protocolo, "nome de parte no texto")
    assert removidos == [ids["companheira"]]
    linha = _acordao(banco, ids["companheira"])
    assert (linha.sit, linha.ementa, linha.decisao) == ("removido", "", None)
    pedido = _pedido(banco, protocolo)
    assert (pedido.status, pedido.decisao) == ("aceito", "nome de parte no texto")
    assert pedido.resolvido_em is not None
    assert cliente.get(f"/api/v1/acordaos/{ids['companheira']}").status_code == 410
    with pytest.raises(pedidos.PedidoInvalido, match="já está aceito"):
        pedidos.aceitar(banco, bruto, protocolo, "de novo")


def test_aceitar_por_numero_bloqueia_o_processo(
    cliente: TestClient, banco: Engine, ids: dict[str, int], bruto: ArmazenamentoBruto
) -> None:
    protocolo = _pedir(cliente, numero(10)[1]).json()["protocolo"]
    removidos = pedidos.aceitar(banco, bruto, protocolo, "aceito")
    assert sorted(removidos) == sorted([ids["heranca"], ids["heranca_embargos"]])
    # Um acórdão do mesmo processo coletado depois não entra.
    with banco.begin() as conexao:
        novo = acordao("u-novo", "Agravo interno no mesmo processo.", sequencial=10)
        assert upsert(conexao, novo, coleta_bruta_id=None, cancelado=False) is Resultado.BLOQUEADO
    assert cliente.get(f"/api/v1/processos/{numero(10)[1]}").status_code == 404


def test_rejeitar_e_limpar_contatos(
    cliente: TestClient, banco: Engine, ids: dict[str, int]
) -> None:
    protocolo = _pedir(cliente, f"/acordao/{ids['plano']}").json()["protocolo"]
    pendente = _pedir(cliente, f"/acordao/{ids['heranca']}").json()["protocolo"]
    pedidos.rejeitar(banco, protocolo, "não há dado pessoal no texto")
    assert _acordao(banco, ids["plano"]).sit == "ativo"
    assert _pedido(banco, protocolo).status == "rejeitado"
    assert pedidos.limpar_contatos(banco, 1) == 0  # resolvido agora: ainda no prazo
    assert pedidos.limpar_contatos(banco, 0) == 1
    assert _pedido(banco, protocolo).contato is None
    assert _pedido(banco, pendente).contato is not None  # pendente: nunca apagado
    with pytest.raises(pedidos.PedidoInvalido, match="não existe"):
        pedidos.rejeitar(banco, 999999, "x")


@pytest.fixture
def ambiente(
    url_banco_teste: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    monkeypatch.setenv("BUSCAJUS_DATABASE_URL", url_banco_teste)
    monkeypatch.setenv("BUSCAJUS_DIRETORIO_RAW", str(tmp_path / "raw"))
    obter_engine.cache_clear()
    yield
    obter_engine.cache_clear()


@pytest.mark.usefixtures("ambiente")
def test_cli_remocao(
    cliente: TestClient, ids: dict[str, int], capsys: pytest.CaptureFixture[str]
) -> None:
    protocolo = _pedir(cliente, f"/acordao/{ids['plano']}").json()["protocolo"]
    assert cli.main(["remocao", "listar"]) == 0
    (pedido,) = json.loads(capsys.readouterr().out)
    assert (pedido["id"], pedido["status"]) == (protocolo, "pendente")
    assert cli.main(["remocao", "aceitar", str(protocolo), "--decisao", "ok"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "pedido": protocolo,
        "status": "aceito",
        "acordaos_removidos": [ids["plano"]],
    }
    assert cli.main(["remocao", "rejeitar", str(protocolo), "--decisao", "x"]) == 2
    assert "já está aceito" in capsys.readouterr().err
    assert cli.main(["remocao", "limpar-contatos", "--dias", "0"]) == 0
    assert json.loads(capsys.readouterr().out) == {"contatos_apagados": 1}
