"""Extensões (vector, unaccent, pg_trgm) e configuração de texto pt_unaccent.

Revision ID: 0001
Revises:
Create Date: 2026-10-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # Português sem acentos: "herança" e "heranca" geram o mesmo lexema.
    op.execute("CREATE TEXT SEARCH CONFIGURATION pt_unaccent (COPY = portuguese)")
    op.execute(
        "ALTER TEXT SEARCH CONFIGURATION pt_unaccent "
        "ALTER MAPPING FOR hword, hword_part, word WITH unaccent, portuguese_stem"
    )


def downgrade() -> None:
    op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS pt_unaccent")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS unaccent")
    op.execute("DROP EXTENSION IF EXISTS vector")
