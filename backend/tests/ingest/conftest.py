import pytest

from buscajus.core.config import ConfigHttp


class RelogioFalso:
    """Relógio simulado: ``dormir`` só avança o tempo e registra a espera."""

    def __init__(self) -> None:
        self.tempo = 1000.0
        self.esperas: list[float] = []

    def agora(self) -> float:
        return self.tempo

    def dormir(self, segundos: float) -> None:
        if segundos > 0:
            self.esperas.append(round(segundos, 6))
            self.tempo += segundos


@pytest.fixture
def relogio() -> RelogioFalso:
    return RelogioFalso()


@pytest.fixture
def config_http() -> ConfigHttp:
    return ConfigHttp()
