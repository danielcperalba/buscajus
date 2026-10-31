"""Montagem da coleta do DJEN a partir da configuração.

Falha fechada: sem modelo de NER configurado, :func:`criar_coleta` levanta
``ErroAnonimizacao`` antes de abrir qualquer conexão com a fonte.
"""

from dataclasses import dataclass

from sqlalchemy import Engine

from buscajus.core.config import Config
from buscajus.ingest.anonimizacao import Anonimizador
from buscajus.ingest.anonimizacao.modelo_ner import carregar_detector
from buscajus.ingest.anonimizacao.pipeline import criar_anonimizador
from buscajus.ingest.bruto import ArmazenamentoBruto
from buscajus.ingest.djen.campos import RegraEstado
from buscajus.ingest.djen.conector import ConectorDjen
from buscajus.ingest.djen.normalizacao import normalizar
from buscajus.ingest.djen.parser import VERSAO_PARSER
from buscajus.ingest.http import ClienteHttp
from buscajus.ingest.processamento import ProcessadorAcordaos
from buscajus.ingest.runner import Orquestrador


@dataclass
class ColetaDjen:
    cliente: ClienteHttp
    conector: ConectorDjen
    orquestrador: Orquestrador
    bruto: ArmazenamentoBruto
    processador: ProcessadorAcordaos

    def fechar(self) -> None:
        self.cliente.fechar()


def regra_estado(config: Config) -> RegraEstado:
    return RegraEstado.de(config.djen.status_ativos, config.djen.status_cancelamento)


def processador(config: Config) -> ProcessadorAcordaos:
    return ProcessadorAcordaos(
        normalizar,
        regra_estado(config).classificar,
        prioridades=config.prioridade_fontes,
    )


def criar_coleta(
    config: Config,
    engine: Engine,
    *,
    anonimizador: Anonimizador | None = None,
    tribunal: str | None = None,
) -> ColetaDjen:
    """``anonimizador`` só é passado nos testes; em produção vem da configuração.

    Com ``tribunal``, a taxa de requisições é a do ajuste do tribunal, se houver (F7-01).
    """
    anonimizar = anonimizador or criar_anonimizador(
        carregar_detector(config.anonimizacao, config.diretorio_modelos)
    )
    cliente = ClienteHttp(config.http, config.djen.taxa(tribunal))
    conector = ConectorDjen(config.djen, cliente, anonimizar, config.diretorio_tmp_cadernos)
    bruto = ArmazenamentoBruto(config.diretorio_raw)
    proc = processador(config)
    orquestrador = Orquestrador(
        engine,
        conector,
        bruto,
        processar=proc,
        estatisticas_http=cliente.estatisticas,
        versao_parser=VERSAO_PARSER,
    )
    return ColetaDjen(cliente, conector, orquestrador, bruto, proc)
