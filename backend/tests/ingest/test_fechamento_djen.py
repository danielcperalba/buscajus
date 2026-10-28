"""Fluxo completo do DJEN com o banco: F1-16, F1-23 a F1-28."""

import gzip
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import respx
from sqlalchemy import Engine, text

from buscajus import cli
from buscajus.core.config import Config
from buscajus.db.engine import obter_engine
from buscajus.ingest import remocao
from buscajus.ingest.anonimizacao.pipeline import criar_anonimizador
from buscajus.ingest.djen import fabrica
from buscajus.ingest.djen.parser import VERSAO_PARSER
from buscajus.ingest.djen.versoes import verificar_versoes
from buscajus.ingest.reprocessamento import reprocessar_cadernos
from buscajus.ingest.texto import chave
from buscajus.ingest.upsert import MOTIVO_ANOMALIA
from fixtures.djen import PASTA, dados, item_ementa

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
            regra=fabrica.regra_estado(config),
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


def test_anomalia_e_texto_nulo_nao_derrubam_o_caderno(
    coleta: fabrica.ColetaDjen, banco: Engine
) -> None:
    anonimizar = criar_anonimizador(DetectorFalso())
    itens = [anonimizar(item_ementa(e)) for e in dados.EMENTAS[:3]]
    assert all(isinstance(i, dict) for i in itens)
    itens[0] = itens[0] | {"status": "X"}  # status não reconhecido
    itens[1] = itens[1] | {"texto": None}  # 3 casos no F1-01
    with banco.begin() as conexao:
        contadores = coleta.processador.processar_itens(conexao, itens, None)  # type: ignore[arg-type]
    assert (contadores.anomalias, contadores.falhas_parser, contadores.cancelados) == (1, 1, 0)
    with banco.connect() as conexao:
        linhas = dict(
            conexao.execute(
                text(
                    "SELECT id_fonte, situacao::text || ':' || coalesce(motivo_situacao, '') "
                    "FROM acordao"
                )
            ).all()
        )
    assert linhas == {
        "900001": f"quarentena:{MOTIVO_ANOMALIA}",
        "900003": "ativo:",
    }


@respx.mock(assert_all_called=False)
def test_cli_djen_imprime_so_o_resumo_json(
    banco: Engine,
    config: Config,
    url_banco_teste: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    respx_mock: respx.MockRouter,
) -> None:
    _servir(respx_mock, 1)
    original = fabrica.criar_coleta

    def criar(config: Config, engine: Engine, **opcoes: Any) -> fabrica.ColetaDjen:
        coleta = original(
            config, engine, anonimizador=criar_anonimizador(DetectorFalso()), **opcoes
        )
        coleta.conector._hoje = lambda: HOJE
        return coleta

    monkeypatch.setattr(fabrica, "criar_coleta", criar)
    monkeypatch.setenv("BUSCAJUS_DATABASE_URL", url_banco_teste)
    monkeypatch.setenv("BUSCAJUS_DIRETORIO_RAW", str(config.diretorio_raw))
    monkeypatch.setenv("BUSCAJUS_DIRETORIO_TMP_CADERNOS", str(config.diretorio_tmp_cadernos))
    monkeypatch.setenv("BUSCAJUS_DJEN__URL_API", URL_API)
    monkeypatch.setenv("BUSCAJUS_DJEN__REQUISICOES_POR_SEGUNDO", "1000")
    obter_engine.cache_clear()
    try:
        codigo = cli.main(
            ["ingest", "djen", "--tribunal", "TJPR", "--de", dados.DATA, "--ate", dados.DATA]
        )
    finally:
        obter_engine.cache_clear()
    assert codigo == 0
    saida = capsys.readouterr()
    (resumo,) = json.loads(saida.out)  # stdout é só o resumo JSON
    assert resumo["resultado"] == "concluida"
    assert '"unidade finalizada"' in saida.err  # os logs vão para stderr


def _conteudo_em_disco(raiz: Path) -> str:
    return "\n".join(
        gzip.decompress(arquivo.read_bytes()).decode("utf-8")
        for arquivo in sorted(raiz.rglob("*.jsonl.gz"))
    )


@respx.mock(assert_all_called=False)
def test_remocao_apaga_o_conteudo_e_reprocessamento_respeita_o_bloqueio(
    coleta: fabrica.ColetaDjen, banco: Engine, config: Config, respx_mock: respx.MockRouter
) -> None:
    """F2-13: nada do removido sobra no banco nem no disco, nem depois de reprocessar."""
    _servir(respx_mock, 1, 1)
    _processar_v1(coleta)
    with banco.connect() as conexao:
        alvo = conexao.execute(
            text("SELECT id, ementa FROM acordao WHERE id_fonte = '900001'")
        ).one()
    trecho = alvo.ementa[:60]
    assert '"id":900001' in _conteudo_em_disco(config.diretorio_raw)

    with banco.begin() as conexao:
        assert remocao.remover(conexao, coleta.bruto, [alvo.id], "pedido de remoção aceito") == [
            alvo.id
        ]

    def verificar() -> None:
        with banco.connect() as conexao:
            linha = conexao.execute(
                text("SELECT situacao::text AS sit, ementa, decisao FROM acordao WHERE id = :id"),
                {"id": alvo.id},
            ).one()
            assert (linha.sit, linha.ementa, linha.decisao) == ("removido", "", None)
            assert (
                conexao.scalar(text("SELECT count(*) FROM bloqueio WHERE id_fonte = '900001'")) == 1
            )
            banco_inteiro = str(conexao.scalar(text("SELECT json_agg(a)::text FROM acordao a")))
            historico = str(
                conexao.scalar(text("SELECT json_agg(h)::text FROM acordao_historico h"))
            )
            bruta = conexao.execute(text("SELECT itens FROM coleta_bruta")).scalar_one()
        disco = _conteudo_em_disco(config.diretorio_raw)
        assert trecho not in banco_inteiro + historico
        assert '"id":900001' not in disco and '"id":"900001"' not in disco
        assert bruta == 19  # coleta_bruta acompanha o arquivo reescrito

    verificar()
    reprocessar_cadernos(
        banco,
        coleta.bruto,
        coleta.processador,
        de=DIA,
        ate=DIA,
        versao_parser=VERSAO_PARSER,
    )
    verificar()
    # Recoleta do caderno: o item volta no ZIP, é recusado pelo bloqueio e sai do bruto.
    (resumo,) = coleta.orquestrador.executar(
        coleta.conector.planejar("TJPR", DIA, DIA), forcar=True
    )
    assert resumo.contadores.bloqueados == 1
    verificar()


def _verificar(coleta: fabrica.ColetaDjen, banco: Engine, config: Config) -> Any:
    (resultado,) = verificar_versoes(
        banco,
        coleta.orquestrador,
        coleta.cliente,
        coleta.bruto,
        url_api=URL_API,
        regra=fabrica.regra_estado(config),
        tribunal="TJPR",
        hoje=HOJE,
    )
    return resultado


@respx.mock(assert_all_called=False)
def test_verificacao_sem_metadados_prontos_nao_reprocessa(
    coleta: fabrica.ColetaDjen, banco: Engine, config: Config, respx_mock: respx.MockRouter
) -> None:
    """F6-01: caderno já processado cujo metadado some (404) fica como está."""
    _servir(respx_mock, 1)
    _processar_v1(coleta)
    respx_mock.get(url_metadados(DIA)).respond(404)
    resultado = _verificar(coleta, banco, config)
    assert (resultado.versao_atual, resultado.reprocessado, resultado.erro) == (None, False, None)


@respx.mock(assert_all_called=False)
def test_reprocessamento_com_erro_fica_registrado(
    coleta: fabrica.ColetaDjen, banco: Engine, config: Config, respx_mock: respx.MockRouter
) -> None:
    """F6-01: nova versão cujo ZIP não baixa (5xx persistente) vira erro, sem conteúdo."""
    _servir(respx_mock, 1)
    _processar_v1(coleta)
    meta_v2 = ler_json(f"metadados-{dados.DATA}-v2.json")
    respx_mock.get(url_metadados(DIA)).respond(200, json=meta_v2)
    respx_mock.get(meta_v2["url"]).respond(503)
    coleta.cliente._config = coleta.cliente._config.model_copy(update={"max_tentativas": 1})
    resultado = _verificar(coleta, banco, config)
    assert resultado.versao_atual == 2 and not resultado.reprocessado
    assert resultado.erro is not None and "503" in resultado.erro
    assert _situacoes(banco)[str(dados.AUSENTE_NO_V2)] == "ativo"


@respx.mock(assert_all_called=False)
def test_ausente_em_estado_anomalo_vai_para_quarentena(
    coleta: fabrica.ColetaDjen, banco: Engine, config: Config, respx_mock: respx.MockRouter
) -> None:
    """F6-01: a checagem pontual devolve um status desconhecido → quarentena (falha fechada)."""
    _servir(respx_mock, 1, 2, 2)
    anomala = ler_json("comunicacao-900020-cancelada.json")
    for item in anomala["items"]:
        item.update(ativo=True, status="X", data_cancelamento=None)
    respx_mock.get(f"{URL_API}/api/v1/comunicacao").respond(200, json=anomala)
    _processar_v1(coleta)
    resultado = _verificar(coleta, banco, config)
    assert resultado.reprocessado and resultado.anomalias == 1
    assert _situacoes(banco)[str(dados.AUSENTE_NO_V2)] == "quarentena"
