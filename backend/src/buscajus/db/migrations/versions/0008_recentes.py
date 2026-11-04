"""Índice da lista de acórdãos recentes (F5-13).

``GET /api/v1/acordaos/recentes`` ordena os acórdãos ativos pela data de publicação, a mesma
dos resultados: ``data_publicacao`` (TJDFT) ou ``data_disponibilizacao`` (DJEN), com desempate
por ``id``. O índice parcial sobre essa expressão, na mesma ordem, serve a consulta (e a
contagem limitada) sem varrer nem ordenar a tabela. A expressão tem de ser idêntica à de
``busca.servico.ORDEM_RECENTES``.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX acordao_recentes_idx ON acordao "
        "((coalesce(data_publicacao, data_disponibilizacao)) DESC NULLS LAST, id DESC) "
        "WHERE situacao = 'ativo'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX acordao_recentes_idx")
