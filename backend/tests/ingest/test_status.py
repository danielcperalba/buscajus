from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Engine

from buscajus import cli
from buscajus.db.engine import obter_engine
from buscajus.ingest import status
from buscajus.ingest.bruto import ArmazenamentoBruto
from buscajus.ingest.runner import Orquestrador

from .test_runner import DIA, ConectorFalso

pytestmark = pytest.mark.banco


@pytest.fixture
def coletado(banco: Engine, tmp_path: Path) -> Engine:
    cadernos = ConectorFalso(paginada=False, falhar_em=(DIA, 0))
    Orquestrador(banco, cadernos, ArmazenamentoBruto(tmp_path)).executar(
        cadernos.planejar("TJPR", date(2026, 10, 13), DIA)
    )
    janelas = ConectorFalso(paginada=True)
    Orquestrador(banco, janelas, ArmazenamentoBruto(tmp_path)).executar(
        janelas.planejar("TJDFT", DIA, DIA)
    )
    return banco


def test_lista_cadernos_com_filtros(coletado: Engine) -> None:
    with coletado.connect() as conexao:
        todos = status.listar_cadernos(conexao)
        filtrados = status.listar_cadernos(conexao, tribunal="tjpr", de=DIA, ate=DIA)
    assert [c["data"] for c in todos] == [DIA, date(2026, 10, 14), date(2026, 10, 13)]
    assert [(c["status"], c["rejeitados"]) for c in todos] == [
        ("erro", 0),
        ("processado", 1),
        ("processado", 1),
    ]
    assert len(filtrados) == 1


def test_tabela_com_total_e_erros(coletado: Engine) -> None:
    with coletado.connect() as conexao:
        cadernos = status.listar_cadernos(conexao)
    tabela = status.formatar_tabela(cadernos, status.COLUNAS_CADERNOS, "Cadernos do DJEN")
    linhas = tabela.splitlines()
    assert linhas[0] == "Cadernos do DJEN"
    assert linhas[1].split()[:3] == ["TRIBUNAL", "DATA", "STATUS"]
    total = next(linha for linha in linhas if linha.startswith("TOTAL"))
    # comunicações lidas, aceitos e rejeitados somados nos dois cadernos processados
    assert total.split()[2:5] == ["20", "4", "2"]
    assert "Erros:" in linhas
    assert any(linha.startswith("  TJPR 2026-10-15: ValueError em") for linha in linhas)


def test_tabela_vazia() -> None:
    assert status.formatar_tabela([], status.COLUNAS_JANELAS, "Janelas") == (
        "Janelas: nenhuma unidade registrada.\n"
    )


def test_comando_ingest_status(
    coletado: Engine,
    url_banco_teste: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("BUSCAJUS_DATABASE_URL", url_banco_teste)
    obter_engine.cache_clear()
    try:
        assert cli.main(["ingest", "status", "--tribunal", "TJPR"]) == 0
    finally:
        obter_engine.cache_clear()
    saida = capsys.readouterr().out
    assert "Cadernos do DJEN" in saida
    assert "2026-10-14" in saida
    # O filtro por tribunal também vale para as janelas paginadas (TJDFT não aparece).
    assert "TJDFT" not in saida


def test_comando_rejeita_data_invalida(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["ingest", "status", "--de", "15/10/2026"])
    assert "AAAA-MM-DD" in capsys.readouterr().err
