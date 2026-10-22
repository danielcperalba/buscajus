"""Processo de fundo: coleta agendada e geração de embeddings.

Na Fase 0 o worker só sobe, registra que está ocioso e espera um sinal de parada.
"""

import logging
import signal
import threading
from types import FrameType

from buscajus.core.config import obter_config
from buscajus.core.logging import configurar_logging

log = logging.getLogger(__name__)


def main() -> None:
    config = obter_config()
    configurar_logging(config.nivel_log)
    parar = threading.Event()

    def _ao_receber_sinal(signum: int, _frame: FrameType | None) -> None:
        log.info("sinal recebido, encerrando", extra={"sinal": signal.Signals(signum).name})
        parar.set()

    signal.signal(signal.SIGTERM, _ao_receber_sinal)
    signal.signal(signal.SIGINT, _ao_receber_sinal)

    log.info(
        "worker iniciado (ocioso)",
        extra={"djen_tribunais": config.djen.tribunais, "tjdft_ativo": config.tjdft.ativo},
    )
    parar.wait()


if __name__ == "__main__":
    main()
