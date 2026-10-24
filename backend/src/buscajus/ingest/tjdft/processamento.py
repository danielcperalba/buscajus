"""Etapas depois do bruto para o TJDFT, na transação do lote (F2-07, F2-08).

Os itens aceitos seguem o caminho comum (normalização, PII residual, upsert). O TJDFT não
tem cancelamento na fonte: todo item aceito está ativo.

Segredo superveniente (F2-07): um registro já indexado que volta com segredo de justiça é
descartado pelo conector antes de qualquer gravação, e só o uuid chega aqui, em memória
(``LoteBruto.ids_segredo``). O acórdão correspondente é removido pela regra geral do F2-13
(``ingest.remocao``): bloqueio, ``removido``, ementa e decisão apagadas no banco e no
histórico, trechos apagados e arquivos brutos reescritos sem ele. A recoleta não o reinsere.
"""

import logging
from collections.abc import Mapping
from typing import Any

from sqlalchemy import Connection, text

from buscajus.ingest.bruto import ArmazenamentoBruto
from buscajus.ingest.conector import Contadores, LoteBruto
from buscajus.ingest.djen.campos import EstadoFonte
from buscajus.ingest.processamento import ProcessadorAcordaos
from buscajus.ingest.remocao import remover
from buscajus.ingest.tjdft.normalizacao import NormalizadorTjdft

log = logging.getLogger(__name__)

MOTIVO_SEGREDO = "segredo de justiça superveniente"


def _sempre_ativo(_item: Mapping[str, Any]) -> EstadoFonte:
    return EstadoFonte.ATIVA


def remover_por_segredo(conexao: Connection, bruto: ArmazenamentoBruto, uuids: list[str]) -> int:
    """Remove (F2-13) os acórdãos já indexados que passaram a vir sob segredo."""
    if not uuids:
        return 0
    ids = conexao.scalars(
        text("SELECT id FROM acordao WHERE fonte = 'tjdft' AND id_fonte = ANY(:uuids)"),
        {"uuids": [u.lower() for u in uuids]},
    ).all()
    return len(remover(conexao, bruto, ids, MOTIVO_SEGREDO))


class ProcessadorTjdft:
    def __init__(self, normalizar: NormalizadorTjdft, bruto: ArmazenamentoBruto) -> None:
        self._comum = ProcessadorAcordaos(normalizar, _sempre_ativo)
        self._bruto = bruto

    def __call__(self, conexao: Connection, lote: LoteBruto, coleta_bruta_id: int) -> Contadores:
        removidos = remover_por_segredo(conexao, self._bruto, lote.ids_segredo)
        if removidos:
            log.info("acórdãos removidos por segredo superveniente", extra={"removidos": removidos})
        return self._comum.processar_itens(conexao, lote.itens, coleta_bruta_id)
