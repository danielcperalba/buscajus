"""Detecção de número de processo na consulta (F4-02; ARCHITECTURE.md, seções 8.1 e 8.2).

- Número CNJ completo, com ou sem máscara (``NNNNNNN-DD.AAAA.J.TR.OOOO`` ou 20 dígitos
  seguidos, inclusive com a máscara incompleta, ex.: ``0011412-20.20258.16.0069``).
- Número parcial com máscara, a partir de ``NNNNNNN-DD`` (ex.: ``0011412-20.2025``): vira
  busca por prefixo dos dígitos.
- Consulta que é (essencialmente) só o número, com palavras como "processo" ou "nº" em volta:
  busca exata. Número com outros termos: o número vira filtro e o resto segue para a busca
  híbrida.

Um número colado a outros dígitos (ex.: 21 dígitos) não é número de processo. CPF, CNPJ,
datas e números de lei não casam com o padrão. Só o primeiro número da consulta é usado.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from buscajus.ingest.processo import NumeroProcessoInvalido, normalizar_numero
from buscajus.ingest.texto import chave

# Completo: 7-2.4.1.2.4, cada separador opcional (inclui 20 dígitos seguidos).
_COMPLETO = re.compile(r"(?<![\d.-])\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}(?![\d-])(?!\.\d)")
# Parcial: começa com NNNNNNN-DD (hífen obrigatório) e para antes do número completo.
_PARCIAL = re.compile(r"(?<![\d.-])\d{7}-\d{2}(?:\.\d{4}(?:\.\d(?:\.\d{2})?)?)?(?![\d-])(?!\.\d)")
# Palavras que acompanham o número sem mudar a intenção de buscar só o processo.
_ACOMPANHANTES = frozenset(
    {"processo", "proc", "autos", "n", "no", "nº", "n°", "numero", "num", "cnj", "do", "o"}
)
MAXIMO_CONSULTA = 500


@dataclass(frozen=True)
class NumeroNaConsulta:
    digitos: str  # 20 dígitos ou o prefixo
    completo: bool
    mascara: str | None = None  # só para o número completo
    valido: bool | None = None  # dígito verificador (mod 97), só para o completo


@dataclass(frozen=True)
class ConsultaAnalisada:
    original: str
    texto: str  # a consulta sem o número, para a busca híbrida
    numero: NumeroNaConsulta | None

    @property
    def tipo(self) -> Literal["processo", "hibrida"]:
        return "processo" if self.numero is not None and not self.texto else "hibrida"


def normalizar_consulta(consulta: str) -> str:
    """NFC, sem caracteres de controle e com espaços simples (seção 8.1)."""
    texto = unicodedata.normalize("NFC", consulta)
    texto = "".join(" " if unicodedata.category(c).startswith("C") else c for c in texto)
    return " ".join(texto.split())[:MAXIMO_CONSULTA]


def _resto(consulta: str, inicio: int, fim: int) -> str:
    resto = " ".join(f"{consulta[:inicio]} {consulta[fim:]}".split())
    palavras = [p for p in re.findall(r"[^\s,;:()]+", resto) if any(c.isalnum() for c in p)]
    if all(chave(p).strip(".") in _ACOMPANHANTES for p in palavras):
        return ""
    return resto.strip(" ,;:-")


def analisar_consulta(consulta: str) -> ConsultaAnalisada:
    texto = normalizar_consulta(consulta)
    completo = _COMPLETO.search(texto)
    if completo:
        try:
            numero = normalizar_numero(completo.group())
        except NumeroProcessoInvalido:  # pragma: no cover (o padrão garante 20 dígitos)
            return ConsultaAnalisada(texto, texto, None)
        encontrado = NumeroNaConsulta(numero.digitos, True, numero.mascara, numero.valido)
        return ConsultaAnalisada(texto, _resto(texto, *completo.span()), encontrado)
    parcial = _PARCIAL.search(texto)
    if parcial:
        digitos = "".join(c for c in parcial.group() if c.isdigit())
        return ConsultaAnalisada(
            texto, _resto(texto, *parcial.span()), NumeroNaConsulta(digitos, completo=False)
        )
    return ConsultaAnalisada(texto, texto, None)
