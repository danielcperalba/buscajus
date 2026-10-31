"""Upsert com versionamento, cancelamentos e bloqueios (F1-25 a F1-27; seção 4.5).

Para cada acórdão normalizado:

1. Bloqueio (``fonte + id_fonte`` ou ``numero_processo``) → não grava (F1-27); se a linha
   já existe, fica ``removido`` e perde ementa e decisão (F2-13). O arquivo bruto do lote é
   reescrito sem o item por quem chamou (orquestrador ou reprocessamento).
2. Linha nova → ``INSERT … ON CONFLICT (fonte, id_fonte) DO NOTHING``.
3. Mesmo ``hash_conteudo`` → só o estado (ativo, status, cancelamento, situação, coleta).
4. Hash diferente → a versão atual vai para ``acordao_historico`` e ``versao += 1``.
5. Situação: ``cancelado`` se a fonte indicar (F1-26), ``quarentena`` se o estado da fonte for
   anômalo (falha fechada: não indexa sem tratar como cancelamento) ou houver PII residual,
   ``duplicado`` se outra fonte de maior prioridade já tiver o mesmo acórdão ativo (F2-09),
   senão ``ativo``. ``removido`` e ``duplicado`` existentes não são desfeitos pela recoleta.
6. Dedup entre fontes (F2-09; ARCHITECTURE.md, seção 3.5): mesmo ``numero_processo`` e mesma
   data de referência (julgamento; na falta, publicação ou disponibilização) em outra fonte.
   Prioridade: API do próprio tribunal > DJEN. O de menor prioridade fica ``duplicado``, com
   ``duplicata_de`` apontando para o outro, seja ele o novo ou o que já estava no banco. Só um
   acórdão ``ativo`` faz o outro virar duplicado.

Os trechos vetoriais (``acordao_trecho``, Fase 3) serão apagados aqui sempre que a situação
deixar de ser ``ativo`` ou o conteúdo mudar (F3-09).
"""

from collections.abc import Mapping, Sequence
from datetime import date
from enum import StrEnum

from sqlalchemy import Connection, text

from buscajus.ingest.modelos import AcordaoNormalizado
from buscajus.ingest.remocao import apagar_conteudo

# Situações definidas fora da coleta, que a recoleta não desfaz.
SITUACOES_PERSISTENTES = ("removido", "duplicado")

# Dedup entre fontes (F2-09): ordem padrão, da maior para a menor prioridade. A API do
# tribunal vence o DJEN. Por tribunal, a ordem vem de ``prioridade_fontes`` (F7-05).
ORDEM_PADRAO: tuple[str, ...] = ("tjdft", "djen")
Prioridades = Mapping[str, Sequence[str]]
MOTIVO_DUPLICADO = "mesmo processo e data em fonte de maior prioridade"

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
    "relator_designado",
    "relator_designado_chave",
    "turma_recursal",
    "possui_inteiro_teor",
    "data_julgamento",
    "data_publicacao",
    "data_disponibilizacao",
    "local_publicacao",
    "ementa",
    "decisao",
    "link_oficial",
    "link_tribunal",
    "anonimizacao_versao",
    "anonimizacao_substituicoes",
    "hash_conteudo",
)
# Os três primeiros vêm da fonte; situação, motivo e duplicata são calculados.
_COLUNAS_ESTADO = (
    "ativo_fonte",
    "status_fonte",
    "data_cancelamento",
    "situacao",
    "motivo_situacao",
    "duplicata_de",
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


def ordem_das_fontes(tribunal: str, prioridades: Prioridades | None = None) -> tuple[str, ...]:
    """Fontes do tribunal da maior para a menor prioridade; as não listadas vêm por último."""
    configurada = tuple((prioridades or {}).get(tribunal.upper(), ()))
    return configurada + tuple(f for f in ORDEM_PADRAO if f not in configurada)


def _fontes(
    acordao: AcordaoNormalizado, prioridades: Prioridades | None, *, superiores: bool
) -> list[str]:
    ordem = ordem_das_fontes(acordao.tribunal, prioridades)
    if acordao.fonte not in ordem:
        return []
    propria = ordem.index(acordao.fonte)
    return list(ordem[:propria] if superiores else ordem[propria + 1 :])


def _data_referencia(acordao: AcordaoNormalizado) -> date | None:
    return acordao.data_julgamento or acordao.data_publicacao or acordao.data_disponibilizacao


def duplicata_superior(
    conexao: Connection, acordao: AcordaoNormalizado, prioridades: Prioridades | None = None
) -> int | None:
    """Id do acórdão ativo de fonte com maior prioridade que é o mesmo deste, se houver."""
    fontes = _fontes(acordao, prioridades, superiores=True)
    data = _data_referencia(acordao)
    if not fontes or data is None:
        return None
    id_superior: int | None = conexao.scalar(
        text("""
            SELECT id FROM acordao
            WHERE numero_processo = :numero AND data_referencia = :data
              AND fonte::text = ANY(:fontes) AND situacao = 'ativo'
            ORDER BY id LIMIT 1
        """),
        {"numero": acordao.numero_processo, "data": data, "fontes": fontes},
    )
    return id_superior


def marcar_duplicatas_inferiores(
    conexao: Connection,
    acordao: AcordaoNormalizado,
    acordao_id: int,
    prioridades: Prioridades | None = None,
) -> int:
    """Marca como ``duplicado`` os ativos de menor prioridade que são o mesmo acórdão."""
    fontes = _fontes(acordao, prioridades, superiores=False)
    data = _data_referencia(acordao)
    if not fontes or data is None:
        return 0
    return len(
        conexao.execute(
            text("""
                UPDATE acordao SET situacao = 'duplicado', motivo_situacao = :motivo,
                    duplicata_de = :id, atualizado_em = now()
                WHERE numero_processo = :numero AND data_referencia = :data
                  AND fonte::text = ANY(:fontes) AND situacao = 'ativo'
                RETURNING id
            """),
            {
                "numero": acordao.numero_processo,
                "data": data,
                "fontes": fontes,
                "id": acordao_id,
                "motivo": MOTIVO_DUPLICADO,
            },
        ).all()
    )


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
    prioridades: Prioridades | None = None,
) -> Resultado:
    chave = {"fonte": acordao.fonte, "id_fonte": acordao.id_fonte}
    if bloqueado(conexao, acordao):
        removidos = conexao.scalars(
            text("""
                UPDATE acordao SET situacao = 'removido', motivo_situacao = 'bloqueio',
                    atualizado_em = now()
                WHERE fonte = CAST(:fonte AS fonte) AND id_fonte = :id_fonte
                  AND situacao <> 'removido'
                RETURNING id
            """),
            chave,
        ).all()
        apagar_conteudo(conexao, list(removidos))
        return Resultado.BLOQUEADO

    situacao, motivo = situacao_coletada(cancelado, motivos_pii, anomalia=anomalia)
    duplicata_de = (
        duplicata_superior(conexao, acordao, prioridades) if situacao == "ativo" else None
    )
    if duplicata_de is not None:
        situacao, motivo = "duplicado", MOTIVO_DUPLICADO
    valores = acordao.colunas() | {
        "situacao": situacao,
        "motivo_situacao": motivo,
        "duplicata_de": duplicata_de,
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
            if situacao == "ativo":
                marcar_duplicatas_inferiores(conexao, acordao, inserido.id, prioridades)
            return Resultado.INSERIDO
        # Outra transação inseriu no meio do caminho: segue como atualização.
        return upsert(
            conexao,
            acordao,
            coleta_bruta_id=coleta_bruta_id,
            cancelado=cancelado,
            motivos_pii=motivos_pii,
            anomalia=anomalia,
            prioridades=prioridades,
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
    if situacao == "ativo" and atual.situacao not in SITUACOES_PERSISTENTES:
        marcar_duplicatas_inferiores(conexao, acordao, atual.id, prioridades)
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
