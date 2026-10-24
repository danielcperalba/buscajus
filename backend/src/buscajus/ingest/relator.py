"""Nome do relator: forma de exibição e chave de filtro (F1-22, ARCHITECTURE.md, seção 5.2).

- Títulos padronizados: ``Desembargador`` → ``Des.``, ``Desembargadora`` → ``Desa.``;
  ``Juiz``/``Juíza`` (e qualificações como "de Direito Substituto em Segundo Grau") são
  mantidos.
- Nomes todos em caixa alta viram *title case*, com partículas em minúsculas.
- ``relator_chave``: sem títulos nem qualificações, sem acentos, em minúsculas.
"""

import re
from dataclasses import dataclass

from buscajus.ingest.texto import chave

PARTICULAS = frozenset({"de", "da", "do", "das", "dos", "e", "em", "di", "du", "del", "van", "von"})

_DESEMBARGADOR = (
    (re.compile(r"^desembargador\(a\)\s+", re.IGNORECASE), "Des."),
    (re.compile(r"^desembargadora\s+", re.IGNORECASE), "Desa."),
    (re.compile(r"^desembargador\s+", re.IGNORECASE), "Des."),
    (re.compile(r"^desa\.?\s+", re.IGNORECASE), "Desa."),
    (re.compile(r"^des\.?\s+", re.IGNORECASE), "Des."),
)
_JUIZ = re.compile(
    r"^(?P<titulo>ju[ií]z(?:a|\(a\))?"
    r"(?:\s+de\s+direito)?"
    r"(?:\s+substitut[oa](?:\(a\))?)?"
    r"(?:\s+em\s+(?:segundo|2[ºo°])\s+grau)?)\s+",
    re.IGNORECASE,
)
_OUTROS_TITULOS = re.compile(
    r"^(?:dr|dra|doutor|doutora|ministro|ministra|min)\.?\s+", re.IGNORECASE
)


@dataclass(frozen=True)
class Relator:
    exibicao: str
    chave: str


def _title_case(texto: str) -> str:
    def palavra(token: str, primeira: bool) -> str:
        if not primeira and token.lower() in PARTICULAS:
            return token.lower()
        return "-".join(parte[:1].upper() + parte[1:].lower() for parte in token.split("-"))

    tokens = texto.split()
    return " ".join(palavra(t, i == 0) for i, t in enumerate(tokens))


def _formatar(texto: str) -> str:
    letras = [c for c in texto if c.isalpha()]
    return _title_case(texto) if letras and all(c.isupper() for c in letras) else texto


def normalizar_relator(valor: str | None) -> Relator | None:
    if not valor:
        return None
    nome = " ".join(valor.split()).strip(" ,.;:")
    if not nome:
        return None

    titulo = ""
    for padrao, abreviacao in _DESEMBARGADOR:
        if padrao.match(nome):
            titulo, nome = abreviacao, padrao.sub("", nome, count=1)
            break
    else:
        juiz = _JUIZ.match(nome)
        if juiz:
            titulo = _formatar(juiz.group("titulo"))
            nome = nome[juiz.end() :]
        else:
            nome = _OUTROS_TITULOS.sub("", nome, count=1)

    nome = _formatar(nome)
    exibicao = f"{titulo} {nome}".strip()
    return Relator(exibicao=exibicao, chave=chave(nome))
