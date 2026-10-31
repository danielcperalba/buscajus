"""Remoção de acórdãos com apagamento do conteúdo (F2-13; ARCHITECTURE.md, seção 4.5).

Regra geral para todo acórdão que vira ``removido`` (segredo de justiça superveniente no
TJDFT, F2-07; pedido de remoção aceito, F4-12):

1. ``bloqueio`` por fonte + id, para que nenhuma recoleta nem reprocessamento o reinsira
   (o upsert consulta o bloqueio, F1-27);
2. ``situacao = 'removido'`` com o motivo;
3. ementa e decisão apagadas em ``acordao`` e nos snapshots de ``acordao_historico``;
4. trechos vetoriais apagados (``acordao_trecho``, F3-09, quando existir);
5. arquivos brutos reescritos sem o registro: o arquivo da última coleta e todos os arquivos
   dos diretórios das unidades em que ele pode ter aparecido, registrados ou não em
   ``coleta_bruta`` (ex.: páginas que sobraram de uma coleta com mais páginas).

O registro de que o acórdão existiu (número, datas, links, motivo) continua no banco; o texto
não.
"""

from collections.abc import Collection, Sequence
from datetime import date, timedelta
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import Connection, text

from buscajus.ingest.bruto import ArmazenamentoBruto, ArquivoBruto

# Campo que identifica o item no bruto de cada fonte.
CAMPO_ID = {"djen": "id", "tjdft": "uuid"}


def apagar_conteudo(conexao: Connection, acordao_ids: Sequence[int]) -> None:
    """Apaga ementa e decisão do acórdão e das versões anteriores."""
    if not acordao_ids:
        return
    ids = list(acordao_ids)
    conexao.execute(
        text("""
            UPDATE acordao SET ementa = '', decisao = NULL, atualizado_em = now()
            WHERE id = ANY(:ids)
        """),
        {"ids": ids},
    )
    conexao.execute(
        text("""
            UPDATE acordao_historico SET snapshot = snapshot - 'ementa' - 'decisao'
            WHERE acordao_id = ANY(:ids)
        """),
        {"ids": ids},
    )
    # F3-09: apagar também os trechos (acordao_trecho) quando a tabela existir.


def atualizar_coleta_bruta(conexao: Connection, arquivo: ArquivoBruto) -> None:
    conexao.execute(
        text("""
            UPDATE coleta_bruta SET sha256 = :sha256, bytes = :bytes, itens = :itens
            WHERE caminho_arquivo = :caminho
        """),
        {
            "sha256": arquivo.sha256,
            "bytes": arquivo.bytes,
            "itens": arquivo.itens,
            "caminho": arquivo.caminho_relativo,
        },
    )


def _diretorios(linha: Any) -> set[str]:
    """Diretórios do bruto em que o acórdão pode ter aparecido."""
    diretorios = set()
    if linha.caminho_arquivo:
        diretorios.add(str(PurePosixPath(linha.caminho_arquivo).parent))
    datas: list[date] = []
    if linha.fonte == "djen" and linha.data_disponibilizacao:
        datas.append(linha.data_disponibilizacao)
    if linha.fonte == "tjdft" and linha.data_publicacao:
        # A unidade do TJDFT é a data UTC: o dia em São Paulo ou o seguinte.
        datas += [linha.data_publicacao, linha.data_publicacao + timedelta(days=1)]
    diretorios.update(f"{linha.fonte}/{linha.tribunal}/{d.isoformat()}" for d in datas)
    return diretorios


def limpar_brutos(
    conexao: Connection, bruto: ArmazenamentoBruto, acordao_ids: Sequence[int]
) -> int:
    """Reescreve os arquivos brutos sem os acórdãos. Devolve quantos arquivos mudaram."""
    if not acordao_ids:
        return 0
    linhas = conexao.execute(
        text("""
            SELECT a.fonte::text AS fonte, a.id_fonte, a.tribunal, a.data_publicacao,
                a.data_disponibilizacao, b.caminho_arquivo
            FROM acordao a LEFT JOIN coleta_bruta b ON b.id = a.coleta_bruta_id
            WHERE a.id = ANY(:ids)
        """),
        {"ids": list(acordao_ids)},
    ).all()
    por_arquivo: dict[tuple[str, str], set[str]] = {}
    for linha in linhas:
        for diretorio in _diretorios(linha):
            for caminho in bruto.listar(diretorio):
                por_arquivo.setdefault((caminho, linha.fonte), set()).add(linha.id_fonte)
    alterados = 0
    for (caminho, fonte), ids_fonte in sorted(por_arquivo.items()):
        arquivo = bruto.reescrever_sem(caminho, CAMPO_ID[fonte], ids_fonte)
        if arquivo is not None:
            atualizar_coleta_bruta(conexao, arquivo)
            alterados += 1
    return alterados


def remover(
    conexao: Connection,
    bruto: ArmazenamentoBruto,
    acordao_ids: Collection[int],
    motivo: str,
    *,
    pedido_remocao_id: int | None = None,
) -> list[int]:
    """Remove os acórdãos (regra geral do F2-13). Devolve os ids efetivamente removidos."""
    ids = sorted(set(acordao_ids))
    if not ids:
        return []
    conexao.execute(
        text("""
            INSERT INTO bloqueio (fonte, id_fonte, motivo, pedido_remocao_id)
            SELECT a.fonte, a.id_fonte, :motivo, :pedido FROM acordao a
            WHERE a.id = ANY(:ids) AND NOT EXISTS (
                SELECT 1 FROM bloqueio b WHERE b.fonte = a.fonte AND b.id_fonte = a.id_fonte
            )
        """),
        {"ids": ids, "motivo": motivo, "pedido": pedido_remocao_id},
    )
    removidos = list(
        conexao.scalars(
            text("""
                UPDATE acordao SET situacao = 'removido', motivo_situacao = :motivo,
                    atualizado_em = now()
                WHERE id = ANY(:ids) AND situacao <> 'removido'
                RETURNING id
            """),
            {"ids": ids, "motivo": motivo},
        )
    )
    # Mesmo os que já estavam removidos têm o conteúdo apagado (idempotente).
    apagar_conteudo(conexao, ids)
    limpar_brutos(conexao, bruto, ids)
    return removidos
