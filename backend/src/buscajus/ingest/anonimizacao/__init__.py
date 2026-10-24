"""Anonimização obrigatória antes de qualquer gravação (ARCHITECTURE.md, seção 6.3).

Este módulo define o contrato usado pelos conectores. A implementação (camadas 1 e 2,
mascaramento de CPF, invariante e lista branca) fica em ``anonimizacao.pipeline``.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Rejeicao:
    """Falha segura: o item não é gravado. Guarda só o id e um motivo sem conteúdo."""

    id_comunicacao: str
    motivo: str


class Anonimizador(Protocol):
    def __call__(self, item: Mapping[str, Any]) -> dict[str, Any] | Rejeicao:
        """Recebe a comunicação aceita, ainda com os destinatários (só em memória).

        Devolve o item anonimizado e com a lista branca aplicada, pronto para o bruto,
        ou :class:`Rejeicao` se não for possível garantir a anonimização.
        """
        ...
