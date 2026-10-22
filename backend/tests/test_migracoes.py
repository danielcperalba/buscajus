from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as ConfigAlembic
from sqlalchemy import Engine, create_engine, text

pytestmark = pytest.mark.banco

ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"


@pytest.fixture
def alembic(url_banco_teste: str) -> Iterator[ConfigAlembic]:
    config = ConfigAlembic(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url_banco_teste)
    command.downgrade(config, "base")
    yield config
    command.downgrade(config, "base")


@pytest.fixture
def engine(url_banco_teste: str) -> Iterator[Engine]:
    engine = create_engine(url_banco_teste)
    yield engine
    engine.dispose()


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
    command.upgrade(alembic, "head")
