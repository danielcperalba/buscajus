"""Tabela classe_cnj, carregada da TPU do CNJ (F2-03).

A API do TJDFT devolve só ``codigoClasseCnj``; o nome da classe vem daqui. A carga lê o
arquivo versionado ``buscajus/db/dados/tpu_classes.json`` (com a data de referência da TPU).
Uma atualização da TPU é um arquivo novo mais uma migração que chame ``carregar_tpu``.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

from buscajus.db.classes_cnj import carregar_tpu

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE classe_cnj (
            codigo          integer PRIMARY KEY,
            nome            text    NOT NULL,
            codigo_pai      integer,
            sigla           text,
            ativa           boolean NOT NULL,
            tpu_referencia  date    NOT NULL  -- data de referência da versão da TPU
        )
    """)
    carregar_tpu(op.get_bind())


def downgrade() -> None:
    op.execute("DROP TABLE classe_cnj")
