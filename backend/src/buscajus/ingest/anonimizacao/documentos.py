"""Mascaramento de documentos de identificação (F1-41, ARCHITECTURE.md, seção 6.3).

Cobre RG/identidade, CNH, título de eleitor, PIS/PASEP/NIS/NIT, CTPS e passaporte. O CPF tem
regra própria (``anonimizacao.cpf``, F1-39).

Ao contrário do CPF, esses números não têm formato próprio que os distinga de números de
processo, leis, artigos, valores ou datas. Por isso **só se mascara o número que vem logo depois
da palavra-chave** do documento ("RG", "R.G.", "identidade", "CNH", "título eleitoral"…),
com no máximo o órgão emissor e um conector ("nº", "n.", "número", "sob o nº", ":") entre
eles. A palavra-chave fica no texto e o número vira ``***``. Como defesa extra, um número no
formato CNJ de processo ou de CNPJ nunca é mascarado, nem um número com menos de 5 dígitos.

E-mail, telefone e OAB não são mascarados: caem na quarentena (``ingest.pii``, F1-24).
"""

import re

MASCARA = "***"

# Siglas: só em maiúsculas e fora de palavras ("AgRg"/"AGRG" não são RG).
_SIGLAS = {
    "rg": r"(?<![A-Za-z])(?:RG|R\.\s?G\.|C\.I\.)(?![A-Za-z])",
    "cnh": r"(?<![A-Za-z])CNH(?![A-Za-z])",
    "pis": r"(?<![A-Za-z])(?:PIS\s*/\s*PASEP|PIS|PASEP|NIS|NIT)(?![A-Za-z])",
    "ctps": r"(?<![A-Za-z])CTPS(?![A-Za-z])",
}
# Por extenso, em qualquer caixa. "Habilitação" e "título" sozinhos não contam (habilitação
# de crédito, título executivo).
_EXTENSO = {
    "rg": r"\b(?:(?:carteira|c[ée]dula|documento)\s+de\s+)?identidade\b",
    "cnh": r"\bcarteira\s+(?:nacional\s+)?de\s+habilita[çc][ãa]o\b",
    "titulo_eleitor": r"\bt[íi]tulo\s+(?:de\s+)?eleitor(?:al)?\b|\binscri[çc][ãa]o\s+eleitoral\b",
    "ctps": r"\bcarteira\s+de\s+trabalho(?:\s+e\s+previd[êe]ncia\s+social)?\b",
    "passaporte": r"\bpassaporte\b",
}

# Entre a palavra-chave e o número: órgão emissor opcional ("RG/SSP-PR") e um conector.
_EMISSOR = r"(?:\s*/\s*[A-Z]{2,6}(?:\s*[-/]\s*[A-Z]{2})?)?"
_CONECTOR = (
    r"(?:\s*[:,–-])?\s*"
    r"(?:(?:sob\s+o\s+)?(?:n[º°o]|n\.[º°o]?|n[uú]m(?:ero)?\.?)\s*[:.]?\s*)?"
)
# O número: grupos de dígitos com separadores simples, com letras do emissor antes (MG-) ou
# no começo do passaporte (FT123456) e dígito X no fim do RG.
_NUMERO = r"(?P<numero>(?:[A-Za-z]{1,3}-?)?\d+(?:[.\-/ ]\d+)*(?:-?[Xx])?)(?![\dA-Za-z])"
# CTPS: a série também identifica.
_SERIE = r"(?P<serie>,?\s*s[ée]rie\s*(?:n[º°o.]?\s*)?\d+(?:\s*[-/]\s*[A-Z]{2})?)?"


def _padrao(tipo: str, chave: str, flags: int = 0) -> re.Pattern[str]:
    serie = _SERIE if tipo == "ctps" else ""
    return re.compile(rf"(?P<chave>{chave}){_EMISSOR}{_CONECTOR}{_NUMERO}{serie}", flags)


_PADROES = [
    *(_padrao(tipo, chave) for tipo, chave in _SIGLAS.items()),
    *(_padrao(tipo, chave, re.IGNORECASE) for tipo, chave in _EXTENSO.items()),
]

_PROCESSO_CNJ = re.compile(r"\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}")
_CNPJ = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")
_MINIMO_DIGITOS = 5


def _e_documento(numero: str) -> bool:
    if sum(c.isdigit() for c in numero) < _MINIMO_DIGITOS:
        return False
    return not (_PROCESSO_CNJ.fullmatch(numero) or _CNPJ.fullmatch(numero))


def _ocorrencias(texto: str) -> list[tuple[int, int]]:
    """(início, fim) de cada trecho a mascarar: o número e, na CTPS, a série."""
    trechos: list[tuple[int, int]] = []
    for padrao in _PADROES:
        for m in padrao.finditer(texto):
            if not _e_documento(m.group("numero")):
                continue
            trechos.append((m.start("numero"), m.end("numero")))
            if "serie" in padrao.groupindex and m.group("serie"):
                serie = re.search(r"\d+(?:\s*[-/]\s*[A-Z]{2})?$", m.group("serie"))
                if serie:
                    trechos.append((m.start("serie") + serie.start(), m.end("serie")))
    # Sem sobreposição (o mesmo número pode casar em mais de um padrão).
    escolhidos: list[tuple[int, int]] = []
    for trecho in sorted(trechos):
        if escolhidos and trecho[0] < escolhidos[-1][1]:
            continue
        escolhidos.append(trecho)
    return escolhidos


def mascarar_documentos(texto: str) -> tuple[str, int]:
    """Texto com os números de documentos mascarados e quantos trechos foram mascarados."""
    trechos = _ocorrencias(texto)
    if not trechos:
        return texto, 0
    partes: list[str] = []
    ultimo = 0
    for inicio, fim in trechos:
        partes += [texto[ultimo:inicio], MASCARA]
        ultimo = fim
    partes.append(texto[ultimo:])
    return "".join(partes), len(trechos)


def tem_documento(texto: str) -> bool:
    """Invariante: sobrou algum número de documento sem máscara?"""
    return bool(_ocorrencias(texto))
