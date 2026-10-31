"""Processo de fundo: coleta agendada e geração de embeddings.

Ao iniciar, apaga cadernos órfãos da área temporária. Com ``agendador.ativo``, roda o
agendador (coleta diária do DJEN com checagem de versões e coleta diária do TJDFT com
recoleta de 30 dias) a cada ``intervalo_segundos``; sem ele, fica ocioso até receber um sinal
de parada.
"""

import logging
import signal
import threading
from types import FrameType

from buscajus.core.config import Config, obter_config
from buscajus.core.erros import descrever_erro
from buscajus.core.logging import configurar_logging
from buscajus.db.engine import obter_engine
from buscajus.ingest import temporario
from buscajus.ingest.agendador import (
    TAREFA_DJEN_DIARIO,
    TAREFA_TJDFT_CONFERENCIA,
    TAREFA_TJDFT_DIARIO,
    Agendador,
    Executor,
    coleta_djen_diaria,
    coleta_tjdft_diaria,
    conferencia_tjdft_mensal,
)

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

    if not config.agendador.ativo:
        log.info(
            "worker iniciado (agendador desligado)",
            extra={"djen_tribunais": config.djen.tribunais, "tjdft_ativo": config.tjdft.ativo},
        )
        parar.wait()
        return

    engine = obter_engine()
    executores: dict[str, Executor] = {TAREFA_DJEN_DIARIO: coleta_djen_diaria(config, engine)}
    if config.tjdft.ativo:
        executores[TAREFA_TJDFT_DIARIO] = coleta_tjdft_diaria(config, engine)
        executores[TAREFA_TJDFT_CONFERENCIA] = conferencia_tjdft_mensal(config, engine)
    agendador = Agendador(engine, config, executores)
    log.info(
        "worker iniciado (agendador ligado)",
        extra={"djen_tribunais": config.djen.tribunais, "tjdft_ativo": config.tjdft.ativo},
    )
    while not parar.is_set():
        try:
            agendador.ciclo()
        except Exception as exc:
            # Só o tipo e o local: a mensagem de exceções genéricas pode trazer conteúdo.
            log.error("falha no ciclo do agendador", extra={"erro": descrever_erro(exc)})
        parar.wait(config.agendador.intervalo_segundos)


if __name__ == "__main__":
    main()
