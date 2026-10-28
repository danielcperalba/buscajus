"""Mapeamento DJEN → ``AcordaoNormalizado`` (F1-23, ARCHITECTURE.md, seção 5.2).

Recebe um item do bruto filtrado (já anonimizado e com a lista branca aplicada).

- ``data_julgamento``: do cabeçalho do texto; ``data_publicacao``: nula (não é calculada);
  ``data_disponibilizacao``: do campo estruturado.
- ``link_oficial``: certidão do CNJ (``/api/v1/comunicacao/{hash}/certidao``), sempre https;
  ``link_tribunal``: campo ``link``.
- Número do processo: ``numero_processo`` (20 dígitos, presente em 100% no F1-01), mascarado
  aqui; ``numeroprocessocommascara`` não existe nos cadernos recentes. O número da célula
  "Processo" é conferido contra ``numero_processo``; na divergência, prevalece o estruturado.
- Classe: ``classe_nome``/``classe_codigo_cnj`` de ``nomeClasse``/``codigoClasse`` (filtros);
  ``classe_citacao`` da célula "Processo" (citação).
- ``link`` e ``idOrgao`` podem faltar; ``texto`` nulo vira falha de parser.
"""

import logging
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from buscajus.ingest.djen.parser import analisar, perfil_para, processo_confere
from buscajus.ingest.modelos import AcordaoNormalizado, ItemInvalido
from buscajus.ingest.processo import normalizar_numero
from buscajus.ingest.relator import normalizar_relator
from buscajus.ingest.texto import chave, decodificar

log = logging.getLogger(__name__)

URL_CERTIDAO = "https://comunicaapi.pje.jus.br/api/v1/comunicacao/{hash}/certidao"
FUSO = ZoneInfo("America/Sao_Paulo")


__all__ = ["ItemInvalido", "normalizar"]


def _texto_curto(valor: Any) -> str | None:
    if valor is None:
        return None
    texto = " ".join(decodificar(str(valor)).split())
    return texto or None


def _data(valor: Any) -> date | None:
    if not isinstance(valor, str) or len(valor) < 10:
        return None
    try:
        return date.fromisoformat(valor[:10])
    except ValueError:
        return None


def _data_hora(valor: Any) -> datetime | None:
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        quando = datetime.fromisoformat(valor.strip())
    except ValueError:
        return None
    return quando if quando.tzinfo else quando.replace(tzinfo=FUSO)


def _inteiro(valor: Any) -> int | None:
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, str) and valor.strip().isdigit():
        return int(valor.strip())
    return None


def normalizar(item: Mapping[str, Any]) -> AcordaoNormalizado:
    """Levanta ``FalhaParser``, ``NumeroProcessoInvalido`` ou ``ItemInvalido`` em falha."""
    id_fonte = item.get("id")
    hash_fonte = item.get("hash")
    if id_fonte in (None, "") or not isinstance(hash_fonte, str) or not hash_fonte:
        raise ItemInvalido("item sem id ou hash")

    analisado = analisar(str(item.get("texto") or ""), perfil_para(item.get("siglaTribunal")))
    numero = normalizar_numero(str(item.get("numero_processo") or ""))
    if not processo_confere(analisado.processo, numero.digitos):
        log.warning("número do cabeçalho difere do campo estruturado", extra={"id_fonte": id_fonte})

    relator = normalizar_relator(analisado.relator)
    orgao = _texto_curto(item.get("nomeOrgao"))
    link = _texto_curto(item.get("link"))
    return AcordaoNormalizado(
        fonte="djen",
        id_fonte=str(id_fonte),
        hash_fonte=hash_fonte,
        tipo_documento_fonte=_texto_curto(item.get("tipoDocumento")),
        tribunal=str(item.get("siglaTribunal") or "").strip().upper(),
        numero_processo=numero.digitos,
        numero_processo_mascara=numero.mascara,
        numero_processo_valido=numero.valido,
        orgao_julgador=orgao,
        id_orgao_fonte=_texto_curto(item.get("idOrgao")),
        classe_nome=_texto_curto(item.get("nomeClasse")) or analisado.classe,
        classe_citacao=analisado.classe or _texto_curto(item.get("nomeClasse")),
        classe_codigo_cnj=_inteiro(item.get("codigoClasse")),
        relator=relator.exibicao if relator else None,
        relator_chave=relator.chave if relator else None,
        turma_recursal="turma recursal" in chave(orgao or ""),
        data_julgamento=analisado.data_julgamento,
        data_publicacao=None,
        data_disponibilizacao=_data(item.get("data_disponibilizacao")),
        ementa=analisado.ementa,
        link_oficial=URL_CERTIDAO.format(hash=hash_fonte),
        link_tribunal=link if link and link.startswith(("http://", "https://")) else None,
        anonimizacao_versao=_texto_curto(item.get("anonimizacao_versao")),
        anonimizacao_substituicoes=_inteiro(item.get("anonimizacao_substituicoes")) or 0,
        ativo_fonte=item["ativo"] if isinstance(item.get("ativo"), bool) else None,
        status_fonte=_texto_curto(item.get("status")),
        data_cancelamento=_data_hora(item.get("data_cancelamento")),
    )
