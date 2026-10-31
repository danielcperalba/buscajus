"""Campos dos registros do TJDFT: lista branca do bruto e filtro de segredo e base (F2-06).

Regra defensiva: só passa o registro cujo ``segredoJustica`` seja exatamente ``false`` e cuja
``base`` seja ``acordaos``. Qualquer outro valor de segredo (``true``, ausente, ``null``,
número ou texto) é tratado como segredo, para que uma mudança de formato da API nunca deixe
passar um registro sigiloso. Turma recursal (``subbase = "acordaos-tr"``) não é critério.
"""

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

BASE = "acordaos"
SUBBASE_TURMA_RECURSAL = "acordaos-tr"

# Campos que podem chegar ao bruto (ARCHITECTURE.md, seção 3.3), mais os metadados da
# anonimização. Ficam de fora, entre outros: inteiroTeorHtml, marcadores,
# jurisprudenciaEmFoco, sequencial, relatorAtivo, uf, codigoSistjOrgaoJulgador e as
# agregações da resposta.
LISTA_BRANCA = frozenset(
    {
        "uuid",
        "identificador",
        "base",
        "subbase",
        "turmaRecursal",
        "processo",
        "nomeRelator",
        "nomeRelatorDesignado",
        "nomeRevisor",
        "descricaoOrgaoJulgador",
        "codigoClasseCnj",
        "dataJulgamento",
        "dataPublicacao",
        "localDePublicacao",
        "ementa",
        "decisao",
        "segredoJustica",
        "possuiInteiroTeor",
        "versao",
        "anonimizacao_versao",
        "anonimizacao_substituicoes",
    }
)


class Descarte(StrEnum):
    SEGREDO = "segredo"
    BASE = "base"


def descarte(registro: Mapping[str, Any]) -> Descarte | None:
    """Motivo para descartar o registro antes de qualquer gravação, ou ``None`` se passa."""
    if registro.get("segredoJustica") is not False:
        return Descarte.SEGREDO
    if registro.get("base") != BASE:
        return Descarte.BASE
    return None


def aplicar_lista_branca(registro: Mapping[str, Any]) -> dict[str, Any]:
    return {campo: valor for campo, valor in registro.items() if campo in LISTA_BRANCA}
