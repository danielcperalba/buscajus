"""Fatiamento de ementas longas (F3-03; ARCHITECTURE.md, seção 7.2).

Ementas que cabem em ``tokens_por_trecho`` tokens do modelo viram um trecho só (a maioria).
As mais longas viram janelas de ``tokens_por_trecho`` tokens com ``sobreposicao`` tokens em
comum entre janelas vizinhas. Os cortes seguem as posições dos tokens no texto original, então
cada trecho é um pedaço contínuo da ementa.
"""

from dataclasses import dataclass

from buscajus.embed.embedder import Tokenizador


@dataclass(frozen=True)
class Trecho:
    ordem: int
    texto: str
    inicio: int  # posição (em caracteres) na ementa
    fim: int
    tokens: int


def fatiar(
    texto: str, tokenizador: Tokenizador, *, tokens_por_trecho: int = 450, sobreposicao: int = 50
) -> list[Trecho]:
    if not 0 <= sobreposicao < tokens_por_trecho:
        raise ValueError("a sobreposição deve ser menor que o tamanho do trecho")
    posicoes = tokenizador.posicoes(texto)
    if len(posicoes) <= tokens_por_trecho:
        return [Trecho(0, texto, 0, len(texto), len(posicoes))] if texto.strip() else []
    passo = tokens_por_trecho - sobreposicao
    trechos: list[Trecho] = []
    inicio_token = 0
    while True:
        fim_token = min(inicio_token + tokens_por_trecho, len(posicoes))
        inicio, fim = posicoes[inicio_token][0], posicoes[fim_token - 1][1]
        trechos.append(
            Trecho(len(trechos), texto[inicio:fim], inicio, fim, fim_token - inicio_token)
        )
        if fim_token == len(posicoes):
            return trechos
        inicio_token += passo
