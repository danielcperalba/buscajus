"""Agendador do worker (F1-30) sobre a fila ``tarefa`` (``FOR UPDATE SKIP LOCKED``).

A cada ciclo: agenda a tarefa diária de cada tribunal do DJEN (uma por dia, a partir do
horário configurado) e executa as tarefas pendentes que já venceram. Cada execução fica
registrada na própria ``tarefa`` (status, tentativas, último erro sem conteúdo).

Desligado por padrão (``agendador.ativo = false``): ligar depende de decidir onde os dados
reais ficam.
"""

import json
import logging
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, text

from buscajus.core.config import Config
from buscajus.core.erros import descrever_erro
from buscajus.ingest.djen.fabrica import criar_coleta
from buscajus.ingest.djen.versoes import verificar_versoes

log = logging.getLogger(__name__)

FUSO = ZoneInfo("America/Sao_Paulo")
TAREFA_DJEN_DIARIO = "djen_diario"

Executor = Callable[[Mapping[str, Any]], None]


class Agendador:
    def __init__(
        self,
        engine: Engine,
        config: Config,
        executores: Mapping[str, Executor],
        *,
        agora: Callable[[], datetime] = lambda: datetime.now(FUSO),
    ) -> None:
        self._engine = engine
        self._config = config
        self._executores = executores
        self._agora = agora

    def ciclo(self) -> int:
        """Agenda o que venceu e executa as pendentes. Devolve quantas executou."""
        self.agendar()
        executadas = 0
        while self.executar_proxima():
            executadas += 1
        return executadas

    def agendar(self) -> None:
        agora = self._agora().astimezone(FUSO)
        horario = datetime.combine(agora.date(), self._config.agendador.horario_djen, FUSO)
        if agora < horario:
            return
        for tribunal in self._config.djen.tribunais:
            payload = {"tribunal": tribunal, "data": agora.date().isoformat()}
            with self._engine.begin() as conexao:
                conexao.execute(
                    text("""
                        INSERT INTO tarefa (tipo, payload, agendada_para)
                        SELECT :tipo, CAST(:payload AS jsonb), :quando
                        WHERE NOT EXISTS (
                            SELECT 1 FROM tarefa
                            WHERE tipo = :tipo AND payload = CAST(:payload AS jsonb)
                        )
                    """),
                    {"tipo": TAREFA_DJEN_DIARIO, "payload": json.dumps(payload), "quando": horario},
                )

    def executar_proxima(self) -> bool:
        with self._engine.begin() as conexao:
            tarefa = conexao.execute(
                text("""
                    SELECT id, tipo, payload FROM tarefa
                    WHERE status = 'pendente' AND agendada_para <= :agora
                    ORDER BY agendada_para, id
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                """),
                {"agora": self._agora()},
            ).one_or_none()
            if tarefa is None:
                return False
            conexao.execute(
                text("""
                    UPDATE tarefa SET status = 'em_andamento', tentativas = tentativas + 1,
                        iniciada_em = now()
                    WHERE id = :id
                """),
                {"id": tarefa.id},
            )

        status, erro = "concluida", None
        try:
            executor = self._executores.get(tarefa.tipo)
            if executor is None:
                raise LookupError(tarefa.tipo)
            executor(tarefa.payload)
        except Exception as exc:
            status, erro = "erro", descrever_erro(exc)
            log.error(
                "tarefa com erro", extra={"tarefa": tarefa.id, "tipo": tarefa.tipo, "erro": erro}
            )
        else:
            log.info("tarefa concluída", extra={"tarefa": tarefa.id, "tipo": tarefa.tipo})
        with self._engine.begin() as conexao:
            conexao.execute(
                text("""
                    UPDATE tarefa SET status = :status, ultimo_erro = :erro, concluida_em = now()
                    WHERE id = :id
                """),
                {"id": tarefa.id, "status": status, "erro": erro},
            )
        return True


def coleta_djen_diaria(config: Config, engine: Engine) -> Executor:
    """Executor da tarefa diária: cadernos recentes do tribunal e checagem de versões."""

    def executar(payload: Mapping[str, Any]) -> None:
        tribunal = str(payload["tribunal"])
        hoje = datetime.fromisoformat(str(payload["data"])).date()
        coleta = criar_coleta(config, engine)  # sem NER: falha fechada aqui
        try:
            inicio = hoje - timedelta(days=config.agendador.dias_retroativos)
            coleta.orquestrador.executar(coleta.conector.planejar(tribunal, inicio, hoje))
            verificar_versoes(
                engine,
                coleta.orquestrador,
                coleta.cliente,
                coleta.bruto,
                url_api=config.djen.url_api,
                status_cancelamento=config.djen.status_cancelamento,
                tribunal=tribunal,
                hoje=hoje,
                dias=config.agendador.dias_verificacao_versao,
            )
        finally:
            coleta.fechar()

    return executar
