"""Reprocessamento a partir do bruto filtrado, sem rede (ARCHITECTURE.md, seção 3.2).

Refaz normalização, PII residual e upsert de cada caderno processado, lendo o arquivo
bruto da versão corrente. Serve para mudanças no parser. Itens bloqueados não voltam ao
banco (F1-27) e saem do arquivo bruto (F2-13). A camada 1 de anonimização não
pode ser refeita daqui, porque os destinatários nunca são gravados.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import Engine, text

from buscajus.ingest.bruto import ArmazenamentoBruto, caminho_caderno
from buscajus.ingest.conector import Contadores
from buscajus.ingest.processamento import ProcessadorAcordaos
from buscajus.ingest.remocao import CAMPO_ID, atualizar_coleta_bruta


@dataclass
class CadernoReprocessado:
    tribunal: str
    data: date
    itens: int
    contadores: Contadores


def reprocessar_cadernos(
    engine: Engine,
    bruto: ArmazenamentoBruto,
    processador: ProcessadorAcordaos,
    *,
    de: date,
    ate: date,
    tribunal: str | None = None,
    versao_parser: str,
) -> list[CadernoReprocessado]:
    with engine.connect() as conexao:
        cadernos = conexao.execute(
            text("""
                SELECT c.id, c.tribunal, c.data, c.versao, b.id AS bruta_id
                FROM caderno_djen c
                JOIN coleta_bruta b ON b.caderno_djen_id = c.id AND b.caminho_arquivo =
                    'djen/' || c.tribunal || '/' || to_char(c.data, 'YYYY-MM-DD')
                    || '/v' || c.versao || '.jsonl.gz'
                WHERE c.status = 'processado' AND c.data BETWEEN :de AND :ate
                  AND (CAST(:tribunal AS text) IS NULL OR c.tribunal = :tribunal)
                ORDER BY c.tribunal, c.data DESC
            """),
            {"de": de, "ate": ate, "tribunal": tribunal.upper() if tribunal else None},
        ).all()

    resultados = []
    for linha in cadernos:
        caminho = caminho_caderno(linha.tribunal, linha.data, linha.versao)
        itens = list(bruto.ler(caminho))
        with engine.begin() as conexao:
            contadores = processador.processar_itens(conexao, itens, linha.bruta_id)
            if contadores.ids_bloqueados:
                reescrito = bruto.reescrever_sem(
                    caminho, CAMPO_ID["djen"], contadores.ids_bloqueados
                )
                if reescrito is not None:
                    atualizar_coleta_bruta(conexao, reescrito)
            conexao.execute(
                text("""
                    UPDATE caderno_djen SET falhas_parser = :falhas, quarentena = :quarentena,
                        cancelados = :cancelados, bloqueados = :bloqueados,
                        anomalias = :anomalias,
                        versao_parser = :versao_parser
                    WHERE id = :id
                """),
                {
                    "id": linha.id,
                    "falhas": contadores.falhas_parser,
                    "quarentena": contadores.quarentena,
                    "cancelados": contadores.cancelados,
                    "bloqueados": contadores.bloqueados,
                    "anomalias": contadores.anomalias,
                    "versao_parser": versao_parser,
                },
            )
        resultados.append(CadernoReprocessado(linha.tribunal, linha.data, len(itens), contadores))
    return resultados
