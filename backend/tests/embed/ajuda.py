"""Apoio aos testes de embeddings sem modelo real: tokenizador e embedder determinísticos."""

import hashlib
import re
from collections.abc import Sequence

import numpy as np

from buscajus.embed.embedder import Perfil, Tokenizador, Vetores, normalizar_l2, perfil
from buscajus.ingest.texto import sem_acentos


class TokenizadorEspacos:
    """Um token por palavra (sequência sem espaço)."""

    def posicoes(self, texto: str) -> list[tuple[int, int]]:
        return [(m.start(), m.end()) for m in re.finditer(r"\S+", texto)]


class EmbedderSacoDePalavras:
    """Embedder falso: soma de vetores por palavra (hash), sem acento e sem caixa.

    Registra os textos recebidos, com os prefixos do perfil do nome do modelo.
    """

    def __init__(self, nome: str = "falso/saco-de-palavras", dimensao: int = 64) -> None:
        self._nome = nome
        self._dimensao = dimensao
        self._perfil: Perfil = perfil(nome)
        self.recebidos: list[str] = []

    @property
    def nome(self) -> str:
        return self._nome

    @property
    def dimensao(self) -> int:
        return self._dimensao

    @property
    def max_tokens(self) -> int:
        return 512

    @property
    def tokenizador(self) -> Tokenizador:
        return TokenizadorEspacos()

    def embed_consultas(self, textos: Sequence[str]) -> Vetores:
        return self._embed([self._perfil.prefixo_consulta + t for t in textos])

    def embed_passagens(self, textos: Sequence[str]) -> Vetores:
        return self._embed([self._perfil.prefixo_passagem + t for t in textos])

    def _embed(self, textos: Sequence[str]) -> Vetores:
        self.recebidos += textos
        matriz = np.zeros((len(textos), self._dimensao), dtype=np.float32)
        for linha, texto in enumerate(textos):
            for palavra in re.findall(r"\w+", sem_acentos(texto).lower()):
                if palavra in ("query", "passage"):
                    continue
                indice = int(hashlib.sha256(palavra.encode()).hexdigest(), 16) % self._dimensao
                matriz[linha, indice] += 1
        return normalizar_l2(matriz)
