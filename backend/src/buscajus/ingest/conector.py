"""Interface comum dos conectores (ARCHITECTURE.md, seção 3.4).

Um conector sabe planejar unidades de coleta e produzir lotes já filtrados, anonimizados e
com a lista branca aplicada. Estado, gravação do bruto e processamento ficam com o
orquestrador (``ingest.runner``), que é o mesmo para todas as fontes.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal, Protocol

from buscajus.core.erros import ErroSeguro

Fonte = Literal["djen", "tjdft"]


@dataclass(frozen=True)
class UnidadeColeta:
    """DJEN: um caderno (tribunal + dia), não paginado. TJDFT: uma janela de datas, paginada."""

    fonte: Fonte
    tribunal: str
    data_inicio: date
    data_fim: date
    paginada: bool

    @property
    def descricao(self) -> str:
        periodo = self.data_inicio.isoformat()
        if self.data_fim != self.data_inicio:
            periodo += f"..{self.data_fim.isoformat()}"
        return f"{self.fonte}/{self.tribunal}/{periodo}"


@dataclass(frozen=True)
class Checkpoint:
    """Onde retomar. Só unidades paginadas retomam; as demais recomeçam do zero."""

    ultima_pagina: int | None = None

    @property
    def proxima_pagina(self) -> int:
        return 0 if self.ultima_pagina is None else self.ultima_pagina + 1


@dataclass
class Contadores:
    recebidos: int = 0
    aceitos: int = 0
    descartados: int = 0
    # Ids das comunicações recusadas pela falha segura da anonimização (nunca o conteúdo).
    rejeitados_anonimizacao: list[str] = field(default_factory=list)
    falhas_parser: int = 0
    quarentena: int = 0
    cancelados: int = 0
    bloqueados: int = 0

    def somar(self, outro: "Contadores") -> None:
        self.recebidos += outro.recebidos
        self.aceitos += outro.aceitos
        self.descartados += outro.descartados
        self.rejeitados_anonimizacao.extend(outro.rejeitados_anonimizacao)
        self.falhas_parser += outro.falhas_parser
        self.quarentena += outro.quarentena
        self.cancelados += outro.cancelados
        self.bloqueados += outro.bloqueados


@dataclass(frozen=True)
class MetadadosCaderno:
    versao: int
    hash: str
    bytes: int | None = None


@dataclass
class LoteBruto:
    """Itens aceitos de uma página (fonte paginada) ou de um caderno inteiro (DJEN)."""

    itens: list[dict[str, Any]]
    caminho_bruto: str
    contadores: Contadores
    pagina: int | None = None
    total_fonte: int | None = None
    caderno: MetadadosCaderno | None = None


class UnidadeSemDados(Exception):
    """A fonte não tem nada para a unidade (ex.: dia sem caderno no DJEN)."""


class UnidadeNaoPronta(Exception):
    """A fonte ainda não terminou de publicar a unidade; tentar mais tarde."""


class ErroColeta(ErroSeguro):
    """Falha da coleta com mensagem segura para log e banco (sem conteúdo da fonte)."""


class Conector(Protocol):
    fonte: Fonte
    # Campos que podem chegar ao armazenamento bruto.
    lista_branca: frozenset[str]

    def planejar(self, tribunal: str, inicio: date, fim: date) -> list[UnidadeColeta]:
        """Unidades do período, da mais recente para a mais antiga."""
        ...

    def coletar(self, unidade: UnidadeColeta, checkpoint: Checkpoint) -> Iterator[LoteBruto]:
        """Lotes da unidade. Unidades paginadas começam em ``checkpoint.proxima_pagina``."""
        ...
