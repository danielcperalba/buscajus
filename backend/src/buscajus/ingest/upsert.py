"""Upsert com versionamento, cancelamentos e bloqueios (F1-25 a F1-27; seção 4.5).

Para cada acórdão normalizado:

1. Bloqueio (``fonte + id_fonte`` ou ``numero_processo``) → não grava (F1-27); se a linha
   já existe, fica ``removido``.
2. Linha nova → ``INSERT … ON CONFLICT (fonte, id_fonte) DO NOTHING``.
3. Mesmo ``hash_conteudo`` → só o estado (ativo, status, cancelamento, situação, coleta).
4. Hash diferente → a versão atual vai para ``acordao_historico`` e ``versao += 1``.
5. Situação: ``cancelado`` se a fonte indicar (F1-26), ``quarentena`` se o estado da fonte for
   anômalo (falha fechada: não indexa sem tratar como cancelamento) ou houver PII residual,
   senão ``ativo``. ``removido`` e ``duplicado`` existentes não são desfeitos pela recoleta.

Os trechos vetoriais (``acordao_trecho``, Fase 3) serão apagados aqui sempre que a situação
deixar de ser ``ativo`` ou o conteúdo mudar (F3-09).
"""

from collections.abc import Sequence
from enum import StrEnum

from sqlalchemy import Connection, text

from buscajus.ingest.modelos import AcordaoNormalizado

# Situações definidas fora da coleta, que a recoleta não desfaz.
SITUACOES_PERSISTENTES = ("removido", "duplicado")

_COLUNAS_CONTEUDO = (
    "identificador_fonte",
    "hash_fonte",
    "tipo_documento_fonte",
    "numero_processo",
    "numero_processo_mascara",
    "numero_processo_valido",
    "tribunal",
    "orgao_julgador",
    "id_orgao_fonte",
    "classe_nome",
    "classe_codigo_cnj",
    "classe_citacao",
    "relator",
    "relator_chave",
    "turma_recursal",
    "possui_inteiro_teor",
    "data_julgamento",
    "data_publicacao",
    "data_disponibilizacao",
    "ementa",
    "decisao",
    "link_oficial",
    "link_tribunal",
    "anonimizacao_versao",
    "anonimizacao_substituicoes",
    "hash_conteudo",
)
# Os três primeiros vêm da fonte; situação e motivo são calculados.
_COLUNAS_ESTADO = (
    "ativo_fonte",
    "status_fonte",
    "data_cancelamento",
    "situacao",
    "motivo_situacao",
)


class Resultado(StrEnum):
    INSERIDO = "inserido"
    ESTADO_ATUALIZADO = "estado_atualizado"
    NOVA_VERSAO = "nova_versao"
    BLOQUEADO = "bloqueado"


MOTIVO_ANOMALIA = "estado da fonte não reconhecido"


def situacao_coletada(
    cancelado: bool, motivos_pii: Sequence[str], *, anomalia: bool = False
) -> tuple[str, str | None]:
    if cancelado:
        return "cancelado", "cancelado na fonte"
    if anomalia:
        return "quarentena", MOTIVO_ANOMALIA
    if motivos_pii:
        return "quarentena", "PII residual: " + ", ".join(motivos_pii)
    return "ativo", None


def bloqueado(conexao: Connection, acordao: AcordaoNormalizado) -> bool:
    return bool(
        conexao.scalar(
            text("""
                SELECT EXISTS (
                    SELECT 1 FROM bloqueio
                    WHERE (fonte = CAST(:fonte AS fonte) AND id_fonte = :id_fonte)
                       OR numero_processo = :numero
                )
            """),
            {
                "fonte": acordao.fonte,
                "id_fonte": acordao.id_fonte,
                "numero": acordao.numero_processo,
            },
        )
    )


def upsert(
    conexao: Connection,
    acordao: AcordaoNormalizado,
    *,
    coleta_bruta_id: int | None,
    cancelado: bool,
    motivos_pii: Sequence[str] = (),
    anomalia: bool = False,
) -> Resultado:
    chave = {"fonte": acordao.fonte, "id_fonte": acordao.id_fonte}
    if bloqueado(conexao, acordao):
        conexao.execute(
            text("""
                UPDATE acordao SET situacao = 'removido', motivo_situacao = 'bloqueio',
                    atualizado_em = now()
                WHERE fonte = CAST(:fonte AS fonte) AND id_fonte = :id_fonte
                  AND situacao <> 'removido'
            """),
            chave,
        )
        return Resultado.BLOQUEADO

    situacao, motivo = situacao_coletada(cancelado, motivos_pii, anomalia=anomalia)
    valores = acordao.colunas() | {
        "situacao": situacao,
        "motivo_situacao": motivo,
        "coleta_bruta_id": coleta_bruta_id,
    }
    atual = conexao.execute(
        text("""
            SELECT id, hash_conteudo, situacao::text AS situacao FROM acordao
            WHERE fonte = CAST(:fonte AS fonte) AND id_fonte = :id_fonte
            FOR UPDATE
        """),
        chave,
    ).one_or_none()

    if atual is None:
        insercao = ("fonte", "id_fonte", *_COLUNAS_CONTEUDO, *_COLUNAS_ESTADO, "coleta_bruta_id")
        inserido = conexao.execute(
            text(f"""
                INSERT INTO acordao ({", ".join(insercao)})
                VALUES ({", ".join(_valor(c) for c in insercao)})
                ON CONFLICT (fonte, id_fonte) DO NOTHING
                RETURNING id
            """),  # noqa: S608 (interpola só nomes de colunas fixos)
            valores,
        ).one_or_none()
        if inserido is not None:
            return Resultado.INSERIDO
        # Outra transação inseriu no meio do caminho: segue como atualização.
        return upsert(
            conexao,
            acordao,
            coleta_bruta_id=coleta_bruta_id,
            cancelado=cancelado,
            motivos_pii=motivos_pii,
            anomalia=anomalia,
        )

    mudou = atual.hash_conteudo != acordao.hash_conteudo
    if mudou:
        conexao.execute(
            text("""
                INSERT INTO acordao_historico (acordao_id, versao, snapshot)
                SELECT id, versao, to_jsonb(a) - 'busca_tsv' - 'data_referencia'
                FROM acordao a WHERE id = :id
            """),
            {"id": atual.id},
        )
    colunas: tuple[str, ...] = (*_COLUNAS_CONTEUDO, "coleta_bruta_id") if mudou else ()
    # removido/duplicado: a situação e o motivo atuais ficam.
    estado = _COLUNAS_ESTADO[:3] if atual.situacao in SITUACOES_PERSISTENTES else _COLUNAS_ESTADO
    atribuicoes = [f"{c} = {_valor(c)}" for c in (*colunas, *estado)]
    conexao.execute(
        text(f"""
            UPDATE acordao SET {", ".join(atribuicoes)},
                versao = versao + {1 if mudou else 0},
                ultima_coleta_em = now(),
                atualizado_em = now()
            WHERE id = :id
        """),  # noqa: S608 (interpola só nomes de colunas fixos)
        valores | {"id": atual.id},
    )
    return Resultado.NOVA_VERSAO if mudou else Resultado.ESTADO_ATUALIZADO


def _valor(coluna: str) -> str:
    if coluna == "fonte":
        return "CAST(:fonte AS fonte)"
    if coluna == "situacao":
        return "CAST(:situacao AS situacao_acordao)"
    return f":{coluna}"


def marcar_situacao(conexao: Connection, acordao_id: int, situacao: str, motivo: str) -> None:
    """Usado pela checagem pontual de acórdãos que sumiram numa nova versão do caderno."""
    conexao.execute(
        text("""
            UPDATE acordao SET situacao = CAST(:situacao AS situacao_acordao),
                motivo_situacao = :motivo, atualizado_em = now()
            WHERE id = :id AND situacao NOT IN ('removido', 'duplicado')
        """),
        {"id": acordao_id, "situacao": situacao, "motivo": motivo},
    )


def marcar_cancelado(conexao: Connection, acordao_id: int, motivo: str) -> None:
    marcar_situacao(conexao, acordao_id, "cancelado", motivo)
