"""Etapas depois do bruto para o TJDFT, na transação do lote (F2-07, F2-08).

Os itens aceitos seguem o caminho comum (normalização, PII residual, upsert). O TJDFT não
tem cancelamento na fonte: todo item aceito está ativo.

Segredo superveniente (F2-07): um registro já indexado que volta com segredo de justiça é
descartado pelo conector antes de qualquer gravação, e só o uuid chega aqui, em memória
(``LoteBruto.ids_segredo``). O acórdão correspondente vira ``removido``; os trechos vetoriais
(Fase 3) serão apagados aqui também (F3-09). ``removido`` não é desfeito pela recoleta.
"""

import logging
from collections.abc import Mapping
from typing import Any

from sqlalchemy import Connection, text

from buscajus.ingest.conector import Contadores, LoteBruto
from buscajus.ingest.djen.campos import EstadoFonte
from buscajus.ingest.processamento import ProcessadorAcordaos
from buscajus.ingest.tjdft.normalizacao import NormalizadorTjdft

log = logging.getLogger(__name__)

MOTIVO_SEGREDO = "segredo de justiça superveniente"


def _sempre_ativo(_item: Mapping[str, Any]) -> EstadoFonte:
    return EstadoFonte.ATIVA


def remover_por_segredo(conexao: Connection, uuids: list[str]) -> int:
    """Marca como ``removido`` os acórdãos do TJDFT que passaram a vir sob segredo."""
    if not uuids:
        return 0
    removidos = conexao.execute(
        text("""
            UPDATE acordao SET situacao = 'removido', motivo_situacao = :motivo,
                atualizado_em = now()
            WHERE fonte = 'tjdft' AND id_fonte = ANY(:uuids) AND situacao <> 'removido'
            RETURNING id
        """),
        {"motivo": MOTIVO_SEGREDO, "uuids": [u.lower() for u in uuids]},
    ).all()
    return len(removidos)


class ProcessadorTjdft:
    def __init__(self, normalizar: NormalizadorTjdft) -> None:
        self._comum = ProcessadorAcordaos(normalizar, _sempre_ativo)

    def __call__(self, conexao: Connection, lote: LoteBruto, coleta_bruta_id: int) -> Contadores:
        removidos = remover_por_segredo(conexao, lote.ids_segredo)
        if removidos:
            log.info("acórdãos removidos por segredo superveniente", extra={"removidos": removidos})
        return self._comum.processar_itens(conexao, lote.itens, coleta_bruta_id)
