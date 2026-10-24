"""Logs estruturados em JSON, uma linha por evento.

Política (ARCHITECTURE.md, seção 6.2): nunca registrar o conteúdo de comunicações,
ementas, nomes de destinatários, URLs temporárias nem termos de busca completos.
Registre identificadores e contagens, passando-os em ``extra``.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Atributos que todo LogRecord tem; o que sobrar veio de ``extra``.
_ATRIBUTOS_PADRAO = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class FormatadorJson(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        evento: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "nivel": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for chave, valor in vars(record).items():
            if chave not in _ATRIBUTOS_PADRAO:
                evento[chave] = valor
        if record.exc_info:
            evento["excecao"] = self.formatException(record.exc_info)
        return json.dumps(evento, ensure_ascii=False, default=str)


def configurar_logging(nivel: str = "INFO") -> None:
    manipulador = logging.StreamHandler(sys.stdout)
    manipulador.setFormatter(FormatadorJson())
    raiz = logging.getLogger()
    raiz.handlers[:] = [manipulador]
    raiz.setLevel(nivel)
    # O log de acesso do uvicorn inclui a query string, que pode conter a busca do usuário.
    logging.getLogger("uvicorn.access").disabled = True
