"""Serviço por trás das rotas da API (F4-01).

As rotas só validam e traduzem HTTP; o trabalho fica num :class:`ServicoBusca`. Enquanto a
busca não existe (F4-03 em diante), o serviço padrão responde 501. Com ``api.mock = true``, um
serviço com dados sintéticos fixos (``api.mock``) responde no formato do contrato, para o
frontend trabalhar contra o servidor de verdade.
"""

from typing import Protocol

from buscajus.api.consulta import ConsultaAnalisada
from buscajus.api.esquemas import (
    AcordaosDoProcesso,
    DetalheAcordao,
    Filtros,
    FiltrosBusca,
    Indisponivel,
    PedidoRemocao,
    Relator,
    RemocaoRecebida,
    RespostaBusca,
)


class ErroApi(Exception):
    """Erro com status HTTP e código estável; vira ``Erro`` no corpo da resposta."""

    def __init__(self, status: int, erro: str, mensagem: str) -> None:
        super().__init__(mensagem)
        self.status = status
        self.erro = erro
        self.mensagem = mensagem


class ServicoBusca(Protocol):
    def buscar(
        self, consulta: ConsultaAnalisada, filtros: FiltrosBusca, pagina: int
    ) -> RespostaBusca: ...

    def detalhe(self, acordao_id: int) -> DetalheAcordao | Indisponivel | None: ...

    def processo(self, digitos: str) -> AcordaosDoProcesso | None: ...

    def filtros(self) -> Filtros: ...

    def relatores(self, prefixo: str) -> list[Relator]: ...

    def registrar_remocao(self, pedido: PedidoRemocao) -> RemocaoRecebida: ...


class ServicoIndisponivel:
    """Busca ainda não implementada (Fase 4): toda rota responde 501."""

    def _indisponivel(self) -> ErroApi:
        return ErroApi(501, "nao_implementado", "a busca ainda não está disponível")

    def buscar(
        self, consulta: ConsultaAnalisada, filtros: FiltrosBusca, pagina: int
    ) -> RespostaBusca:
        raise self._indisponivel()

    def detalhe(self, acordao_id: int) -> DetalheAcordao | Indisponivel | None:
        raise self._indisponivel()

    def processo(self, digitos: str) -> AcordaosDoProcesso | None:
        raise self._indisponivel()

    def filtros(self) -> Filtros:
        raise self._indisponivel()

    def relatores(self, prefixo: str) -> list[Relator]:
        raise self._indisponivel()

    def registrar_remocao(self, pedido: PedidoRemocao) -> RemocaoRecebida:
        raise self._indisponivel()
