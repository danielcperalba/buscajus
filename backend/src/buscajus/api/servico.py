"""Serviço por trás das rotas da API (F4-01).

As rotas só validam e traduzem HTTP; o trabalho fica num :class:`ServicoBusca`: o real, sobre o
Postgres (``busca.servico``), ou, com ``api.mock = true``, um com dados sintéticos fixos
(``api.mock``), para o frontend trabalhar sem banco.
"""

from typing import Protocol

from buscajus.api.consulta import ConsultaAnalisada
from buscajus.api.esquemas import (
    AcordaosDoProcesso,
    CoberturaTribunal,
    DetalheAcordao,
    Filtros,
    FiltrosBusca,
    Indisponivel,
    PedidoRemocao,
    Relator,
    RemocaoRecebida,
    RespostaBusca,
    SituacaoAcordao,
)


class ErroApi(Exception):
    """Erro com status HTTP e código estável; vira ``Erro`` no corpo da resposta."""

    def __init__(
        self, status: int, erro: str, mensagem: str, *, cabecalhos: dict[str, str] | None = None
    ) -> None:
        super().__init__(mensagem)
        self.status = status
        self.erro = erro
        self.mensagem = mensagem
        self.cabecalhos = cabecalhos or {}


class ServicoBusca(Protocol):
    def buscar(
        self, consulta: ConsultaAnalisada, filtros: FiltrosBusca, pagina: int
    ) -> RespostaBusca: ...

    def detalhe(self, acordao_id: int) -> DetalheAcordao | Indisponivel | None: ...

    def situacao(self, acordao_id: int) -> SituacaoAcordao | None:
        """``None`` para inexistente e para o que não é exibido (quarentena, duplicado)."""
        ...

    def processo(self, digitos: str) -> AcordaosDoProcesso | None: ...

    def filtros(self) -> Filtros: ...

    def cobertura(self) -> list[CoberturaTribunal]: ...

    def relatores(self, prefixo: str) -> list[Relator]: ...

    def registrar_remocao(self, pedido: PedidoRemocao) -> RemocaoRecebida: ...
