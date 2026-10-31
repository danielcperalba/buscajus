"""Embeddings com um modelo real minúsculo (F3-02, F3-03).

Exige o grupo opcional ``embeddings`` (sem ele, os testes são pulados) e baixa ~17 MB do
Hugging Face na primeira vez. O modelo é o de testes do próprio sentence-transformers, com a
revisão fixada: serve para provar a integração, não para medir qualidade.
"""

from collections.abc import Iterator

import numpy as np
import pytest

pytest.importorskip("sentence_transformers")

from buscajus.embed.embedder import EmbedderSentenceTransformers
from buscajus.embed.fatiamento import fatiar
from buscajus.embed.indice import Documento, IndiceVetorialMemoria

pytestmark = pytest.mark.modelo

MODELO = "sentence-transformers-testing/stsb-bert-tiny-safetensors"
REVISAO = "f3cb857cba53019a20df283396bcca179cf051a4"


@pytest.fixture(scope="module")
def embedder() -> Iterator[EmbedderSentenceTransformers]:
    yield EmbedderSentenceTransformers(MODELO, revisao=REVISAO, dispositivo="cpu", tamanho_lote=2)


def test_nome_dimensao_e_normalizacao(embedder: EmbedderSentenceTransformers) -> None:
    assert embedder.nome == f"{MODELO}@{REVISAO}"
    vetores = embedder.embed_passagens(["partilha de bens", "plano de saúde", "furto", "x"])
    assert vetores.shape == (4, embedder.dimensao)
    assert vetores.dtype == np.float32
    assert np.allclose(np.linalg.norm(vetores, axis=1), 1, atol=1e-5)
    assert embedder.embed_consultas([]).shape == (0, embedder.dimensao)


def test_lotes_nao_mudam_os_vetores(embedder: EmbedderSentenceTransformers) -> None:
    textos = ["herança", "inventário e partilha", "dano moral", "pensão alimentícia", "pix"]
    juntos = embedder.embed_passagens(textos)
    sozinhos = np.vstack([embedder.embed_passagens([t]) for t in textos])
    assert np.allclose(juntos, sozinhos, atol=1e-4)


def test_tokenizador_do_modelo_no_fatiamento(embedder: EmbedderSentenceTransformers) -> None:
    texto = "DIREITO CIVIL. Partilha de bens na herança. " * 80
    posicoes = embedder.tokenizador.posicoes(texto)
    assert all(texto[i:f].strip() for i, f in posicoes)
    trechos = fatiar(texto, embedder.tokenizador, tokens_por_trecho=100, sobreposicao=20)
    assert len(trechos) > 1 and all(t.tokens <= 100 for t in trechos)
    assert all(texto[t.inicio : t.fim] == t.texto for t in trechos)
    assert embedder.max_tokens > 0


def test_indice_vetorial_com_modelo_real(embedder: EmbedderSentenceTransformers) -> None:
    documentos = [Documento("1", "A partilha da herança entre os filhos."), Documento("2", "x")]
    resultados = IndiceVetorialMemoria(embedder, documentos).buscar("herança", 2)
    assert {r.id for r in resultados} == {"1", "2"}
