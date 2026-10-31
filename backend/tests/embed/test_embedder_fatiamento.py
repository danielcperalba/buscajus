"""Abstração de embeddings (F3-02) e fatiamento (F3-03), sem modelo real."""

import numpy as np
import pytest
from pydantic import ValidationError

from buscajus.core.config import ConfigEmbeddings
from buscajus.embed.embedder import (
    PERFIL_E5,
    SEM_PREFIXO,
    Embedder,
    em_lotes,
    normalizar_l2,
    perfil,
)
from buscajus.embed.fatiamento import fatiar

from .ajuda import EmbedderSacoDePalavras, TokenizadorEspacos


def test_normalizar_l2() -> None:
    vetores = normalizar_l2([[3.0, 4.0], [0.0, 0.0]])
    assert vetores.dtype == np.float32
    assert np.allclose(vetores[0], [0.6, 0.8])
    assert np.allclose(vetores[1], [0.0, 0.0])  # vetor nulo não vira NaN
    assert normalizar_l2([1.0, 1.0]).shape == (1, 2)


def test_em_lotes() -> None:
    assert [list(lote) for lote in em_lotes(list(range(5)), 2)] == [[0, 1], [2, 3], [4]]


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("intfloat/multilingual-e5-small", PERFIL_E5),
        ("intfloat/multilingual-e5-base@abc123", PERFIL_E5),
        ("intfloat/multilingual-e5-large", PERFIL_E5),
        ("BAAI/bge-m3", SEM_PREFIXO),
        ("rufimelo/Legal-BERTimbau-sts-base", SEM_PREFIXO),
    ],
)
def test_prefixos_por_familia(nome: str, esperado: object) -> None:
    assert perfil(nome) == esperado


def test_prefixos_aplicados_pelo_embedder() -> None:
    embedder = EmbedderSacoDePalavras("intfloat/multilingual-e5-base")
    embedder.embed_consultas(["herança"])
    embedder.embed_passagens(["partilha de bens"])
    assert embedder.recebidos == ["query: herança", "passage: partilha de bens"]


def test_falso_cumpre_o_protocolo() -> None:
    embedder: Embedder = EmbedderSacoDePalavras()
    vetores = embedder.embed_passagens(["a b", "c"])
    assert vetores.shape == (2, embedder.dimensao)
    assert np.allclose(np.linalg.norm(vetores, axis=1), 1)


def test_configuracao_rejeita_sobreposicao_maior_que_o_trecho() -> None:
    with pytest.raises(ValidationError):
        ConfigEmbeddings(tokens_por_trecho=100, sobreposicao_tokens=100)
    assert ConfigEmbeddings().modelo is None  # modelo ainda não fixado (F3-06)


# --- F3-03 ----------------------------------------------------------------------------


def _palavras(n: int) -> str:
    return " ".join(f"p{i}" for i in range(n))


def test_ementa_curta_vira_um_trecho() -> None:
    texto = "DIREITO CIVIL. Partilha de bens.  Recurso desprovido."
    (trecho,) = fatiar(texto, TokenizadorEspacos())
    assert (trecho.ordem, trecho.texto, trecho.inicio, trecho.fim) == (0, texto, 0, len(texto))
    assert trecho.tokens == 7


def test_texto_vazio_nao_gera_trecho() -> None:
    assert fatiar("   ", TokenizadorEspacos()) == []


def test_ementa_longa_vira_janelas_com_sobreposicao() -> None:
    texto = _palavras(1000)
    trechos = fatiar(texto, TokenizadorEspacos(), tokens_por_trecho=450, sobreposicao=50)
    assert [t.ordem for t in trechos] == [0, 1, 2]
    assert [t.tokens for t in trechos] == [450, 450, 200]
    palavras = [t.texto.split() for t in trechos]
    assert palavras[0][0] == "p0" and palavras[0][-1] == "p449"
    assert palavras[1][0] == "p400" and palavras[1][-1] == "p849"
    assert palavras[2][0] == "p800" and palavras[2][-1] == "p999"
    # Sobreposição de 50 tokens entre vizinhos e cobertura do texto inteiro.
    assert palavras[0][-50:] == palavras[1][:50]
    assert trechos[0].inicio == 0 and trechos[-1].fim == len(texto)
    assert all(texto[t.inicio : t.fim] == t.texto for t in trechos)


def test_limite_exato_nao_gera_trecho_extra() -> None:
    assert len(fatiar(_palavras(450), TokenizadorEspacos())) == 1
    trechos = fatiar(_palavras(850), TokenizadorEspacos())
    assert [t.tokens for t in trechos] == [450, 450]


def test_sobreposicao_invalida() -> None:
    with pytest.raises(ValueError, match="sobreposição"):
        fatiar("a b", TokenizadorEspacos(), tokens_por_trecho=10, sobreposicao=10)
