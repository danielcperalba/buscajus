"""Processo de fundo: coleta agendada e geração de embeddings.

Por enquanto o worker só limpa a área temporária, registra que está ocioso e espera um
sinal de parada.
"""

import logging
import signal
import threading
from types import FrameType

from buscajus.core.config import Config, obter_config
from buscajus.core.logging import configurar_logging
from buscajus.ingest import temporario

log = logging.getLogger(__name__)


def preparar(config: Config) -> None:
    """Passos de inicialização: apaga cadernos órfãos de uma execução interrompida."""
    temporario.limpar_orfaos(config.diretorio_tmp_cadernos)
    temporario.preparar(config.diretorio_tmp_cadernos)


def main() -> None:
    config = obter_config()
    configurar_logging(config.nivel_log)
    preparar(config)
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
