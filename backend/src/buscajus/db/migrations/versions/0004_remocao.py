"""Tabelas pedido_remocao e bloqueio (ARCHITECTURE.md, seções 4.4 e 6.5).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # O e-mail do solicitante (contato) é apagado depois da resolução e do prazo de retenção.
    op.execute("""
        CREATE TABLE pedido_remocao (
            id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            acordao_id       bigint      REFERENCES acordao(id),
            numero_processo  text,
            motivo           text        NOT NULL,
            contato          text,
            status           text        NOT NULL DEFAULT 'pendente'
                CHECK (status IN ('pendente', 'aceito', 'rejeitado')),
            decisao          text,
            criado_em        timestamptz NOT NULL DEFAULT now(),
            resolvido_em     timestamptz,
            CHECK (acordao_id IS NOT NULL OR numero_processo IS NOT NULL)
        )
    """)

    # Consultado no upsert para que a recoleta não reinsira conteúdo removido.
    op.execute("""
        CREATE TABLE bloqueio (
            id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            fonte              fonte,
            id_fonte           text,
            numero_processo    char(20),
            motivo             text        NOT NULL,
            pedido_remocao_id  bigint      REFERENCES pedido_remocao(id),
            criado_em          timestamptz NOT NULL DEFAULT now(),
            CHECK ((fonte IS NULL) = (id_fonte IS NULL)),
            CHECK (id_fonte IS NOT NULL OR numero_processo IS NOT NULL)
        )
    """)
    op.execute(
        "CREATE INDEX bloqueio_fonte_idx ON bloqueio (fonte, id_fonte) WHERE id_fonte IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX bloqueio_processo_idx ON bloqueio (numero_processo) "
        "WHERE numero_processo IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE bloqueio")
    op.execute("DROP TABLE pedido_remocao")
