"""Colunas do conector TJDFT (F2-06 a F2-08).

- ``acordao.relator_designado`` e ``relator_designado_chave``: relator para o acórdão
  (``nomeRelatorDesignado``), usado na citação como "Rel. p/ acórdão"; o relator original
  continua em ``relator``.
- ``acordao.local_publicacao``: veículo da publicação (``localDePublicacao``: "DJE" ou "PJe"),
  usado na citação.
- ``coleta_janela.descartados_segredo``: quantos registros vieram sob segredo de justiça e foram
  descartados antes de qualquer gravação (só a contagem; nenhum campo deles é gravado).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE acordao ADD COLUMN relator_designado text")
    op.execute("ALTER TABLE acordao ADD COLUMN relator_designado_chave text")
    op.execute("ALTER TABLE acordao ADD COLUMN local_publicacao text")
    op.execute(
        "ALTER TABLE coleta_janela ADD COLUMN descartados_segredo integer NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE coleta_janela DROP COLUMN descartados_segredo")
    op.execute("ALTER TABLE acordao DROP COLUMN local_publicacao")
    op.execute("ALTER TABLE acordao DROP COLUMN relator_designado_chave")
    op.execute("ALTER TABLE acordao DROP COLUMN relator_designado")
