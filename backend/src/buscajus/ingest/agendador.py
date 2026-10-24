"""Agendador do worker (F1-30, F2-10) sobre a fila ``tarefa`` (``FOR UPDATE SKIP LOCKED``).

A cada ciclo: agenda as tarefas diárias (uma por dia, a partir do horário configurado) que
este worker sabe executar e executa as pendentes que já venceram:

- DJEN, uma por tribunal: cadernos recentes e checagem de versões;
- TJDFT: o dia mais recente, a reconsulta do anterior e a recoleta dos últimos
  ``dias_recoleta_tjdft`` dias (mudanças de segredo e registros publicados com atraso);
- TJDFT, uma vez por mês (``dia_conferencia_tjdft``): conferência dos dias de 31 a
  ``dias_conferencia_tjdft`` atrás, recoletando só os que mudaram (F2-14).

Cada execução fica registrada na própria ``tarefa`` (status, tentativas, último erro sem
conteúdo).

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
from buscajus.ingest.djen import fabrica
from buscajus.ingest.djen.fabrica import criar_coleta
from buscajus.ingest.djen.versoes import verificar_versoes
from buscajus.ingest.tjdft import fabrica as fabrica_tjdft
from buscajus.ingest.tjdft.conferencia import conferir_dias_antigos

log = logging.getLogger(__name__)

FUSO = ZoneInfo("America/Sao_Paulo")
TAREFA_DJEN_DIARIO = "djen_diario"
TAREFA_TJDFT_DIARIO = "tjdft_diario"
TAREFA_TJDFT_CONFERENCIA = "tjdft_conferencia_mensal"

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
        hoje = agora.date().isoformat()
        config = self._config.agendador
        tarefas = [
            (TAREFA_DJEN_DIARIO, config.horario_djen, {"tribunal": tribunal, "data": hoje})
            for tribunal in self._config.djen.tribunais
        ]
        if self._config.tjdft.ativo:
            tarefas.append((TAREFA_TJDFT_DIARIO, config.horario_tjdft, {"data": hoje}))
            if agora.day == config.dia_conferencia_tjdft:
                tarefas.append((TAREFA_TJDFT_CONFERENCIA, config.horario_tjdft, {"data": hoje}))
        for tipo, horario_do_dia, payload in tarefas:
            horario = datetime.combine(agora.date(), horario_do_dia, FUSO)
            if agora < horario or tipo not in self._executores:
                continue
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
                    {"tipo": tipo, "payload": json.dumps(payload), "quando": horario},
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
                regra=fabrica.regra_estado(config),
                tribunal=tribunal,
                hoje=hoje,
                dias=config.agendador.dias_verificacao_versao,
            )
        finally:
            coleta.fechar()

    return executar


def coleta_tjdft_diaria(config: Config, engine: Engine) -> Executor:
    """Executor da tarefa diária do TJDFT: do dia mais recente aos últimos 30 dias.

    Todos os dias são recoletados (``forcar``): o mais recente, a reconsulta do anterior
    (virada do dia em UTC) e a recoleta, que pega mudanças de segredo e registros publicados
    com atraso. O upsert por uuid evita duplicatas.
    """

    def executar(payload: Mapping[str, Any]) -> None:
        hoje = datetime.fromisoformat(str(payload["data"])).date()
        coleta = fabrica_tjdft.criar_coleta(config, engine)  # sem NER: falha fechada aqui
        try:
            inicio = hoje - timedelta(days=config.agendador.dias_recoleta_tjdft)
            unidades = coleta.conector.planejar("TJDFT", inicio, hoje)
            coleta.orquestrador.executar(unidades, forcar=True)
        finally:
            coleta.fechar()

    return executar


def conferencia_tjdft_mensal(config: Config, engine: Engine) -> Executor:
    """Executor da conferência mensal do TJDFT (F2-14)."""

    def executar(payload: Mapping[str, Any]) -> None:
        hoje = datetime.fromisoformat(str(payload["data"])).date()
        coleta = fabrica_tjdft.criar_coleta(config, engine)  # sem NER: falha fechada aqui
        try:
            dias = conferir_dias_antigos(
                engine,
                coleta.conector,
                coleta.orquestrador,
                hoje=hoje,
                de_dias=config.agendador.dias_recoleta_tjdft + 1,
                ate_dias=config.agendador.dias_conferencia_tjdft,
            )
        finally:
            coleta.fechar()
        log.info(
            "conferência do TJDFT concluída",
            extra={
                "dias": len(dias),
                "recoletados": sum(d.recoletado for d in dias),
                "erros": sum(d.erro is not None for d in dias),
            },
        )

    return executar
