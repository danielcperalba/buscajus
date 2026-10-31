import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as ConfigAlembic
from sqlalchemy import Engine, create_engine, text

from buscajus.core.config import obter_config

ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"


@pytest.fixture(autouse=True)
def _config_limpa(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isola cada teste das variáveis BUSCAJUS_* e do .env da máquina."""
    for variavel in list(os.environ):
        if variavel.startswith("BUSCAJUS_") and not variavel.startswith("BUSCAJUS_TEST_"):
            monkeypatch.delenv(variavel)
    monkeypatch.chdir(Path(__file__).parent)
    obter_config.cache_clear()
    yield
    obter_config.cache_clear()


@pytest.fixture
def url_banco_teste() -> str:
    """Banco descartável para testes; o conteúdo é apagado pelos próprios testes."""
    url = os.environ.get("BUSCAJUS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("BUSCAJUS_TEST_DATABASE_URL não definida")
    return url


@pytest.fixture
def alembic(url_banco_teste: str) -> ConfigAlembic:
    config = ConfigAlembic(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url_banco_teste)
    return config


@pytest.fixture
def engine(url_banco_teste: str) -> Iterator[Engine]:
    engine = create_engine(url_banco_teste)
    yield engine
    engine.dispose()


@pytest.fixture
def banco(alembic: ConfigAlembic, engine: Engine) -> Iterator[Engine]:
    """Banco com todas as migrações aplicadas; as tabelas são esvaziadas ao fim do teste.

    Tabelas de referência carregadas pelas migrações (``classe_cnj``) são preservadas.
    """
    command.upgrade(alembic, "head")
    yield engine
    with engine.begin() as conexao:
        tabelas = conexao.scalars(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' "
                "AND tablename NOT IN ('alembic_version', 'classe_cnj')"
            )
        ).all()
        if tabelas:
            conexao.execute(text(f"TRUNCATE {', '.join(tabelas)} RESTART IDENTITY CASCADE"))
