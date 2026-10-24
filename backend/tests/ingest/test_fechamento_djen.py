"""Fluxo completo do DJEN com o banco: F1-16, F1-23 a F1-28."""

import json
from collections import Counter
from pathlib import Path

import pytest
import respx
from sqlalchemy import Engine, text

from buscajus import cli
from buscajus.core.config import Config
from buscajus.db.engine import obter_engine
from buscajus.ingest.anonimizacao.pipeline import criar_anonimizador
from buscajus.ingest.djen import fabrica
from buscajus.ingest.djen.parser import VERSAO_PARSER
from buscajus.ingest.djen.versoes import verificar_versoes
from buscajus.ingest.reprocessamento import reprocessar_cadernos
from buscajus.ingest.texto import chave
from fixtures.djen import PASTA, dados

from .anonimizacao_ajuda import DetectorFalso
from .djen_ajuda import DIA, HOJE, URL_API, ler_json, url_metadados

pytestmark = pytest.mark.banco


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        diretorio_raw=tmp_path / "raw",
        diretorio_tmp_cadernos=tmp_path / "tmp",
        djen={"url_api": URL_API, "requisicoes_por_segundo": 1000},
    )


@pytest.fixture
def coleta(banco: Engine, config: Config) -> fabrica.ColetaDjen:
    coleta = fabrica.criar_coleta(config, banco, anonimizador=criar_anonimizador(DetectorFalso()))
    coleta.conector._hoje = lambda: HOJE
    return coleta


def _servir(roteador: respx.MockRouter, *versoes: int) -> None:
    roteador.get(url_metadados(DIA)).mock(
        side_effect=[
            respx.MockResponse(200, json=ler_json(f"metadados-{dados.DATA}-v{v}.json"))
            for v in versoes
        ]
    )
    for v in sorted(set(versoes)):
        meta = ler_json(f"metadados-{dados.DATA}-v{v}.json")
        roteador.get(meta["url"]).respond(
            200, content=(PASTA / f"caderno-{dados.DATA}-v{v}.zip").read_bytes()
        )


def _situacoes(banco: Engine) -> dict[str, str]:
    with banco.connect() as conexao:
        return dict(conexao.execute(text("SELECT id_fonte, situacao::text FROM acordao")).all())


def _processar_v1(coleta: fabrica.ColetaDjen) -> None:
    (resumo,) = coleta.orquestrador.executar(coleta.conector.planejar("TJPR", DIA, DIA))
    assert resumo.erro is None


@respx.mock
def test_caderno_vira_acordaos(coleta: fabrica.ColetaDjen, banco: Engine) -> None:
    _servir(respx.mock, 1)
    _processar_v1(coleta)

    situacoes = _situacoes(banco)
    assert len(situacoes) == 20
    assert Counter(situacoes.values()) == {"ativo": 18, "quarentena": 1, "cancelado": 1}
    assert situacoes["900019"] == "quarentena"
    assert situacoes["900015"] == "cancelado"
    with banco.connect() as conexao:
        caderno = conexao.execute(text("SELECT * FROM caderno_djen")).one()
        assert (caderno.acordaos_aceitos, caderno.quarentena, caderno.cancelados) == (20, 1, 1)
        assert (caderno.falhas_parser, caderno.versao_parser) == (0, VERSAO_PARSER)
        tudo = " ".join(
            str(v) for linha in conexao.execute(text("SELECT * FROM acordao")) for v in linha
        )
        relatores = set(conexao.scalars(text("SELECT DISTINCT relator FROM acordao")))
    texto = chave(tudo).upper()
    for nome in dados.NOMES_CAMADA_1 + dados.NOMES_CAMADA_2:
        assert nome not in texto, nome
    assert dados.MARCADOR_DESCARTADO not in texto
    assert "Des. Aristeu Prudente Valença" in relatores


@respx.mock
def test_nova_versao_reprocessa_e_confere_ausentes(
    coleta: fabrica.ColetaDjen, banco: Engine, config: Config
) -> None:
    # metadados: coleta do v1, verificação, reprocessamento e segunda verificação
    _servir(respx.mock, 1, 2, 2, 2)
    checagem = respx.get(f"{URL_API}/api/v1/comunicacao").respond(
        200, json=ler_json("comunicacao-900020-cancelada.json")
    )
    _processar_v1(coleta)
    with banco.connect() as conexao:
        versoes_antes = dict(conexao.execute(text("SELECT id_fonte, versao FROM acordao")).all())

    def verificar() -> list:  # type: ignore[type-arg]
        return verificar_versoes(
            banco,
            coleta.orquestrador,
            coleta.cliente,
            coleta.bruto,
            url_api=URL_API,
            status_cancelamento=config.djen.status_cancelamento,
            tribunal="TJPR",
            hoje=HOJE,
        )

    (resultado,) = verificar()
    assert (resultado.versao_anterior, resultado.versao_atual) == (1, 2)
    assert resultado.reprocessado
    assert (resultado.ausentes, resultado.cancelados) == (1, 1)
    assert checagem.call_count == 1

    situacoes = _situacoes(banco)
    assert situacoes[str(dados.AUSENTE_NO_V2)] == "cancelado"
    assert situacoes[str(dados.CANCELADA_NO_V2)] == "cancelado"
    with banco.connect() as conexao:
        motivo = conexao.scalar(
            text("SELECT motivo_situacao FROM acordao WHERE id_fonte = :id"),
            {"id": str(dados.AUSENTE_NO_V2)},
        )
        caderno = conexao.execute(text("SELECT versao, verificado_em FROM caderno_djen")).one()
        versoes_depois = dict(conexao.execute(text("SELECT id_fonte, versao FROM acordao")).all())
    assert motivo == "ausente na versão 2 do caderno"
    assert caderno.versao == 2 and caderno.verificado_em is not None
    # O conteúdo das demais não mudou: nenhuma nova versão de acórdão.
    assert versoes_depois == versoes_antes

    # Mesma versão na próxima verificação: nada a reprocessar.
    (resultado,) = verificar()
    assert not resultado.reprocessado
    assert checagem.call_count == 1


@respx.mock(assert_all_called=False)
def test_reprocessar_do_bruto_sem_rede_respeita_bloqueio(
    coleta: fabrica.ColetaDjen, banco: Engine, config: Config, respx_mock: respx.MockRouter
) -> None:
    _servir(respx_mock, 1)
    _processar_v1(coleta)
    with banco.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO bloqueio (fonte, id_fonte, motivo) VALUES ('djen', '900003', 'teste')"
            )
        )
        conexao.execute(text("DELETE FROM acordao WHERE id_fonte <> '900003'"))
    chamadas = len(respx_mock.calls)

    (resultado,) = reprocessar_cadernos(
        banco,
        coleta.bruto,
        coleta.processador,
        de=DIA,
        ate=DIA,
        tribunal="tjpr",
        versao_parser=VERSAO_PARSER,
    )
    assert len(respx_mock.calls) == chamadas  # nenhuma requisição
    assert resultado.itens == 20
    assert resultado.contadores.bloqueados == 1
    situacoes = _situacoes(banco)
    assert len(situacoes) == 20
    assert situacoes["900003"] == "removido"
    with banco.connect() as conexao:
        assert conexao.scalar(text("SELECT bloqueados FROM caderno_djen")) == 1


@respx.mock
def test_cli_djen_falha_fechada_sem_ner(
    url_banco_teste: str,
    banco: Engine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("BUSCAJUS_DATABASE_URL", url_banco_teste)
    obter_engine.cache_clear()
    try:
        codigo = cli.main(
            ["ingest", "djen", "--tribunal", "TJPR", "--de", dados.DATA, "--ate", dados.DATA]
        )
    finally:
        obter_engine.cache_clear()
    assert codigo == 2
    assert "NER" in capsys.readouterr().err
    assert not respx.mock.calls
    with banco.connect() as conexao:
        assert conexao.scalar(text("SELECT count(*) FROM caderno_djen")) == 0


@respx.mock(assert_all_called=False)
def test_cli_reprocessar(
    coleta: fabrica.ColetaDjen,
    config: Config,
    url_banco_teste: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    respx_mock: respx.MockRouter,
) -> None:
    _servir(respx_mock, 1)
    _processar_v1(coleta)
    monkeypatch.setenv("BUSCAJUS_DATABASE_URL", url_banco_teste)
    monkeypatch.setenv("BUSCAJUS_DIRETORIO_RAW", str(config.diretorio_raw))
    obter_engine.cache_clear()
    try:
        codigo = cli.main(
            ["ingest", "reprocessar", "--fonte", "djen", "--de", dados.DATA, "--ate", dados.DATA]
        )
    finally:
        obter_engine.cache_clear()
    assert codigo == 0
    saida = json.loads(capsys.readouterr().out)
    assert saida[0]["itens"] == 20
    assert saida[0]["quarentena"] == 1
