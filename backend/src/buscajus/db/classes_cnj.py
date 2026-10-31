"""Tabela ``classe_cnj``: classes processuais da TPU do CNJ (F2-03, ARCHITECTURE.md, seção 3.3).

A API do TJDFT devolve só ``codigoClasseCnj``; o nome da classe (filtros e citação) vem desta
tabela, carregada do arquivo versionado ``dados/tpu_classes.json``. O arquivo é gerado por
``backend/scripts/atualizar_tpu.py`` a partir da API pública da TPU e traz a data de
referência da versão. A TPU é tabela de referência pública, não fonte de jurisprudência.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, text

ARQUIVO_TPU = Path(__file__).parent / "dados" / "tpu_classes.json"


@dataclass(frozen=True)
class Tpu:
    data_referencia: date
    classes: tuple[Mapping[str, Any], ...]


def ler_tpu(arquivo: Path = ARQUIVO_TPU) -> Tpu:
    conteudo = json.loads(arquivo.read_text(encoding="utf-8"))
    return Tpu(date.fromisoformat(conteudo["data_referencia"]), tuple(conteudo["classes"]))


def carregar_tpu(conexao: Connection, arquivo: Path = ARQUIVO_TPU) -> int:
    """Insere ou atualiza as classes do arquivo. Devolve quantas foram carregadas.

    Classes que saíram da TPU não são apagadas (acórdãos antigos podem usá-las).
    """
    tpu = ler_tpu(arquivo)
    conexao.execute(
        text("""
            INSERT INTO classe_cnj (codigo, nome, codigo_pai, sigla, ativa, tpu_referencia)
            VALUES (:codigo, :nome, :codigo_pai, :sigla, :ativa, :referencia)
            ON CONFLICT (codigo) DO UPDATE SET
                nome = excluded.nome, codigo_pai = excluded.codigo_pai,
                sigla = excluded.sigla, ativa = excluded.ativa,
                tpu_referencia = excluded.tpu_referencia
        """),
        [dict(classe) | {"referencia": tpu.data_referencia} for classe in tpu.classes],
    )
    return len(tpu.classes)


def nomes_por_codigo(conexao: Connection) -> dict[int, str]:
    """Todas as classes (são algumas centenas), para resolver o nome sem consulta por item."""
    linhas = conexao.execute(text("SELECT codigo, nome FROM classe_cnj")).all()
    return {linha.codigo: linha.nome for linha in linhas}
