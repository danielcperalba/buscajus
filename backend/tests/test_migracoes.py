import re
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config as ConfigAlembic
from sqlalchemy import Engine, text

from buscajus.db.classes_cnj import ler_tpu

pytestmark = pytest.mark.banco

TABELAS_POR_REVISAO = {
    "0002": {"caderno_djen", "coleta_janela", "coleta_bruta", "tarefa"},
    "0003": {"acordao", "acordao_historico"},
    "0004": {"bloqueio", "pedido_remocao"},
    "0006": {"classe_cnj"},
}

# Nenhuma coluna pode guardar partes, advogados ou destinatários (ARCHITECTURE.md, seção 6.6).
COLUNA_PROIBIDA = re.compile(r"destinatari|advogad|parte|cpf|cnpj|polo")


@pytest.fixture(autouse=True)
def _banco_vazio(alembic: ConfigAlembic) -> Iterator[None]:
    command.downgrade(alembic, "base")
    yield
    command.downgrade(alembic, "base")


def _tabelas(engine: Engine) -> set[str]:
    with engine.connect() as conexao:
        return set(
            conexao.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        )


def test_upgrade_cria_extensoes(alembic: ConfigAlembic, engine: Engine) -> None:
    command.upgrade(alembic, "head")
    with engine.connect() as conexao:
        extensoes = set(conexao.scalars(text("SELECT extname FROM pg_extension")))
    assert {"vector", "unaccent", "pg_trgm"} <= extensoes


def test_pt_unaccent_ignora_acentos(alembic: ConfigAlembic, engine: Engine) -> None:
    command.upgrade(alembic, "head")
    with engine.connect() as conexao:
        com_acento = conexao.scalar(text("SELECT to_tsvector('pt_unaccent', 'Herança')::text"))
        sem_acento = conexao.scalar(text("SELECT to_tsvector('pt_unaccent', 'heranca')::text"))
    assert com_acento == sem_acento == "'heranc':1"


def test_downgrade_e_upgrade_de_novo(alembic: ConfigAlembic, engine: Engine) -> None:
    command.upgrade(alembic, "head")
    command.downgrade(alembic, "base")
    with engine.connect() as conexao:
        assert (
            conexao.scalar(text("SELECT count(*) FROM pg_ts_config WHERE cfgname = 'pt_unaccent'"))
            == 0
        )
    assert _tabelas(engine) <= {"alembic_version"}
    command.upgrade(alembic, "head")


@pytest.mark.parametrize("revisao", sorted(TABELAS_POR_REVISAO))
def test_cada_migracao_aplica_e_reverte(
    alembic: ConfigAlembic, engine: Engine, revisao: str
) -> None:
    anterior = f"{int(revisao) - 1:04d}"
    command.upgrade(alembic, revisao)
    assert TABELAS_POR_REVISAO[revisao] <= _tabelas(engine)
    command.downgrade(alembic, anterior)
    assert not TABELAS_POR_REVISAO[revisao] & _tabelas(engine)


def test_esquema_sem_colunas_de_partes(alembic: ConfigAlembic, engine: Engine) -> None:
    command.upgrade(alembic, "head")
    with engine.connect() as conexao:
        colunas = conexao.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public'"
            )
        ).all()
    assert colunas
    proibidas = [f"{t}.{c}" for t, c in colunas if COLUNA_PROIBIDA.search(c)]
    assert proibidas == []


def test_busca_tsv_e_data_referencia_sao_geradas(alembic: ConfigAlembic, engine: Engine) -> None:
    command.upgrade(alembic, "head")
    with engine.begin() as conexao:
        conexao.execute(
            text("""
                INSERT INTO acordao (fonte, id_fonte, numero_processo, numero_processo_mascara,
                    numero_processo_valido, tribunal, ementa, link_oficial, hash_conteudo,
                    data_disponibilizacao, classe_nome)
                VALUES ('djen', '1', '00000000000000000000', '0000000-00.0000.0.00.0000',
                    false, 'TJPR', 'Partilha de bens na herança.', 'https://exemplo',
                    'h', '2026-10-14', 'Apelação Cível')
            """)
        )
        linha = conexao.execute(
            text(
                "SELECT data_referencia, busca_tsv @@ to_tsquery('pt_unaccent', 'heranca') "
                "FROM acordao"
            )
        ).one()
    assert str(linha[0]) == "2026-10-14"
    assert linha[1] is True


def test_0005_anomalias_e_classe_citacao(alembic: ConfigAlembic, engine: Engine) -> None:
    def colunas() -> set[str]:
        with engine.connect() as conexao:
            return {
                f"{t}.{c}"
                for t, c in conexao.execute(
                    text(
                        "SELECT table_name, column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public'"
                    )
                )
            }

    novas = {"caderno_djen.anomalias", "coleta_janela.anomalias", "acordao.classe_citacao"}
    command.upgrade(alembic, "0005")
    assert novas <= colunas()
    command.downgrade(alembic, "0004")
    assert not novas & colunas()


def test_0006_carrega_a_tpu(alembic: ConfigAlembic, engine: Engine) -> None:
    tpu = ler_tpu()
    command.upgrade(alembic, "0006")
    with engine.connect() as conexao:
        total, referencias = conexao.execute(
            text("SELECT count(*), array_agg(DISTINCT tpu_referencia) FROM classe_cnj")
        ).one()
        nome = conexao.scalar(text("SELECT nome FROM classe_cnj WHERE codigo = 198"))
    assert total == len(tpu.classes) > 800
    assert referencias == [tpu.data_referencia]
    assert nome == "Apelação Cível"


def test_0007_colunas_do_tjdft(alembic: ConfigAlembic, engine: Engine) -> None:
    def colunas() -> set[str]:
        with engine.connect() as conexao:
            return {
                f"{t}.{c}"
                for t, c in conexao.execute(
                    text(
                        "SELECT table_name, column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public'"
                    )
                )
            }

    novas = {
        "acordao.relator_designado",
        "acordao.relator_designado_chave",
        "acordao.local_publicacao",
        "coleta_janela.descartados_segredo",
    }
    command.upgrade(alembic, "0007")
    assert novas <= colunas()
    command.downgrade(alembic, "0006")
    assert not novas & colunas()
