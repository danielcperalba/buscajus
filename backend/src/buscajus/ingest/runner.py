"""Orquestrador genérico da coleta (ARCHITECTURE.md, seção 3.4).

Para cada unidade: consulta o estado, pula as concluídas (salvo ``forcar``), marca como em
andamento e percorre os lotes do conector. Cada lote é gravado no bruto filtrado e, numa
única transação, registrado em ``coleta_bruta``, processado e somado ao estado da unidade.

Retomada (F1-10):

- unidade concluída → pulada, salvo ``forcar``;
- caderno (não paginado) interrompido ou com erro → reprocessado inteiro;
- unidade paginada interrompida ou com erro → continua de ``ultima_pagina + 1``; com
  ``forcar``, recomeça da página 0.

Uma interrupção do processo (sinal, ``KeyboardInterrupt``) deixa a unidade ``em_andamento``;
um erro comum a marca como ``erro`` e o orquestrador segue para a próxima unidade.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from sqlalchemy import Connection, Engine

from buscajus.core.erros import descrever_erro
from buscajus.ingest.bruto import ArmazenamentoBruto
from buscajus.ingest.conector import (
    Checkpoint,
    Conector,
    Contadores,
    LoteBruto,
    UnidadeColeta,
    UnidadeNaoPronta,
    UnidadeSemDados,
)
from buscajus.ingest.estado import Repositorio, registrar_coleta_bruta, repositorio_para
from buscajus.ingest.http import Estatisticas

log = logging.getLogger(__name__)


class Processador(Protocol):
    """Etapas seguintes ao bruto (normalização, PII, upsert), na transação do lote.

    Devolve as contagens que acrescenta (falhas de parser, quarentena, cancelados…).
    """

    def __call__(
        self, conexao: Connection, lote: LoteBruto, coleta_bruta_id: int
    ) -> Contadores: ...


class Resultado(StrEnum):
    CONCLUIDA = "concluida"
    PULADA = "pulada"
    SEM_DADOS = "sem_dados"
    NAO_PRONTA = "nao_pronta"
    ERRO = "erro"


@dataclass
class ResumoUnidade:
    unidade: UnidadeColeta
    resultado: Resultado
    contadores: Contadores = field(default_factory=Contadores)
    lotes: int = 0
    erro: str | None = None


class Orquestrador:
    def __init__(
        self,
        engine: Engine,
        conector: Conector,
        bruto: ArmazenamentoBruto,
        *,
        processar: Processador | None = None,
        estatisticas_http: Estatisticas | None = None,
        versao_parser: str | None = None,
    ) -> None:
        self._engine = engine
        self._conector = conector
        self._bruto = bruto
        self._processar = processar
        self._estatisticas = estatisticas_http
        self._versao_parser = versao_parser

    def executar(
        self, unidades: Iterable[UnidadeColeta], *, forcar: bool = False
    ) -> list[ResumoUnidade]:
        return [self.executar_unidade(unidade, forcar=forcar) for unidade in unidades]

    def executar_unidade(self, unidade: UnidadeColeta, *, forcar: bool = False) -> ResumoUnidade:
        repo = repositorio_para(unidade)
        with self._engine.begin() as conexao:
            estado = repo.obter(conexao, unidade)
            if estado is not None and estado.concluida and not forcar:
                return ResumoUnidade(unidade, Resultado.PULADA)
            retomar = (
                unidade.paginada
                and not forcar
                and estado is not None
                and estado.status in ("em_andamento", "erro")
            )
            estado = repo.iniciar(conexao, unidade, recomecar=not retomar)

        checkpoint = Checkpoint(estado.ultima_pagina if retomar else None)
        resumo = ResumoUnidade(unidade, Resultado.CONCLUIDA)
        respostas_429_antes = self._respostas_429()
        try:
            self._coletar(unidade, checkpoint, repo, estado.id, resumo)
        except UnidadeSemDados:
            resumo.resultado = Resultado.SEM_DADOS
        except UnidadeNaoPronta:
            resumo.resultado = Resultado.NAO_PRONTA
        except Exception as exc:
            resumo.resultado = Resultado.ERRO
            resumo.erro = descrever_erro(exc)

        respostas_429 = self._respostas_429() - respostas_429_antes
        with self._engine.begin() as conexao:
            match resumo.resultado:
                case Resultado.CONCLUIDA:
                    repo.concluir(conexao, estado.id, respostas_429, self._versao_parser)
                case Resultado.SEM_DADOS:
                    repo.marcar_sem_dados(conexao, estado.id, respostas_429)
                case Resultado.NAO_PRONTA:
                    repo.marcar_pendente(conexao, estado.id, respostas_429)
                case _:
                    repo.marcar_erro(conexao, estado.id, respostas_429, resumo.erro or "")
        self._log(resumo)
        return resumo

    def _coletar(
        self,
        unidade: UnidadeColeta,
        checkpoint: Checkpoint,
        repo: Repositorio,
        id_unidade: int,
        resumo: ResumoUnidade,
    ) -> None:
        lotes = self._conector.coletar(unidade, checkpoint)
        try:
            for lote in lotes:
                arquivo = self._bruto.gravar(
                    lote.caminho_bruto, lote.itens, self._conector.lista_branca
                )
                with self._engine.begin() as conexao:
                    id_bruta = registrar_coleta_bruta(
                        conexao, unidade, id_unidade, arquivo, lote.pagina, self._versao_parser
                    )
                    if self._processar is not None:
                        lote.contadores.somar(self._processar(conexao, lote, id_bruta))
                    repo.registrar_lote(conexao, id_unidade, lote)
                resumo.contadores.somar(lote.contadores)
                resumo.lotes += 1
        finally:
            # Garante o ``finally`` do conector (ex.: apagar o ZIP) mesmo se o laço parar aqui.
            fechar = getattr(lotes, "close", None)
            if fechar is not None:
                fechar()

    def _respostas_429(self) -> int:
        return self._estatisticas.respostas_429 if self._estatisticas else 0

    @staticmethod
    def _log(resumo: ResumoUnidade) -> None:
        c = resumo.contadores
        extra = {
            "unidade": resumo.unidade.descricao,
            "resultado": str(resumo.resultado),
            "lotes": resumo.lotes,
            "recebidos": c.recebidos,
            "aceitos": c.aceitos,
            "rejeitados_anonimizacao": len(c.rejeitados_anonimizacao),
            "falhas_parser": c.falhas_parser,
            "quarentena": c.quarentena,
            "cancelados": c.cancelados,
            "anomalias": c.anomalias,
        }
        if resumo.resultado is Resultado.ERRO:
            log.error("unidade com erro", extra=extra | {"erro": resumo.erro})
        else:
            log.info("unidade finalizada", extra=extra)
