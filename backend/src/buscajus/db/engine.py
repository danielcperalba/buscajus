from functools import lru_cache

from sqlalchemy import Engine, create_engine, text

from buscajus.core.config import obter_config


@lru_cache
def obter_engine() -> Engine:
    return create_engine(obter_config().database_url, pool_pre_ping=True)


def banco_disponivel(engine: Engine) -> bool:
    try:
        with engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))
    except Exception:
        return False
    return True
