"""Relógio monotônico injetável, para que esperas e limites de taxa sejam testáveis."""

import time
from typing import Protocol


class Relogio(Protocol):
    def agora(self) -> float:
        """Segundos num relógio monotônico."""
        ...

    def dormir(self, segundos: float) -> None: ...


class RelogioSistema:
    def agora(self) -> float:
        return time.monotonic()

    def dormir(self, segundos: float) -> None:
        if segundos > 0:
            time.sleep(segundos)
