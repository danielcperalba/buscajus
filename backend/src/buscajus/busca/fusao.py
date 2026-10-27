"""Fusão dos ramos por Reciprocal Rank Fusion (F4-06; ARCHITECTURE.md, seção 8.5).

``pontuacao(d) = Σ_r peso_r / (k + posição_r(d))``, com posição começando em 1. Empates:
melhor posição em qualquer ramo, depois o menor id (ordem estável). Até ``limite`` resultados;
as páginas são recortes dessa lista.
"""

from collections.abc import Mapping, Sequence


def rrf(
    rankings: Mapping[str, Sequence[int]],
    pesos: Mapping[str, float] | None = None,
    *,
    k: float = 60,
    limite: int = 200,
) -> list[tuple[int, float]]:
    pontuacao: dict[int, float] = {}
    melhor_posicao: dict[int, int] = {}
    for ramo, ids in rankings.items():
        peso = (pesos or {}).get(ramo, 1.0)
        vistos: set[int] = set()
        for posicao, doc in enumerate(ids, start=1):
            if doc in vistos:  # o mesmo acórdão duas vezes num ramo conta uma vez
                continue
            vistos.add(doc)
            pontuacao[doc] = pontuacao.get(doc, 0.0) + peso / (k + posicao)
            melhor_posicao[doc] = min(melhor_posicao.get(doc, posicao), posicao)
    ordem = sorted(pontuacao, key=lambda d: (-pontuacao[d], melhor_posicao[d], d))
    return [(doc, pontuacao[doc]) for doc in ordem[:limite]]


def pagina(ids: Sequence[int], numero: int, por_pagina: int) -> list[int]:
    inicio = (numero - 1) * por_pagina
    return list(ids[inicio : inicio + por_pagina])
