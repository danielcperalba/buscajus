import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from buscajus.core.config import obter_config


@pytest.fixture(autouse=True)
def _config_limpa(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isola cada teste das variáveis BUSCAJUS_* e do .env da máquina."""
    for variavel in list(os.environ):
        if variavel.startswith("BUSCAJUS_") and variavel != "BUSCAJUS_TEST_DATABASE_URL":
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
