"""Casamento tolerante de nomes de pessoas e iniciais (ARCHITECTURE.md, seção 6.3).

O casamento ignora acentos e caixa e é feito sobre uma forma do texto com **o mesmo
comprimento** do original (cada caractere vira sua letra-base em maiúscula), para que as
posições encontradas valham no texto original e a substituição preserve o resto.

Um nome casa por inteiro ou por subsequências de dois ou mais tokens, na ordem (ex.: primeiro
e último nome), com partículas opcionais entre eles. Um token isolado nunca casa.
"""

import itertools
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

PARTICULAS = frozenset({"DE", "DA", "DO", "DAS", "DOS", "E", "DI", "DU", "DEL", "D", "VAN", "VON"})
# Acima disso, só os primeiros tokens geram subsequências (2^n cresce rápido).
MAXIMO_TOKENS = 8

_SEPARADOR = r"[\s.,'’-]+(?:(?:DE|DA|DO|DAS|DOS|E|DI|DU|DEL|D)[\s.'’]+)*"
_LIMITE_ANTES = r"(?<![A-Z0-9])"
_LIMITE_DEPOIS = r"(?![A-Z0-9])"


def _base(caractere: str) -> str:
    decomposto = unicodedata.normalize("NFKD", caractere)
    letra = decomposto[0].upper() if decomposto else caractere
    return letra if len(letra) == 1 else caractere


def alinhado(texto: str) -> str:
    """Letras-base em maiúsculas, com o mesmo comprimento do texto original."""
    return "".join(_base(c) for c in texto)


def tokens(nome: str) -> list[str]:
    return [
        t for t in re.findall(r"[A-Z0-9]+", alinhado(nome)) if t not in PARTICULAS and len(t) > 1
    ]


def iniciais(nome: str) -> str:
    """``JOSÉ DA SILVA SANTOS`` → ``J.S.S.``"""
    return "".join(f"{t[0]}." for t in tokens(nome) if t[0].isalpha())


def padrao_sequencia(sequencia: Sequence[str]) -> str:
    return _SEPARADOR.join(re.escape(t) for t in sequencia)


def subsequencias(nome: str) -> list[tuple[str, ...]]:
    ts = tokens(nome)[:MAXIMO_TOKENS]
    if len(ts) < 2:
        return []
    return [
        tuple(ts[i] for i in indices)
        for k in range(len(ts), 1, -1)
        for indices in itertools.combinations(range(len(ts)), k)
    ]


@dataclass(frozen=True)
class Ocorrencia:
    inicio: int
    fim: int
    indice: int  # posição do nome na lista do Casador


class Casador:
    """Procura vários nomes de uma vez, preferindo a ocorrência mais longa."""

    def __init__(self, nomes: Sequence[str]) -> None:
        self.nomes = list(nomes)
        grupos = []
        for indice, nome in enumerate(self.nomes):
            padroes = sorted(
                {padrao_sequencia(s) for s in subsequencias(nome)}, key=len, reverse=True
            )
            if padroes:
                grupos.append((max(map(len, padroes)), f"(?P<n{indice}>{'|'.join(padroes)})"))
        grupos.sort(key=lambda g: g[0], reverse=True)
        self._regex = (
            re.compile(
                _LIMITE_ANTES + "(?:" + "|".join(g for _, g in grupos) + ")" + _LIMITE_DEPOIS
            )
            if grupos
            else None
        )

    def __bool__(self) -> bool:
        return self._regex is not None

    def encontrar(self, texto: str) -> list[Ocorrencia]:
        if self._regex is None:
            return []
        return [
            Ocorrencia(m.start(), m.end(), int((m.lastgroup or "n0")[1:]))
            for m in self._regex.finditer(alinhado(texto))
        ]


def trechos_protegidos(texto: str, protegidos: Iterable[str]) -> list[tuple[int, int]]:
    """Posições de expressões que nunca são substituídas (relator, epônimos)."""
    alvo = alinhado(texto)
    trechos = []
    for expressao in protegidos:
        ts = [t for t in re.findall(r"[A-Z0-9]+", alinhado(expressao)) if t not in PARTICULAS]
        if not ts:
            continue
        regex = re.compile(_LIMITE_ANTES + padrao_sequencia(ts) + _LIMITE_DEPOIS)
        trechos += [(m.start(), m.end()) for m in regex.finditer(alvo)]
    return trechos


def sobrepoe(inicio: int, fim: int, trechos: Iterable[tuple[int, int]]) -> bool:
    return any(inicio < f and i < fim for i, f in trechos)


def substituir(texto: str, casador: Casador, protegidos: Sequence[str] = ()) -> tuple[str, int]:
    """Troca cada ocorrência pelas iniciais do nome completo. Devolve o texto e a contagem."""
    if not casador:
        return texto, 0
    trechos = trechos_protegidos(texto, protegidos)
    partes: list[str] = []
    ultimo = 0
    substituicoes = 0
    for oc in casador.encontrar(texto):
        if sobrepoe(oc.inicio, oc.fim, trechos):
            continue
        partes += [texto[ultimo : oc.inicio], iniciais(casador.nomes[oc.indice])]
        ultimo = oc.fim
        substituicoes += 1
    partes.append(texto[ultimo:])
    return "".join(partes), substituicoes
