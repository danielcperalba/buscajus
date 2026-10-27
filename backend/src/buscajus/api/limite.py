"""Limite de taxa por IP na API (F4-13).

Janela deslizante em memória, por IP e por tipo de rota: consultas (busca, detalhe, processo,
filtros, relatores) e pedidos de remoção têm limites distintos. Acima do limite, 429 com
``Retry-After``. Vale para um processo da API; com vários processos, cada um conta o seu (o
MVP roda um só).
"""

import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import Request

from buscajus.api.servico import ErroApi


class LimitadorJanela:
    def __init__(
        self,
        limite: int,
        janela_segundos: float,
        *,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limite = limite
        self._janela = janela_segundos
        self._relogio = relogio
        self._eventos: dict[str, deque[float]] = {}
        self._trava = threading.Lock()

    def registrar(self, chave: str) -> float | None:
        """Conta um pedido; devolve ``None`` se cabe no limite ou os segundos até caber."""
        agora = self._relogio()
        with self._trava:
            eventos = self._eventos.setdefault(chave, deque())
            while eventos and eventos[0] <= agora - self._janela:
                eventos.popleft()
            if len(eventos) >= self._limite:
                return eventos[0] + self._janela - agora
            eventos.append(agora)
            # Libera a memória de IPs que pararam de pedir.
            if len(self._eventos) > 10_000:
                for antigo in [k for k, v in self._eventos.items() if not v]:
                    del self._eventos[antigo]
            return None


def ip_do_cliente(request: Request, *, confiar_x_forwarded_for: bool) -> str:
    if confiar_x_forwarded_for:
        encaminhado = request.headers.get("x-forwarded-for")
        if encaminhado:
            return encaminhado.split(",")[0].strip()
    return request.client.host if request.client else "desconhecido"


def verificar(limitador: LimitadorJanela, chave: str) -> None:
    espera = limitador.registrar(chave)
    if espera is not None:
        raise ErroApi(
            429,
            "limite_excedido",
            "muitas requisições; tente de novo em instantes",
            cabecalhos={"Retry-After": str(max(1, int(espera + 0.999)))},
        )
