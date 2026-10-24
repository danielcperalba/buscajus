"""Campos das comunicações do DJEN: lista branca, filtro de tipo e cancelamento."""

import unicodedata
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

TIPO_EMENTA = "Ementa de Acórdão"

# Campos que podem chegar ao bruto (ARCHITECTURE.md, seção 3.2), mais os metadados da
# anonimização. destinatarios, destinatarioadvogados e motivo_cancelamento (texto livre)
# ficam de fora.
LISTA_BRANCA = frozenset(
    {
        "id",
        "hash",
        "data_disponibilizacao",
        "siglaTribunal",
        "tipoDocumento",
        "nomeOrgao",
        "idOrgao",
        "nomeClasse",
        "codigoClasse",
        "numero_processo",
        "numeroprocessocommascara",
        "texto",
        "link",
        "ativo",
        "status",
        "data_cancelamento",
        "anonimizacao_versao",
        "anonimizacao_substituicoes",
    }
)


def normalizar_tipo(valor: Any) -> str:
    """``tipoDocumento`` comparável: NFC, sem espaços extras, sem diferença de caixa."""
    if not isinstance(valor, str):
        return ""
    return " ".join(unicodedata.normalize("NFC", valor).split()).casefold()


def tipo_aceito(item: Mapping[str, Any], tipos_aceitos: Collection[str]) -> bool:
    """Compara depois do *parse* do JSON (o caderno escapa acentos: ``Ac\\u00f3rd\\u00e3o``)."""
    return normalizar_tipo(item.get("tipoDocumento")) in {normalizar_tipo(t) for t in tipos_aceitos}


class EstadoFonte(StrEnum):
    ATIVA = "ativa"
    CANCELADA = "cancelada"
    # Estado que a regra não reconhece: não é indexado nem tratado como cancelamento.
    ANOMALA = "anomala"


@dataclass(frozen=True)
class RegraEstado:
    """Estado de uma comunicação a partir de ``ativo``, ``data_cancelamento`` e ``status``.

    F1-01 (3 cadernos, 347 mil comunicações): ``status = "P"`` e ``ativo = true`` em 100%;
    ``data_cancelamento`` sempre nula. Regra:

    - ``ativo == false`` ou ``data_cancelamento`` preenchida → cancelada;
    - ``status`` em ``status_cancelamento`` (vazio até haver valor confirmado) → cancelada;
    - ``ativo == true`` e ``status`` em ``status_ativos`` → ativa;
    - qualquer outra combinação → anômala (falha fechada).
    """

    status_ativos: frozenset[str] = frozenset({"P"})
    status_cancelamento: frozenset[str] = frozenset()

    @classmethod
    def de(cls, status_ativos: Iterable[str], status_cancelamento: Iterable[str]) -> "RegraEstado":
        return cls(frozenset(status_ativos), frozenset(status_cancelamento))

    def classificar(self, item: Mapping[str, Any]) -> EstadoFonte:
        if item.get("ativo") is False or item.get("data_cancelamento") not in (None, ""):
            return EstadoFonte.CANCELADA
        status = item.get("status")
        status = status.strip() if isinstance(status, str) else None
        if status in self.status_cancelamento:
            return EstadoFonte.CANCELADA
        if item.get("ativo") is True and status in self.status_ativos:
            return EstadoFonte.ATIVA
        return EstadoFonte.ANOMALA
