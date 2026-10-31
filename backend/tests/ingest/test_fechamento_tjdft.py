"""Fechamento do TJDFT com o banco: anonimização real (F2-12), CLI e agendamento (F2-10)."""

import gzip
import json
import re
from collections.abc import Iterator, Mapping
from datetime import date, datetime, time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import respx
from sqlalchemy import Engine, text

from buscajus import cli
from buscajus.core.config import Config
from buscajus.db.engine import obter_engine
from buscajus.ingest import agendador as modulo_agendador
from buscajus.ingest.agendador import (
    TAREFA_DJEN_DIARIO,
    TAREFA_TJDFT_CONFERENCIA,
    TAREFA_TJDFT_DIARIO,
    Agendador,
    coleta_tjdft_diaria,
    conferencia_tjdft_mensal,
)
from buscajus.ingest.anonimizacao.pipeline import ErroAnonimizacao
from buscajus.ingest.conector import UnidadeColeta
from buscajus.ingest.runner import Resultado
from buscajus.ingest.tjdft import fabrica
from buscajus.ingest.tjdft.anonimizacao import criar_anonimizador
from buscajus.ingest.tjdft.conector import ConectorTjdft
from fixtures.tjdft import dados

from .anonimizacao_ajuda import DetectorFalso
from .test_tjdft_anonimizacao import NOMES_DETECTADOS
from .tjdft_ajuda import DIA, HOJE, URL_API, ServidorTjdft, config_tjdft, uuid

pytestmark = pytest.mark.banco

FUSO = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        diretorio_raw=tmp_path / "raw",
        tjdft={"url_api": URL_API, "requisicoes_por_segundo": 1000},
    )


@pytest.fixture
def servidor() -> Iterator[ServidorTjdft]:
    with respx.mock(assert_all_called=False) as roteador:
        yield ServidorTjdft(roteador)


def _criar_com_falso(config: Config, engine: Engine) -> fabrica.ColetaTjdft:
    anonimizador = criar_anonimizador(DetectorFalso(NOMES_DETECTADOS))
    coleta = fabrica.criar_coleta(config, engine, anonimizador=anonimizador)
    coleta.conector._hoje = lambda: HOJE
    return coleta


# --- F2-12: anonimização real até o banco -------------------------------------------


def test_nomes_e_cpfs_nao_chegam_ao_banco_nem_ao_bruto(
    banco: Engine, config: Config, servidor: ServidorTjdft
) -> None:
    coleta = _criar_com_falso(config, banco)
    try:
        unidade = coleta.conector.planejar("TJDFT", DIA, DIA)[0]
        assert coleta.orquestrador.executar_unidade(unidade).resultado is Resultado.CONCLUIDA
    finally:
        coleta.fechar()

    with banco.connect() as conexao:
        linhas = conexao.execute(
            text(
                "SELECT id_fonte, ementa, decisao, situacao::text AS sit, anonimizacao_versao, "
                "anonimizacao_substituicoes FROM acordao"
            )
        ).all()
        gravado = str(conexao.scalar(text("SELECT json_agg(a)::text FROM acordao a")))
    brutos = ""
    for arquivo in sorted(config.diretorio_raw.rglob("*.jsonl.gz")):
        brutos += gzip.decompress(arquivo.read_bytes()).decode("utf-8")

    for texto in (gravado, brutos):
        for nome in dados.DEVEM_SUMIR:
            assert nome not in texto
            assert json.dumps(nome)[1:-1] not in texto
        for cpf in dados.CPFS:
            assert not re.search(rf"(?<!\d){re.escape(cpf)}(?!\d)", texto)
        for marcador in dados.NUNCA:
            assert marcador not in texto

    criminal = next(linha for linha in linhas if linha.id_fonte == uuid(5))
    assert criminal.sit == "ativo"  # o CPF foi mascarado: não cai na quarentena
    for preservado in dados.PRESERVADOS:
        assert preservado in criminal.ementa + criminal.decisao
    for numero in dados.NAO_CPFS:
        assert numero in criminal.ementa
    assert criminal.anonimizacao_versao == "cpf-1+ner-falso-1"
    assert criminal.anonimizacao_substituicoes == 4


@respx.mock
def test_fabrica_sem_ner_falha_antes_da_rede(banco: Engine, config: Config) -> None:
    with pytest.raises(ErroAnonimizacao, match="NER"):
        fabrica.criar_coleta(config, banco)
    assert not respx.mock.calls


def test_fabrica_com_conector_desativado(banco: Engine) -> None:
    with pytest.raises(fabrica.ConectorDesativado):
        fabrica.criar_coleta(Config(tjdft={"ativo": False}), banco)


# --- F2-10: CLI ---------------------------------------------------------------------


@pytest.fixture
def ambiente(
    url_banco_teste: str, config: Config, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    monkeypatch.setenv("BUSCAJUS_DATABASE_URL", url_banco_teste)
    monkeypatch.setenv("BUSCAJUS_DIRETORIO_RAW", str(config.diretorio_raw))
    monkeypatch.setenv("BUSCAJUS_TJDFT__URL_API", URL_API)
    monkeypatch.setenv("BUSCAJUS_TJDFT__REQUISICOES_POR_SEGUNDO", "1000")
    obter_engine.cache_clear()
    yield
    obter_engine.cache_clear()


@respx.mock
@pytest.mark.usefixtures("ambiente")
def test_cli_tjdft_falha_fechada_sem_ner(banco: Engine, capsys: pytest.CaptureFixture[str]) -> None:
    codigo = cli.main(["ingest", "tjdft", "--de", dados.DIA, "--ate", dados.DIA])
    assert codigo == 2
    assert "NER" in capsys.readouterr().err
    assert not respx.mock.calls
    with banco.connect() as conexao:
        assert conexao.scalar(text("SELECT count(*) FROM coleta_janela")) == 0


@pytest.mark.usefixtures("ambiente")
def test_cli_tjdft(
    banco: Engine,
    servidor: ServidorTjdft,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original = fabrica.criar_coleta

    def criar(config: Config, engine: Engine) -> fabrica.ColetaTjdft:
        coleta = original(
            config, engine, anonimizador=criar_anonimizador(DetectorFalso(NOMES_DETECTADOS))
        )
        coleta.conector._hoje = lambda: HOJE
        return coleta

    monkeypatch.setattr(fabrica, "criar_coleta", criar)
    codigo = cli.main(["ingest", "tjdft", "--de", dados.DIA, "--ate", dados.DIA])
    assert codigo == 0
    saida = capsys.readouterr()
    # stdout é só o resumo JSON; os logs vão para stderr.
    (resumo,) = json.loads(saida.out)
    assert '"unidade finalizada"' in saida.err
    assert resumo == {
        "unidade": f"tjdft/TJDFT/{dados.DIA}",
        "resultado": "concluida",
        "recebidos": 45,
        "aceitos": 44,
        "descartados_segredo": 1,
        "descartados_outros": 0,
        "rejeitados_anonimizacao": 0,
        "falhas_parser": 0,
        "quarentena": 1,
        "erro": None,
    }


# --- F2-10: agendamento -------------------------------------------------------------


class Relogio:
    def __init__(self, quando: datetime) -> None:
        self.quando = quando

    def __call__(self) -> datetime:
        return self.quando


def _config_agendador() -> Config:
    return Config(
        agendador={"ativo": True, "horario_djen": time(9, 0), "horario_tjdft": time(8, 0)}
    )


def _tipos(banco: Engine) -> list[tuple[str, str]]:
    with banco.connect() as conexao:
        return [
            (linha.tipo, linha.status)
            for linha in conexao.execute(text("SELECT tipo, status FROM tarefa ORDER BY id"))
        ]


def test_agendamento_do_tjdft_desligado_por_padrao() -> None:
    assert Config().agendador.ativo is False


def test_agenda_o_tjdft_uma_vez_por_dia(banco: Engine) -> None:
    execucoes: list[Mapping[str, Any]] = []
    relogio = Relogio(datetime(2026, 10, 20, 7, 59, tzinfo=FUSO))
    agendador = Agendador(
        banco,
        _config_agendador(),
        {TAREFA_TJDFT_DIARIO: execucoes.append, TAREFA_DJEN_DIARIO: lambda _p: None},
        agora=relogio,
    )
    assert agendador.ciclo() == 0
    relogio.quando = datetime(2026, 10, 20, 8, 30, tzinfo=FUSO)
    assert agendador.ciclo() == 1  # só o TJDFT: o DJEN é às 9h
    relogio.quando = datetime(2026, 10, 20, 9, 30, tzinfo=FUSO)
    assert agendador.ciclo() == 1  # agora o DJEN; o TJDFT não repete
    assert execucoes == [{"data": "2026-10-20"}]
    assert _tipos(banco) == [
        (TAREFA_TJDFT_DIARIO, "concluida"),
        (TAREFA_DJEN_DIARIO, "concluida"),
    ]


def test_sem_executor_ou_com_conector_desativado_nao_agenda(banco: Engine) -> None:
    relogio = Relogio(datetime(2026, 10, 20, 10, 0, tzinfo=FUSO))
    Agendador(banco, _config_agendador(), {}, agora=relogio).ciclo()
    config = _config_agendador().model_copy(
        update={"tjdft": Config().tjdft.model_copy(update={"ativo": False})}
    )
    Agendador(banco, config, {TAREFA_TJDFT_DIARIO: lambda _p: None}, agora=relogio).ciclo()
    assert _tipos(banco) == []


def test_tarefa_diaria_sem_ner_falha_fechada(banco: Engine) -> None:
    executar = coleta_tjdft_diaria(Config(), banco)
    with pytest.raises(ErroAnonimizacao):
        executar({"data": "2026-10-20"})
    with banco.connect() as conexao:
        assert conexao.scalar(text("SELECT count(*) FROM coleta_janela")) == 0


def test_tarefa_diaria_recoleta_os_ultimos_30_dias(
    banco: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    chamadas: list[tuple[list[UnidadeColeta], bool]] = []

    class Orquestrador:
        def executar(self, unidades: list[UnidadeColeta], *, forcar: bool = False) -> None:
            chamadas.append((unidades, forcar))

    hoje = date(2026, 10, 20)
    conector = ConectorTjdft(config_tjdft(), None, None, hoje=lambda: hoje)  # type: ignore[arg-type]
    falsa = SimpleNamespace(conector=conector, orquestrador=Orquestrador(), fechar=lambda: None)
    monkeypatch.setattr(modulo_agendador.fabrica_tjdft, "criar_coleta", lambda *_a: falsa)

    coleta_tjdft_diaria(Config(), banco)({"data": hoje.isoformat()})
    ((unidades, forcar),) = chamadas
    assert forcar is True
    assert [u.data_inicio for u in unidades[:2]] == [hoje, date(2026, 10, 19)]
    assert unidades[-1].data_inicio == date(2026, 9, 20)
    assert len(unidades) == 31


def test_conferencia_mensal_so_no_dia_configurado(banco: Engine) -> None:
    relogio = Relogio(datetime(2026, 11, 1, 8, 30, tzinfo=FUSO))
    nada = lambda _p: None  # noqa: E731
    agendador = Agendador(
        banco,
        _config_agendador(),
        {TAREFA_TJDFT_DIARIO: nada, TAREFA_TJDFT_CONFERENCIA: nada},
        agora=relogio,
    )
    assert agendador.ciclo() == 2
    relogio.quando = datetime(2026, 11, 2, 8, 30, tzinfo=FUSO)
    assert agendador.ciclo() == 1
    assert [t for t, _ in _tipos(banco)] == [
        TAREFA_TJDFT_DIARIO,
        TAREFA_TJDFT_CONFERENCIA,
        TAREFA_TJDFT_DIARIO,
    ]


def test_conferencia_mensal_sem_ner_falha_fechada(banco: Engine) -> None:
    with pytest.raises(ErroAnonimizacao):
        conferencia_tjdft_mensal(Config(), banco)({"data": "2026-11-01"})
