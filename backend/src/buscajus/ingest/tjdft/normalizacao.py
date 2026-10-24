"""Mapeamento TJDFT → ``AcordaoNormalizado`` (F2-08, ARCHITECTURE.md, seção 5.2).

Recebe um item do bruto filtrado (já anonimizado e com a lista branca aplicada).

- Datas: ``dataJulgamento`` e ``dataPublicacao`` vêm em UTC (``…T03:00:00.000Z``) e são
  convertidas para America/Sao_Paulo antes de virar data.
- Classe: ``codigoClasseCnj`` + nome pela tabela ``classe_cnj`` (TPU); o mesmo nome vai para
  a citação (``classe_citacao``). Código fora da TPU fica sem nome.
- Relator: ``nomeRelator`` em ``relator``; ``nomeRelatorDesignado`` em ``relator_designado``
  (a citação usa "Rel. p/ acórdão" com ele). Os nomes vêm em maiúsculas e viram *title case*.
- ``turma_recursal``: ``turmaRecursal = true`` ou ``subbase = "acordaos-tr"``.
- ``link_oficial``: ``https://jurisdf.tjdft.jus.br/acordaos/{uuid}``.
- ``local_publicacao``: ``localDePublicacao`` ("DJE" ou "PJe"), para a citação.
"""

import re
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from buscajus.ingest.modelos import AcordaoNormalizado, ItemInvalido
from buscajus.ingest.processo import normalizar_numero
from buscajus.ingest.relator import normalizar_relator
from buscajus.ingest.texto import decodificar, normalizar_espacos
from buscajus.ingest.tjdft.campos import SUBBASE_TURMA_RECURSAL

# Registrada em coleta_janela e coleta_bruta (versao_parser); mude quando o mapeamento mudar.
VERSAO_NORMALIZACAO = "tjdft-1"
URL_ACORDAO = "https://jurisdf.tjdft.jus.br/acordaos/{uuid}"
FUSO = ZoneInfo("America/Sao_Paulo")
TRIBUNAL = "TJDFT"
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def data_sao_paulo(valor: Any) -> date | None:
    """Data em America/Sao_Paulo de um instante ISO 8601 (sem fuso, entende-se UTC)."""
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        instante = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=UTC)
    return instante.astimezone(FUSO).date()


def _texto_curto(valor: Any) -> str | None:
    if not isinstance(valor, str):
        return None
    return " ".join(decodificar(valor).split()) or None


def _texto_longo(valor: Any) -> str | None:
    if not isinstance(valor, str):
        return None
    return normalizar_espacos(decodificar(valor)) or None


def _inteiro(valor: Any) -> int | None:
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, str) and valor.strip().isdigit():
        return int(valor.strip())
    return None


class NormalizadorTjdft:
    """``classes``: nomes da TPU por código (``classes_cnj.nomes_por_codigo``)."""

    def __init__(self, classes: Mapping[int, str]) -> None:
        self._classes = classes

    def __call__(self, item: Mapping[str, Any]) -> AcordaoNormalizado:
        """Levanta ``ItemInvalido`` ou ``NumeroProcessoInvalido`` em falha."""
        uuid = item.get("uuid")
        if not isinstance(uuid, str) or not _UUID.match(uuid):
            raise ItemInvalido("item sem uuid válido")
        ementa = _texto_longo(item.get("ementa"))
        if ementa is None:
            raise ItemInvalido("item sem ementa")

        numero = normalizar_numero(str(item.get("processo") or ""))
        relator = normalizar_relator(_texto_curto(item.get("nomeRelator")))
        designado = normalizar_relator(_texto_curto(item.get("nomeRelatorDesignado")))
        codigo_classe = _inteiro(item.get("codigoClasseCnj"))
        classe = self._classes.get(codigo_classe) if codigo_classe is not None else None
        turma_recursal = (
            item.get("turmaRecursal") is True or item.get("subbase") == SUBBASE_TURMA_RECURSAL
        )
        possui_inteiro_teor = item.get("possuiInteiroTeor")
        return AcordaoNormalizado(
            fonte="tjdft",
            id_fonte=uuid.lower(),
            identificador_fonte=_texto_curto(item.get("identificador")),
            tipo_documento_fonte=_texto_curto(item.get("base")),
            tribunal=TRIBUNAL,
            numero_processo=numero.digitos,
            numero_processo_mascara=numero.mascara,
            numero_processo_valido=numero.valido,
            orgao_julgador=_texto_curto(item.get("descricaoOrgaoJulgador")),
            classe_nome=classe,
            classe_codigo_cnj=codigo_classe,
            classe_citacao=classe,
            relator=relator.exibicao if relator else None,
            relator_chave=relator.chave if relator else None,
            relator_designado=designado.exibicao if designado else None,
            relator_designado_chave=designado.chave if designado else None,
            turma_recursal=turma_recursal,
            possui_inteiro_teor=possui_inteiro_teor
            if isinstance(possui_inteiro_teor, bool)
            else None,
            data_julgamento=data_sao_paulo(item.get("dataJulgamento")),
            data_publicacao=data_sao_paulo(item.get("dataPublicacao")),
            local_publicacao=_texto_curto(item.get("localDePublicacao")),
            ementa=ementa,
            decisao=_texto_longo(item.get("decisao")),
            link_oficial=URL_ACORDAO.format(uuid=uuid.lower()),
            anonimizacao_versao=_texto_curto(item.get("anonimizacao_versao")),
            anonimizacao_substituicoes=_inteiro(item.get("anonimizacao_substituicoes")) or 0,
        )
