"""Etapas depois do bruto: normalização, PII residual e upsert, na transação do lote."""

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from sqlalchemy import Connection

from buscajus.ingest.conector import Contadores, LoteBruto
from buscajus.ingest.djen.campos import EstadoFonte
from buscajus.ingest.djen.normalizacao import ItemInvalido
from buscajus.ingest.djen.parser import FalhaParser
from buscajus.ingest.modelos import AcordaoNormalizado
from buscajus.ingest.pii import verificar_pii
from buscajus.ingest.processo import NumeroProcessoInvalido
from buscajus.ingest.upsert import Resultado, upsert

FALHAS_DE_PARSER = (FalhaParser, NumeroProcessoInvalido, ItemInvalido)


class ProcessadorAcordaos:
    def __init__(
        self,
        normalizar: Callable[[Mapping[str, Any]], AcordaoNormalizado],
        estado: Callable[[Mapping[str, Any]], EstadoFonte],
    ) -> None:
        self._normalizar = normalizar
        self._estado = estado

    def __call__(self, conexao: Connection, lote: LoteBruto, coleta_bruta_id: int) -> Contadores:
        return self.processar_itens(conexao, lote.itens, coleta_bruta_id)

    def processar_itens(
        self, conexao: Connection, itens: Iterable[Mapping[str, Any]], coleta_bruta_id: int | None
    ) -> Contadores:
        contadores = Contadores()
        for item in itens:
            try:
                acordao = self._normalizar(item)
            except FALHAS_DE_PARSER:
                # O item continua no bruto filtrado, para depurar e reprocessar.
                contadores.falhas_parser += 1
                continue
            estado = self._estado(item)
            cancelado = estado is EstadoFonte.CANCELADA
            anomalia = estado is EstadoFonte.ANOMALA
            motivos = verificar_pii(acordao.ementa)
            resultado = upsert(
                conexao,
                acordao,
                coleta_bruta_id=coleta_bruta_id,
                cancelado=cancelado,
                motivos_pii=motivos,
                anomalia=anomalia,
            )
            if resultado is Resultado.BLOQUEADO:
                contadores.bloqueados += 1
            elif cancelado:
                contadores.cancelados += 1
            elif anomalia:
                contadores.anomalias += 1
            elif motivos:
                contadores.quarentena += 1
        return contadores
