"""Decodificação e limpeza de texto comum às fontes (F1-18, ARCHITECTURE.md, seção 5).

O ``texto`` do DJEN é HTML com entidades nomeadas (``&Atilde;``), numéricas (``&#227;``) e,
às vezes, escapadas duas vezes (``&amp;Atilde;``). O parser de HTML resolve o primeiro nível;
:func:`decodificar` resolve o que sobrar nos nós de texto.
"""

import html
import re
import unicodedata

# Entidade que sobrou depois de uma passada: nomeada, decimal ou hexadecimal.
_ENTIDADE = re.compile(r"&(?:[A-Za-z][A-Za-z0-9]{1,31}|#\d{1,7}|#[xX][0-9A-Fa-f]{1,6});")
# Caracteres de controle (categoria Cc), exceto quebra de linha e tabulação.
_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_ESPACOS = re.compile(r"[^\S\n]+")
_LINHAS_VAZIAS = re.compile(r"\n{3,}")
# Hifenização de quebra de linha: só entre letras minúsculas ("indeni-\nzação").
_HIFENIZACAO = re.compile(r"(?<=[a-zà-ÿ])-\n(?=[a-zà-ÿ])")


def decodificar(texto: str) -> str:
    """Entidades HTML (com segunda passada só se ainda houver entidades), NFC e sem controles."""
    texto = html.unescape(texto)
    if _ENTIDADE.search(texto):
        texto = html.unescape(texto)
    texto = unicodedata.normalize("NFC", texto)
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    return _CONTROLE.sub("", texto)


def normalizar_espacos(texto: str) -> str:
    """Espaços (inclusive ``&nbsp;``) colapsados, linhas aparadas, sem linhas vazias repetidas."""
    linhas = [_ESPACOS.sub(" ", linha).strip() for linha in texto.split("\n")]
    texto = "\n".join(linhas)
    texto = _HIFENIZACAO.sub("", texto)
    return _LINHAS_VAZIAS.sub("\n\n", texto).strip()


def sem_acentos(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def chave(texto: str) -> str:
    """Forma de comparação: sem acentos, minúsculas, espaços simples."""
    return " ".join(sem_acentos(texto).casefold().split())
