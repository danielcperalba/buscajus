"""Camada 2: NER de pessoas (ARCHITECTURE.md, seção 6.3).

O modelo entra pela interface :class:`DetectorPessoas`; a escolha dele é o F1-36 e a
implementação, o F1-37. Este módulo aplica as detecções com as exceções do ARCHITECTURE:

- o relator do acórdão;
- nomes precedidos de títulos de magistrado em citações de precedentes (``Rel.``,
  ``Min.``, ``Des.``, ``Juiz``…);
- epônimos de leis e institutos de uma lista curada.

Na dúvida, substitui: um nome trocado por engano custa legibilidade; um que escapa vaza.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from buscajus.ingest.anonimizacao.nomes import alinhado, iniciais, sobrepoe, trechos_protegidos

# Lista curada de epônimos (nomes de pessoas que dão nome a leis e institutos).
EPONIMOS = (
    "Lei Maria da Penha",
    "Lei Carolina Dieckmann",
    "Lei Henry Borel",
    "Lei Mariana Ferrer",
    "Lei Joanna Maranhão",
    "Lei Tatiane Spitzner",
    "Lei Lucas",
    "Lei Berenice Piana",
    "Lei Romeo Mion",
    "Lei Aldir Blanc",
    "Lei Paulo Gustavo",
    "Lei Pelé",
    "Lei Zico",
    "Lei Rouanet",
    "Lei Arouca",
    "Lei Kandir",
    "Lei Afonso Arinos",
    "Lei Eloy Chaves",
    "Lei Eloi Chaves",
    "Lei Menino Bernardo",
    "Lei Clodovil Hernandes",
)

# Título de magistrado imediatamente antes do nome (texto alinhado: sem acento, maiúsculo).
_TITULO_ANTES = re.compile(
    r"(?<![A-Z])(?:REL|RELA|RELATOR|RELATORA|MIN|MINISTRO|MINISTRA|DES|DESA|DESEMBARGADOR|"
    r"DESEMBARGADORA|JUIZ|JUIZA|CONS|CONSELHEIRO|CONSELHEIRA)\.?(?:\(A\))?"
    r"(?:\s+(?:MIN|DES|DESA|JUIZ|JUIZA)\.?)?[\s:]*$"
)
_JANELA_TITULO = 40


@dataclass(frozen=True)
class Entidade:
    inicio: int
    fim: int


class DetectorPessoas(Protocol):
    """Modelo local de NER. ``versao`` identifica o modelo em ``anonimizacao_versao``."""

    versao: str

    def detectar(self, texto: str) -> Sequence[Entidade]:
        """Trechos do texto reconhecidos como nomes de pessoas."""
        ...


def _precedido_de_titulo(texto: str, inicio: int) -> bool:
    antes = alinhado(texto[max(0, inicio - _JANELA_TITULO) : inicio])
    return bool(_TITULO_ANTES.search(antes))


def aplicar(
    texto: str, detector: DetectorPessoas, protegidos: Sequence[str] = ()
) -> tuple[str, int]:
    """Troca as pessoas detectadas por iniciais, respeitando as exceções."""
    entidades = sorted(detector.detectar(texto), key=lambda e: (e.inicio, -e.fim))
    trechos = trechos_protegidos(texto, (*EPONIMOS, *protegidos))
    partes: list[str] = []
    ultimo = 0
    substituicoes = 0
    for entidade in entidades:
        if entidade.inicio < ultimo or entidade.fim <= entidade.inicio:
            continue  # sobreposta a uma já substituída, ou vazia
        trecho = texto[entidade.inicio : entidade.fim]
        if (
            sobrepoe(entidade.inicio, entidade.fim, trechos)
            or _precedido_de_titulo(texto, entidade.inicio)
            or not iniciais(trecho)
        ):
            continue
        partes += [texto[ultimo : entidade.inicio], iniciais(trecho)]
        ultimo = entidade.fim
        substituicoes += 1
    partes.append(texto[ultimo:])
    return "".join(partes), substituicoes
