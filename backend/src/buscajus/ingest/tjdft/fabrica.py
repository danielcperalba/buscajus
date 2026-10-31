"""Montagem da coleta do TJDFT a partir da configuração.

Falha fechada: sem modelo de NER configurado, :func:`criar_coleta` levanta
``ErroAnonimizacao`` antes de abrir qualquer conexão com a fonte.
"""

from dataclasses import dataclass

from sqlalchemy import Engine

from buscajus.core.config import Config
from buscajus.core.erros import ErroSeguro
from buscajus.db.classes_cnj import nomes_por_codigo
from buscajus.ingest.anonimizacao import Anonimizador
from buscajus.ingest.anonimizacao.modelo_ner import carregar_detector
from buscajus.ingest.bruto import ArmazenamentoBruto
from buscajus.ingest.http import ClienteHttp
from buscajus.ingest.runner import Orquestrador
from buscajus.ingest.tjdft.anonimizacao import criar_anonimizador
from buscajus.ingest.tjdft.conector import ConectorTjdft
from buscajus.ingest.tjdft.normalizacao import VERSAO_NORMALIZACAO, NormalizadorTjdft
from buscajus.ingest.tjdft.processamento import ProcessadorTjdft


class ConectorDesativado(ErroSeguro):
    pass


@dataclass
class ColetaTjdft:
    cliente: ClienteHttp
    conector: ConectorTjdft
    orquestrador: Orquestrador

    def fechar(self) -> None:
        self.cliente.fechar()


def criar_coleta(
    config: Config, engine: Engine, *, anonimizador: Anonimizador | None = None
) -> ColetaTjdft:
    """``anonimizador`` só é passado nos testes; em produção vem da configuração."""
    if not config.tjdft.ativo:
        raise ConectorDesativado("o conector do TJDFT está desativado (tjdft.ativo = false)")
    anonimizar = anonimizador or criar_anonimizador(
        carregar_detector(config.anonimizacao, config.diretorio_modelos)
    )
    with engine.connect() as conexao:
        classes = nomes_por_codigo(conexao)
    cliente = ClienteHttp(config.http, config.tjdft.requisicoes_por_segundo)
    conector = ConectorTjdft(config.tjdft, cliente, anonimizar)
    bruto = ArmazenamentoBruto(config.diretorio_raw)
    orquestrador = Orquestrador(
        engine,
        conector,
        bruto,
        processar=ProcessadorTjdft(
            NormalizadorTjdft(classes), bruto, prioridades=config.prioridade_fontes
        ),
        estatisticas_http=cliente.estatisticas,
        versao_parser=VERSAO_NORMALIZACAO,
    )
    return ColetaTjdft(cliente, conector, orquestrador)
