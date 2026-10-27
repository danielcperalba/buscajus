"""Ramo vetorial da busca (F4-05; ARCHITECTURE.md, seção 8.3), atrás de uma interface.

A implementação (embedding da consulta e top-k sobre ``acordao_trecho`` com HNSW) depende do
modelo fixado (F3-06) e da tabela de trechos (F3-07). Até lá o ramo fica desligado: devolve
nada, e a busca híbrida funciona só com o full-text.
"""

from typing import Protocol

from sqlalchemy import Connection

from buscajus.api.consulta import NumeroNaConsulta
from buscajus.api.esquemas import FiltrosBusca


class RamoVetorial(Protocol):
    @property
    def disponivel(self) -> bool: ...

    def buscar(
        self,
        conexao: Connection,
        consulta: str,
        filtros: FiltrosBusca,
        numero: NumeroNaConsulta | None,
        *,
        limite: int,
    ) -> list[tuple[int, float]]:
        """(id do acórdão, similaridade), um por acórdão, com os mesmos filtros do full-text."""
        ...


class RamoVetorialDesligado:
    disponivel = False

    def buscar(
        self,
        conexao: Connection,
        consulta: str,
        filtros: FiltrosBusca,
        numero: NumeroNaConsulta | None,
        *,
        limite: int,
    ) -> list[tuple[int, float]]:
        return []
