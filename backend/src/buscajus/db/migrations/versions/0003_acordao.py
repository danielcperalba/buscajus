"""Tabelas acordao e acordao_historico (ARCHITECTURE.md, seção 4.2).

Não há coluna para partes, advogados ou destinatários; um teste de esquema garante isso.
A tabela de vetores (acordao_trecho) só entra na Fase 3, com a dimensão do modelo escolhido.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE situacao_acordao AS ENUM "
        "('ativo', 'cancelado', 'removido', 'quarentena', 'duplicado')"
    )
    op.execute("""
        CREATE TABLE acordao (
            id                          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

            -- origem
            fonte                       fonte        NOT NULL,
            id_fonte                    text         NOT NULL,
            identificador_fonte         text,
            hash_fonte                  text,
            tipo_documento_fonte        text,

            -- processo
            numero_processo             char(20)     NOT NULL,
            numero_processo_mascara     text         NOT NULL,
            numero_processo_valido      boolean      NOT NULL,
            tribunal                    text         NOT NULL,

            -- julgamento
            orgao_julgador              text,
            id_orgao_fonte              text,
            classe_nome                 text,
            classe_codigo_cnj           integer,
            relator                     text,
            relator_chave               text,
            turma_recursal              boolean,
            possui_inteiro_teor         boolean,

            -- datas
            data_julgamento             date,
            data_publicacao             date,
            data_disponibilizacao       date,
            data_referencia             date GENERATED ALWAYS AS
                (coalesce(data_julgamento, data_publicacao, data_disponibilizacao)) STORED,

            -- conteúdo
            ementa                      text         NOT NULL,
            decisao                     text,
            link_oficial                text         NOT NULL,
            link_tribunal               text,

            -- anonimização (nunca guarda os nomes substituídos)
            anonimizacao_versao         text,
            anonimizacao_substituicoes  smallint     NOT NULL DEFAULT 0,

            -- estado
            situacao                    situacao_acordao NOT NULL DEFAULT 'ativo',
            ativo_fonte                 boolean,
            status_fonte                text,
            data_cancelamento           timestamptz,
            duplicata_de                bigint       REFERENCES acordao(id),
            motivo_situacao             text,

            -- versionamento e coleta
            hash_conteudo               text         NOT NULL,
            versao                      integer      NOT NULL DEFAULT 1,
            coleta_bruta_id             bigint       REFERENCES coleta_bruta(id),
            primeira_coleta_em          timestamptz  NOT NULL DEFAULT now(),
            ultima_coleta_em            timestamptz  NOT NULL DEFAULT now(),
            atualizado_em               timestamptz  NOT NULL DEFAULT now(),

            -- full-text
            busca_tsv                   tsvector GENERATED ALWAYS AS (
                setweight(to_tsvector('pt_unaccent', coalesce(ementa, '')), 'A') ||
                setweight(to_tsvector('pt_unaccent', coalesce(classe_nome, '')), 'B') ||
                setweight(to_tsvector('pt_unaccent', coalesce(orgao_julgador, '')), 'C')
            ) STORED,

            UNIQUE (fonte, id_fonte)
        )
    """)
    op.execute(
        "CREATE INDEX acordao_tsv_idx ON acordao USING gin (busca_tsv) WHERE situacao = 'ativo'"
    )
    op.execute("CREATE INDEX acordao_processo_idx ON acordao (numero_processo)")
    op.execute("CREATE INDEX acordao_processo_pref ON acordao (numero_processo bpchar_pattern_ops)")
    op.execute(
        "CREATE INDEX acordao_filtros_idx ON acordao (tribunal, data_referencia DESC) "
        "WHERE situacao = 'ativo'"
    )
    op.execute("CREATE INDEX acordao_classe_idx ON acordao (classe_codigo_cnj)")
    op.execute("CREATE INDEX acordao_orgao_idx ON acordao (tribunal, orgao_julgador)")
    op.execute(
        "CREATE INDEX acordao_relator_trgm ON acordao USING gin (relator_chave gin_trgm_ops)"
    )

    op.execute("""
        CREATE TABLE acordao_historico (
            id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            acordao_id      bigint      NOT NULL REFERENCES acordao(id) ON DELETE CASCADE,
            versao          integer     NOT NULL,
            snapshot        jsonb       NOT NULL,
            substituido_em  timestamptz NOT NULL DEFAULT now(),
            UNIQUE (acordao_id, versao)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE acordao_historico")
    op.execute("DROP TABLE acordao")
    op.execute("DROP TYPE situacao_acordao")
