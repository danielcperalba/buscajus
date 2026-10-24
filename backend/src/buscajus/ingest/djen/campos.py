"""Campos das comunicações do DJEN: lista branca, filtro de tipo e cancelamento."""

import unicodedata
from collections.abc import Collection, Mapping
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


def comunicacao_cancelada(item: Mapping[str, Any], status_cancelamento: Collection[str]) -> bool:
    """``ativo == false``, ``data_cancelamento`` preenchida ou ``status`` de cancelamento."""
    if item.get("ativo") is False:
        return True
    if item.get("data_cancelamento") not in (None, ""):
        return True
    status = item.get("status")
    return isinstance(status, str) and status.strip() in set(status_cancelamento)
