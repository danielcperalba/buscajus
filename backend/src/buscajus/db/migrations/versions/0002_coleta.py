"""Tabelas de coleta: caderno_djen, coleta_janela, coleta_bruta e tarefa.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE TYPE fonte AS ENUM ('djen', 'tjdft')")

    # Uma linha por caderno diário do DJEN (tribunal + dia). O caderno é a unidade de
    # coleta não paginada: interrompido, é reprocessado inteiro (ARCHITECTURE.md, seção 3.1).
    op.execute("""
        CREATE TABLE caderno_djen (
            id                       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tribunal                 text        NOT NULL,
            data                     date        NOT NULL,
            status                   text        NOT NULL DEFAULT 'pendente'
                CHECK (status IN ('pendente', 'em_andamento', 'processado', 'sem_caderno', 'erro')),
            versao                   integer,
            hash                     text,
            bytes                    bigint,
            total_fonte              integer,
            comunicacoes_lidas       integer     NOT NULL DEFAULT 0,
            acordaos_aceitos         integer     NOT NULL DEFAULT 0,
            -- Só os ids das comunicações recusadas pela falha segura, nunca o conteúdo.
            rejeitados_anonimizacao  text[]      NOT NULL DEFAULT '{}',
            falhas_parser            integer     NOT NULL DEFAULT 0,
            quarentena               integer     NOT NULL DEFAULT 0,
            cancelados               integer     NOT NULL DEFAULT 0,
            bloqueados               integer     NOT NULL DEFAULT 0,
            respostas_429            integer     NOT NULL DEFAULT 0,
            tentativas               integer     NOT NULL DEFAULT 0,
            ultimo_erro              text,
            versao_parser            text,
            verificado_em            timestamptz,
            iniciado_em              timestamptz,
            processado_em            timestamptz,
            UNIQUE (tribunal, data)
        )
    """)

    # Checkpoint das fontes paginadas (TJDFT): a unidade continua da página seguinte.
    op.execute("""
        CREATE TABLE coleta_janela (
            id                       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            fonte                    fonte       NOT NULL,
            tribunal                 text        NOT NULL,
            data_inicio              date        NOT NULL,
            data_fim                 date        NOT NULL,
            status                   text        NOT NULL DEFAULT 'pendente'
                CHECK (status IN ('pendente', 'em_andamento', 'concluida', 'erro')),
            total_fonte              integer,
            ultima_pagina            integer,
            itens_recebidos          integer     NOT NULL DEFAULT 0,
            itens_aceitos            integer     NOT NULL DEFAULT 0,
            itens_descartados        integer     NOT NULL DEFAULT 0,
            rejeitados_anonimizacao  text[]      NOT NULL DEFAULT '{}',
            falhas_parser            integer     NOT NULL DEFAULT 0,
            quarentena               integer     NOT NULL DEFAULT 0,
            cancelados               integer     NOT NULL DEFAULT 0,
            bloqueados               integer     NOT NULL DEFAULT 0,
            respostas_429            integer     NOT NULL DEFAULT 0,
            tentativas               integer     NOT NULL DEFAULT 0,
            ultimo_erro              text,
            versao_parser            text,
            iniciada_em              timestamptz,
            concluida_em             timestamptz,
            UNIQUE (fonte, tribunal, data_inicio, data_fim),
            CHECK (data_inicio <= data_fim)
        )
    """)

    # Metadados de cada arquivo bruto filtrado (só itens aceitos e anonimizados).
    op.execute("""
        CREATE TABLE coleta_bruta (
            id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            fonte             fonte       NOT NULL,
            caderno_djen_id   bigint      REFERENCES caderno_djen(id),
            coleta_janela_id  bigint      REFERENCES coleta_janela(id),
            pagina            integer,
            caminho_arquivo   text        NOT NULL UNIQUE,  -- relativo ao diretório raw
            sha256            text        NOT NULL,
            bytes             bigint      NOT NULL,
            itens             integer     NOT NULL,
            recebida_em       timestamptz NOT NULL DEFAULT now(),
            versao_parser     text,
            CHECK ((caderno_djen_id IS NULL) <> (coleta_janela_id IS NULL))
        )
    """)

    # Fila simples, consumida com SELECT … FOR UPDATE SKIP LOCKED.
    op.execute("""
        CREATE TABLE tarefa (
            id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tipo           text        NOT NULL,
            payload        jsonb       NOT NULL DEFAULT '{}',
            status         text        NOT NULL DEFAULT 'pendente'
                CHECK (status IN ('pendente', 'em_andamento', 'concluida', 'erro')),
            agendada_para  timestamptz NOT NULL DEFAULT now(),
            tentativas     integer     NOT NULL DEFAULT 0,
            ultimo_erro    text,
            criada_em      timestamptz NOT NULL DEFAULT now(),
            iniciada_em    timestamptz,
            concluida_em   timestamptz
        )
    """)
    op.execute("CREATE INDEX tarefa_fila_idx ON tarefa (agendada_para) WHERE status = 'pendente'")


def downgrade() -> None:
    op.execute("DROP TABLE tarefa")
    op.execute("DROP TABLE coleta_bruta")
    op.execute("DROP TABLE coleta_janela")
    op.execute("DROP TABLE caderno_djen")
    op.execute("DROP TYPE fonte")
