"""Índices temporários para a avaliação (F3-04): vetorial em memória e full-text no Postgres.

São "sistemas" de busca para comparar modelos antes de existir a tabela ``acordao_trecho``
(F3-07) e a API de busca (Fase 4). O vetorial fatia cada ementa (F3-03), gera os vetores das
passagens e, na consulta, pontua cada acórdão pelo seu melhor trecho (similaridade de cosseno).
O full-text é o mesmo ramo da busca (``busca.texto.ramo_texto``, seção 8.4), sem filtros.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from sqlalchemy import Engine, text

from buscajus.api.esquemas import FiltrosBusca
from buscajus.busca.texto import ramo_texto
from buscajus.embed.embedder import Embedder
from buscajus.embed.fatiamento import fatiar


@dataclass(frozen=True)
class Documento:
    id: str
    texto: str


@dataclass(frozen=True)
class Resultado:
    id: str
    pontuacao: float


class Sistema(Protocol):
    @property
    def nome(self) -> str: ...

    def buscar(self, consulta: str, k: int) -> list[Resultado]: ...


class IndiceVetorialMemoria:
    def __init__(
        self,
        embedder: Embedder,
        documentos: Iterable[Documento],
        *,
        tokens_por_trecho: int = 450,
        sobreposicao: int = 50,
    ) -> None:
        self._embedder = embedder
        ids: list[str] = []
        textos: list[str] = []
        for documento in documentos:
            for trecho in fatiar(
                documento.texto,
                embedder.tokenizador,
                tokens_por_trecho=tokens_por_trecho,
                sobreposicao=sobreposicao,
            ):
                ids.append(documento.id)
                textos.append(trecho.texto)
        self._ids = np.array(ids, dtype=object)
        self._vetores = embedder.embed_passagens(textos)
        self.trechos = len(textos)

    @property
    def nome(self) -> str:
        return f"vetorial:{self._embedder.nome}"

    def buscar(self, consulta: str, k: int) -> list[Resultado]:
        if self.trechos == 0:
            return []
        similaridades = self._vetores @ self._embedder.embed_consultas([consulta])[0]
        melhores: dict[str, float] = {}
        for indice in np.argsort(-similaridades):
            doc = str(self._ids[indice])
            if doc not in melhores:
                melhores[doc] = float(similaridades[indice])
                if len(melhores) == k:
                    break
        return [Resultado(doc, pontuacao) for doc, pontuacao in melhores.items()]


class BuscaTextoPostgres:
    """Full-text sobre os acórdãos ativos (id do acórdão como texto)."""

    nome = "texto"

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def buscar(self, consulta: str, k: int) -> list[Resultado]:
        with self._engine.connect() as conexao:
            resultados = ramo_texto(conexao, consulta, FiltrosBusca(), limite=k)
        return [Resultado(str(i), pontuacao) for i, pontuacao in resultados]


def documentos_ativos(engine: Engine, limite: int | None = None) -> list[Documento]:
    """Ementas dos acórdãos ativos, para montar o índice vetorial temporário."""
    with engine.connect() as conexao:
        linhas = conexao.execute(
            text("""
                SELECT id, ementa FROM acordao WHERE situacao = 'ativo'
                ORDER BY id LIMIT :limite
            """),
            {"limite": limite},
        ).all()
    return [Documento(str(linha.id), linha.ementa) for linha in linhas]
