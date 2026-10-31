"""F6-03 (ausência de dados pessoais) e F6-04 (segredo de justiça), de ponta a ponta.

Pipeline completo com as fixtures sintéticas e o anonimizador real (NER falso): DJEN e TJDFT
até o banco, varrendo todas as tabelas, todos os arquivos brutos e os logs. Bloqueia o merge
se falhar (roda no CI).
"""

import gzip
import json
import logging
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import respx
from sqlalchemy import Engine, text

from buscajus.api.consulta import analisar_consulta
from buscajus.api.esquemas import FiltrosBusca
from buscajus.busca.servico import ServicoPostgres
from buscajus.core.config import Config
from buscajus.ingest.anonimizacao.pipeline import criar_anonimizador
from buscajus.ingest.djen import fabrica as fabrica_djen
from buscajus.ingest.runner import Resultado
from buscajus.ingest.texto import chave
from buscajus.ingest.tjdft import fabrica as fabrica_tjdft
from buscajus.ingest.tjdft.anonimizacao import criar_anonimizador as anonimizador_tjdft
from fixtures.djen import dados as djen
from fixtures.tjdft import dados as tjdft

from .anonimizacao_ajuda import DetectorFalso
from .djen_ajuda import DIA, HOJE, URL_API, area_vazia, servir_caderno, url_metadados
from .test_tjdft_anonimizacao import NOMES_DETECTADOS
from .tjdft_ajuda import DIA as DIA_TJDFT
from .tjdft_ajuda import URL_API as URL_TJDFT
from .tjdft_ajuda import ServidorTjdft, alterar_registro, fixture, uuid

pytestmark = pytest.mark.banco


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        diretorio_raw=tmp_path / "raw",
        diretorio_tmp_cadernos=tmp_path / "tmp",
        djen={"url_api": URL_API, "requisicoes_por_segundo": 1000},
        tjdft={"url_api": URL_TJDFT, "requisicoes_por_segundo": 1000},
    )


def _banco_inteiro(banco: Engine) -> str:
    with banco.connect() as conexao:
        tabelas = conexao.scalars(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "AND tablename NOT IN ('alembic_version', 'classe_cnj')"
            )
        ).all()
        return "\n".join(
            str(conexao.scalar(text(f"SELECT coalesce(json_agg(t)::text, '') FROM {t} t")))  # noqa: S608
            for t in tabelas
        )


def _brutos(raiz: Path) -> str:
    return "\n".join(
        gzip.decompress(arquivo.read_bytes()).decode("utf-8")
        for arquivo in sorted(raiz.rglob("*.jsonl.gz"))
    )


def _normalizado(texto: str) -> str:
    """Sem acentos e em maiúsculas (o banco e o bruto guardam UTF-8 sem escapes)."""
    return chave(texto).upper()


def _sem_cpf(texto: str, cpf: str) -> bool:
    return not re.search(rf"(?<![\d.]){re.escape(cpf)}(?![\d-])", texto)


# --- F6-03: DJEN ----------------------------------------------------------------------


@pytest.fixture
def djen_processado(
    banco: Engine, config: Config, caplog: pytest.LogCaptureFixture
) -> Iterator[dict[str, str]]:
    caplog.set_level(logging.DEBUG)
    with respx.mock(assert_all_called=False) as roteador:
        servir_caderno(roteador, DIA)
        coleta = fabrica_djen.criar_coleta(
            config, banco, anonimizador=criar_anonimizador(DetectorFalso())
        )
        coleta.conector._hoje = lambda: HOJE
        try:
            (resumo,) = coleta.orquestrador.executar(coleta.conector.planejar("TJPR", DIA, DIA))
        finally:
            coleta.fechar()
    assert resumo.resultado is Resultado.CONCLUIDA
    yield {
        "banco": _normalizado(_banco_inteiro(banco)),
        "bruto": _normalizado(_brutos(config.diretorio_raw)),
        "logs": _normalizado(" ".join(f"{r.getMessage()} {vars(r)}" for r in caplog.records)),
    }


def test_nenhum_destinatario_pf_sobra_no_banco_no_bruto_nem_nos_logs(
    djen_processado: dict[str, str],
) -> None:
    for onde, conteudo in djen_processado.items():
        for nome in djen.NOMES_CAMADA_1 + djen.NOMES_CAMADA_2:
            assert nome not in conteudo, (onde, nome)
        for cpf in djen.CPFS:
            assert _sem_cpf(conteudo, cpf), (onde, cpf)
        assert djen.MARCADOR_DESCARTADO not in conteudo, onde
        assert "X-AMZ" not in conteudo, onde  # URL temporária do caderno


def test_nomes_de_pj_entes_publicos_e_magistrados_ficam(djen_processado: dict[str, str]) -> None:
    for preservado in (*djen.PRESERVADOS, *djen.RELATORES):
        assert _normalizado(preservado) in djen_processado["banco"], preservado
    for numero in djen.NAO_CPFS:
        assert numero in djen_processado["banco"]


def test_area_temporaria_vazia_depois_de_falha(banco: Engine, config: Config) -> None:
    with respx.mock(assert_all_called=False) as roteador:
        meta = json.loads(
            (
                Path(djen.__file__).parent / f"metadados-{djen.DATA}-v1-hash-incorreto.json"
            ).read_text(encoding="utf-8")
        )
        roteador.get(url_metadados(DIA)).respond(200, json=meta)
        conteudo = (Path(djen.__file__).parent / f"caderno-{djen.DATA}-v1.zip").read_bytes()
        roteador.get(meta["url"]).respond(200, content=conteudo)
        coleta = fabrica_djen.criar_coleta(
            config, banco, anonimizador=criar_anonimizador(DetectorFalso())
        )
        coleta.conector._hoje = lambda: HOJE
        try:
            (resumo,) = coleta.orquestrador.executar(coleta.conector.planejar("TJPR", DIA, DIA))
        finally:
            coleta.fechar()
    assert resumo.resultado is Resultado.ERRO
    assert area_vazia(config.diretorio_tmp_cadernos)
    assert not list(config.diretorio_raw.rglob("*.jsonl.gz"))


def test_esquema_sem_colunas_de_partes(banco: Engine) -> None:
    with banco.connect() as conexao:
        colunas = conexao.scalars(
            text("SELECT column_name FROM information_schema.columns WHERE table_schema='public'")
        ).all()
    assert [c for c in colunas if re.search(r"destinatari|advogad|parte|cpf|cnpj|polo", c)] == []


# --- F6-03 e F6-04: TJDFT -------------------------------------------------------------

# Variantes de segredo: o registro 1 vira cada uma delas; o registro 3 já vem com true.
VARIANTES = {
    "true": lambda r: r.update(segredoJustica=True),
    "null": lambda r: r.update(segredoJustica=None),
    "ausente": lambda r: r.pop("segredoJustica"),
    "1": lambda r: r.update(segredoJustica=1),
    "S": lambda r: r.update(segredoJustica="S"),
}


def _coletar_tjdft(banco: Engine, config: Config, pagina0: dict[str, Any] | None = None) -> None:
    with respx.mock(assert_all_called=False) as roteador:
        servidor = ServidorTjdft(roteador)
        if pagina0 is not None:
            servidor.servir(DIA_TJDFT, 0, pagina0)
        coleta = fabrica_tjdft.criar_coleta(
            config, banco, anonimizador=anonimizador_tjdft(DetectorFalso(NOMES_DETECTADOS))
        )
        coleta.conector._hoje = lambda: HOJE
        try:
            unidade = coleta.conector.planejar("TJDFT", DIA_TJDFT, DIA_TJDFT)[0]
            resumo = coleta.orquestrador.executar_unidade(unidade, forcar=True)
        finally:
            coleta.fechar()
    assert resumo.resultado is Resultado.CONCLUIDA


@pytest.mark.parametrize("variante", sorted(VARIANTES))
def test_segredo_nao_aparece_em_tabela_bruto_nem_busca(
    banco: Engine, config: Config, variante: str
) -> None:
    pagina0 = alterar_registro(fixture(DIA_TJDFT, 0), 1, VARIANTES[variante])
    _coletar_tjdft(banco, config, pagina0)

    gravado = _banco_inteiro(banco) + _brutos(config.diretorio_raw)
    for sigiloso in (uuid(1), uuid(3)):
        assert sigiloso not in gravado
    assert tjdft.MARCADOR_SEGREDO not in gravado
    # A ementa do registro 1 (plano de saúde) não está em lugar nenhum nem na busca.
    assert "NEGATIVA DE COBERTURA" not in gravado.upper()
    servico = ServicoPostgres(banco)
    for consulta in ("negativa de cobertura plano de saúde", "guarda alimentos sigilario"):
        resposta = servico.buscar(analisar_consulta(consulta), FiltrosBusca(), 1)
        assert all(
            "NEGATIVA DE COBERTURA" not in r.trecho.upper() and "SIGILARIO" not in r.trecho.upper()
            for r in resposta.resultados
        ), consulta
    with banco.connect() as conexao:
        janela = conexao.execute(text("SELECT descartados_segredo FROM coleta_janela")).one()
    assert janela.descartados_segredo == 2


def test_tjdft_sem_pessoas_nem_cpf_gravados(banco: Engine, config: Config) -> None:
    _coletar_tjdft(banco, config)
    gravado = _normalizado(_banco_inteiro(banco) + _brutos(config.diretorio_raw))
    for nome in tjdft.DEVEM_SUMIR:
        assert _normalizado(nome) not in gravado
    for cpf in tjdft.CPFS:
        assert _sem_cpf(gravado, cpf)
    for marcador in tjdft.NUNCA:
        assert marcador not in gravado
    for preservado in tjdft.PRESERVADOS:
        assert _normalizado(preservado) in gravado
