"""Cliente HTTP das fontes: taxa limitada, User-Agent identificável e novas tentativas.

Regras (ARCHITECTURE.md, seção 3.1):

- *token bucket* por fonte, sem rajadas; pausa preventiva quando ``x-ratelimit-remaining``
  chega a zero;
- 429 → espera ``Retry-After`` (ou 60 s) e tenta de novo;
- 5xx, timeout e falha de conexão → *backoff* curto (5 s, 15 s, 45 s);
- depois de ``max_tentativas``, :class:`TentativasEsgotadas`.

As mensagens de erro e os logs nunca trazem a URL, só o rótulo da requisição: a URL
temporária do caderno do DJEN não pode ser gravada nem logada.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx

from buscajus import __version__
from buscajus.core.config import URL_PROJETO, ConfigHttp
from buscajus.core.erros import ErroSeguro
from buscajus.core.relogio import Relogio, RelogioSistema

log = logging.getLogger(__name__)

# O httpx registra cada requisição com a URL completa em INFO. Vale para qualquer processo
# que use este cliente, mesmo sem configurar_logging.
for _nome in ("httpx", "httpcore", "httpx2", "httpcore2"):
    logging.getLogger(_nome).setLevel(logging.WARNING)


class ErroHttp(ErroSeguro):
    """Falha de requisição a uma fonte. A mensagem é segura para log (sem URL)."""


class TentativasEsgotadas(ErroHttp):
    pass


class RespostaGrandeDemais(ErroHttp):
    pass


class _Transitorio(Exception):
    """Falha que merece nova tentativa; sem ``espera``, vale o *backoff* da tentativa."""

    def __init__(self, motivo: str, espera: float | None = None) -> None:
        super().__init__(motivo)
        self.motivo = motivo
        self.espera = espera


@dataclass
class Estatisticas:
    requisicoes: int = 0
    respostas_429: int = 0
    novas_tentativas: int = 0
    pausas_limite: int = 0


def user_agent(contato: str | None) -> str:
    detalhes = f"+{URL_PROJETO}" + (f"; {contato}" if contato else "")
    return f"BuscaJus/{__version__} ({detalhes})"


class BaldeDeFichas:
    """*Token bucket* sem rajadas: no máximo ``taxa`` requisições por segundo."""

    def __init__(self, taxa: float, relogio: Relogio, capacidade: float = 1.0) -> None:
        self._taxa = taxa
        self._capacidade = capacidade
        self._relogio = relogio
        self._fichas = capacidade
        self._ultimo = relogio.agora()

    def adquirir(self) -> None:
        agora = self._relogio.agora()
        self._fichas = min(self._capacidade, self._fichas + (agora - self._ultimo) * self._taxa)
        self._ultimo = agora
        if self._fichas < 1:
            espera = (1 - self._fichas) / self._taxa
            self._relogio.dormir(espera)
            self._fichas = 1
            self._ultimo = agora + espera
        self._fichas -= 1


class ClienteHttp:
    def __init__(
        self,
        config: ConfigHttp,
        requisicoes_por_segundo: float,
        *,
        relogio: Relogio | None = None,
    ) -> None:
        self._config = config
        self._relogio = relogio or RelogioSistema()
        self._balde = BaldeDeFichas(requisicoes_por_segundo, self._relogio)
        self._bloqueado_ate = 0.0
        self.estatisticas = Estatisticas()
        self._http = httpx.Client(
            headers={"User-Agent": user_agent(config.contato)},
            timeout=httpx.Timeout(config.timeout_segundos, connect=config.timeout_conexao_segundos),
            follow_redirects=False,
        )

    def __enter__(self) -> "ClienteHttp":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.fechar()

    def fechar(self) -> None:
        self._http.close()

    def requisitar(self, metodo: str, url: str, *, rotulo: str, **kwargs: Any) -> httpx.Response:
        """Faz a requisição com novas tentativas.

        Devolve a resposta de qualquer status que não seja 429 nem 5xx (inclusive 404);
        quem chama decide o que fazer com ela.
        """

        def enviar() -> httpx.Response:
            resposta = self._http.request(metodo, url, **kwargs)
            self._verificar(resposta)
            return resposta

        return self._com_tentativas(rotulo, enviar)

    def baixar(self, url: str, destino: Path, *, rotulo: str, limite_bytes: int) -> int:
        """Baixa em streaming para ``destino`` e devolve o número de bytes.

        Em qualquer falha o arquivo parcial é apagado.
        """

        def enviar() -> int:
            with self._http.stream(
                "GET", url, timeout=self._config.timeout_download_segundos
            ) as resposta:
                self._verificar(resposta)
                if resposta.status_code != httpx.codes.OK:
                    raise ErroHttp(f"{rotulo}: HTTP {resposta.status_code}")
                total = 0
                with destino.open("wb") as arquivo:
                    for bloco in resposta.iter_bytes():
                        total += len(bloco)
                        if total > limite_bytes:
                            raise RespostaGrandeDemais(
                                f"{rotulo}: maior que o limite de {limite_bytes} bytes"
                            )
                        arquivo.write(bloco)
                return total

        try:
            return self._com_tentativas(rotulo, enviar)
        except BaseException:
            destino.unlink(missing_ok=True)
            raise

    def _com_tentativas[T](self, rotulo: str, enviar: Callable[[], T]) -> T:
        maximo = self._config.max_tentativas
        for tentativa in range(1, maximo + 1):
            self._aguardar_vez()
            self.estatisticas.requisicoes += 1
            try:
                return enviar()
            except httpx.TimeoutException:
                falha = _Transitorio("timeout")
            except httpx.TransportError:
                falha = _Transitorio("falha de conexão")
            except _Transitorio as transitorio:
                falha = transitorio
            if tentativa == maximo:
                break
            espera = self._backoff(tentativa) if falha.espera is None else falha.espera
            self.estatisticas.novas_tentativas += 1
            log.warning(
                "falha transitória, nova tentativa",
                extra={
                    "rotulo": rotulo,
                    "motivo": falha.motivo,
                    "tentativa": tentativa,
                    "espera_s": espera,
                },
            )
            self._relogio.dormir(espera)
        raise TentativasEsgotadas(f"{rotulo}: {falha.motivo} após {maximo} tentativas")

    def _aguardar_vez(self) -> None:
        espera = self._bloqueado_ate - self._relogio.agora()
        if espera > 0:
            self._relogio.dormir(espera)
        self._balde.adquirir()

    def _verificar(self, resposta: httpx.Response) -> None:
        """Lê os cabeçalhos de limite e converte 429/5xx em falha transitória."""
        restante = _inteiro(resposta.headers.get("x-ratelimit-remaining"))
        if restante is not None and restante <= 0:
            self.estatisticas.pausas_limite += 1
            self._bloqueado_ate = max(
                self._bloqueado_ate,
                self._relogio.agora() + self._config.pausa_limite_esgotado_segundos,
            )
        if resposta.status_code == httpx.codes.TOO_MANY_REQUESTS:
            self.estatisticas.respostas_429 += 1
            raise _Transitorio("HTTP 429", self._espera_429(resposta.headers.get("retry-after")))
        if resposta.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
            raise _Transitorio(f"HTTP {resposta.status_code}")

    def _espera_429(self, retry_after: str | None) -> float:
        espera = _segundos_retry_after(retry_after)
        if espera is None:
            espera = self._config.espera_429_segundos
        return min(espera, self._config.espera_maxima_429_segundos)

    def _backoff(self, tentativa: int) -> float:
        esperas = self._config.backoff_segundos
        return esperas[min(tentativa, len(esperas)) - 1]


def _inteiro(valor: str | None) -> int | None:
    if valor is None:
        return None
    try:
        return int(valor.strip())
    except ValueError:
        return None


def _segundos_retry_after(valor: str | None) -> float | None:
    """``Retry-After`` em segundos ou como data HTTP."""
    if valor is None:
        return None
    valor = valor.strip()
    if valor.isdigit():
        return float(valor)
    try:
        quando = parsedate_to_datetime(valor)
    except (TypeError, ValueError):
        return None
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=UTC)
    return max(0.0, (quando - datetime.now(UTC)).total_seconds())
