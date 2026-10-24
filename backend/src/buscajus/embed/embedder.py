"""Abstração do modelo de embedding (F3-02; ARCHITECTURE.md, seção 7).

- :class:`Embedder`: ``nome`` (modelo + revisão, gravado em ``acordao_trecho.modelo``),
  ``dimensao``, ``embed_consultas`` e ``embed_passagens`` (vetores ``float32`` com norma L2 1,
  para distância de cosseno), ``tokenizador`` e ``max_tokens`` (para o fatiamento, F3-03).
- Prefixos por família de modelo (:func:`perfil`): a família e5 exige ``"query: "`` e
  ``"passage: "``; os demais candidatos não usam prefixo.
- :class:`EmbedderSentenceTransformers`: modelo local via sentence-transformers, em lotes,
  em GPU se houver (``dispositivo = "auto"``). O pacote fica no grupo opcional
  ``embeddings`` e só é importado quando o modelo é carregado.
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

Vetores = npt.NDArray[np.float32]


@dataclass(frozen=True)
class Perfil:
    prefixo_consulta: str = ""
    prefixo_passagem: str = ""


PERFIL_E5 = Perfil(prefixo_consulta="query: ", prefixo_passagem="passage: ")
SEM_PREFIXO = Perfil()


def perfil(nome_modelo: str) -> Perfil:
    """Prefixos exigidos pela família do modelo (e5: ``query:``/``passage:``)."""
    familia = nome_modelo.split("@", 1)[0].lower()
    if familia.startswith("intfloat/") and "e5" in familia:
        return PERFIL_E5
    return SEM_PREFIXO


class Tokenizador(Protocol):
    def posicoes(self, texto: str) -> list[tuple[int, int]]:
        """Posição (início, fim) no texto de cada token, sem os tokens especiais."""
        ...


class Embedder(Protocol):
    @property
    def nome(self) -> str: ...

    @property
    def dimensao(self) -> int: ...

    @property
    def max_tokens(self) -> int: ...

    @property
    def tokenizador(self) -> Tokenizador: ...

    def embed_consultas(self, textos: Sequence[str]) -> Vetores: ...

    def embed_passagens(self, textos: Sequence[str]) -> Vetores: ...


def normalizar_l2(vetores: npt.ArrayLike) -> Vetores:
    """Norma L2 1 em cada linha (vetor nulo continua nulo)."""
    matriz = np.atleast_2d(np.asarray(vetores, dtype=np.float32))
    normas = np.linalg.norm(matriz, axis=1, keepdims=True)
    resultado: Vetores = (matriz / np.where(normas == 0, 1, normas)).astype(np.float32)
    return resultado


def em_lotes[T](itens: Sequence[T], tamanho: int) -> Iterator[Sequence[T]]:
    for inicio in range(0, len(itens), tamanho):
        yield itens[inicio : inicio + tamanho]


def escolher_dispositivo(dispositivo: str) -> str:
    if dispositivo != "auto":
        return dispositivo
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


class TokenizadorHF:
    """Tokenizador rápido do Hugging Face (o do próprio modelo)."""

    def __init__(self, tokenizer: Any) -> None:
        self._tokenizer = tokenizer

    def posicoes(self, texto: str) -> list[tuple[int, int]]:
        codificado = self._tokenizer(
            texto, add_special_tokens=False, return_offsets_mapping=True, truncation=False
        )
        return [(int(i), int(f)) for i, f in codificado["offset_mapping"]]


class EmbedderSentenceTransformers:
    def __init__(
        self,
        modelo: str,
        *,
        revisao: str | None = None,
        dispositivo: str = "auto",
        tamanho_lote: int = 32,
        diretorio_cache: str | None = None,
    ) -> None:
        from sentence_transformers import SentenceTransformer

        self._modelo = SentenceTransformer(
            modelo,
            revision=revisao,
            device=escolher_dispositivo(dispositivo),
            cache_folder=diretorio_cache,
        )
        self._nome = f"{modelo}@{revisao}" if revisao else modelo
        self._perfil = perfil(modelo)
        self._tamanho_lote = tamanho_lote
        self._tokenizador = TokenizadorHF(self._modelo.tokenizer)

    @property
    def nome(self) -> str:
        return self._nome

    @property
    def dimensao(self) -> int:
        # sentence-transformers 6 renomeou o método; o nome antigo vale nas versões anteriores.
        obter = (
            getattr(self._modelo, "get_embedding_dimension", None)
            or self._modelo.get_sentence_embedding_dimension
        )
        dimensao = obter()
        if dimensao is None:
            raise ValueError("o modelo não informa a dimensão dos vetores")
        return int(dimensao)

    @property
    def max_tokens(self) -> int:
        return int(self._modelo.max_seq_length)

    @property
    def tokenizador(self) -> Tokenizador:
        return self._tokenizador

    def embed_consultas(self, textos: Sequence[str]) -> Vetores:
        return self._embed([self._perfil.prefixo_consulta + t for t in textos])

    def embed_passagens(self, textos: Sequence[str]) -> Vetores:
        return self._embed([self._perfil.prefixo_passagem + t for t in textos])

    def _embed(self, textos: Sequence[str]) -> Vetores:
        if not textos:
            return np.zeros((0, self.dimensao), dtype=np.float32)
        partes = [
            self._modelo.encode(
                list(lote),
                batch_size=self._tamanho_lote,
                convert_to_numpy=True,
                normalize_embeddings=False,
                show_progress_bar=False,
            )
            for lote in em_lotes(textos, self._tamanho_lote)
        ]
        return normalizar_l2(np.concatenate(partes))
