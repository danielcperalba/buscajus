from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from buscajus.core.config import obter_config

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Os testes passam a URL explicitamente; fora deles, vale BUSCAJUS_DATABASE_URL.
url = config.get_main_option("sqlalchemy.url") or obter_config().database_url


def executar_offline() -> None:
    context.configure(url=url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def executar_online() -> None:
    engine = create_engine(url)
    with engine.connect() as conexao:
        context.configure(connection=conexao)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    executar_offline()
else:
    executar_online()
