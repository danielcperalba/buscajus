"""Limite de taxa por IP na API (F4-13).

Janela deslizante em memória, por IP e por tipo de rota: consultas (busca, detalhe, processo,
filtros, relatores) e pedidos de remoção têm limites distintos. Acima do limite, 429 com
``Retry-After``. Vale para um processo da API; com vários processos, cada um conta o seu (o
MVP roda um só).

IP do cliente: com ``api.proxies_confiaveis = N > 0``, o N-ésimo item **a partir da direita**
do ``X-Forwarded-For`` (o que os nossos proxies acrescentaram); os itens à esquerda vêm do
cliente e podem ser falsificados. Com 0, ou com o cabeçalho ausente, curto ou malformado, vale
o IP da conexão.

Memória: no máximo ``max_chaves`` IPs são acompanhados; acima disso, os menos recentes são
descartados (um ataque com IPs variados não faz a memória crescer sem limite).
"""

import ipaddress
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable

from fastapi import Request

from buscajus.api.servico import ErroApi

MAX_CHAVES = 100_000


class LimitadorJanela:
    def __init__(
        self,
        limite: int,
        janela_segundos: float,
        *,
        max_chaves: int = MAX_CHAVES,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limite = limite
        self._janela = janela_segundos
        self._max_chaves = max_chaves
        self._relogio = relogio
        # Ordem de uso: a primeira chave é a menos recente.
        self._eventos: OrderedDict[str, deque[float]] = OrderedDict()
        self._trava = threading.Lock()

    @property
    def chaves(self) -> int:
        return len(self._eventos)

    def registrar(self, chave: str) -> float | None:
        """Conta um pedido; devolve ``None`` se cabe no limite ou os segundos até caber."""
        agora = self._relogio()
        with self._trava:
            eventos = self._eventos.get(chave)
            if eventos is None:
                while len(self._eventos) >= self._max_chaves:
                    self._eventos.popitem(last=False)
                eventos = self._eventos[chave] = deque()
            self._eventos.move_to_end(chave)
            while eventos and eventos[0] <= agora - self._janela:
                eventos.popleft()
            if len(eventos) >= self._limite:
                return eventos[0] + self._janela - agora
            eventos.append(agora)
            return None


def _ip(valor: str) -> str | None:
    try:
        return str(ipaddress.ip_address(valor.strip()))
    except ValueError:
        return None


def ip_do_cliente(request: Request, *, proxies_confiaveis: int) -> str:
    conexao = request.client.host if request.client else "desconhecido"
    if proxies_confiaveis <= 0:
        return conexao
    cabecalho = request.headers.get("x-forwarded-for")
    if not cabecalho:
        return conexao
    itens = cabecalho.split(",")
    if len(itens) < proxies_confiaveis:
        return conexao
    return _ip(itens[-proxies_confiaveis]) or conexao


def verificar(limitador: LimitadorJanela, chave: str) -> None:
    espera = limitador.registrar(chave)
    if espera is not None:
        raise ErroApi(
            429,
            "limite_excedido",
            "muitas requisições; tente de novo em instantes",
            cabecalhos={"Retry-After": str(max(1, int(espera + 0.999)))},
        )
