"""Contagem de anomalias de estado da fonte e classe usada na citação (achados do F1-01).

- ``anomalias`` em ``caderno_djen`` e ``coleta_janela``: comunicações com estado da fonte não
  reconhecido (ex.: ``status`` diferente de "P"), que vão para a quarentena.
- ``acordao.classe_citacao``: a classe entre parênteses na célula "Processo" do cabeçalho,
  que difere de ``nomeClasse`` em 44% das ementas do TJPR. A citação usa esta; ``classe_nome``
  e ``classe_codigo_cnj`` (de ``nomeClasse``/``codigoClasse``) servem aos filtros.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE caderno_djen ADD COLUMN anomalias integer NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE coleta_janela ADD COLUMN anomalias integer NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE acordao ADD COLUMN classe_citacao text")


def downgrade() -> None:
    op.execute("ALTER TABLE acordao DROP COLUMN classe_citacao")
    op.execute("ALTER TABLE coleta_janela DROP COLUMN anomalias")
    op.execute("ALTER TABLE caderno_djen DROP COLUMN anomalias")
