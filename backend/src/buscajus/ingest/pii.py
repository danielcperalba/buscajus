"""Verificação de PII residual na ementa normalizada (F1-24, ARCHITECTURE.md, seção 6.4).

Última rede, depois da anonimização. Conservadora: prefere falso positivo, porque o
acórdão só vai para a quarentena (não indexado nem exibido) até a revisão manual.
Devolve só os **tipos** encontrados, nunca os trechos.
"""

import re

from buscajus.ingest.anonimizacao.cpf import tem_cpf
from buscajus.ingest.anonimizacao.documentos import tem_documento

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.IGNORECASE)
_TELEFONE = re.compile(
    r"\(\s*\d{2}\s*\)\s*9?\d{4}[-\s.]?\d{4}(?!\d)"
    r"|(?<!\d)\+55\s*\d{2}\s*9?\d{4}[-\s.]?\d{4}(?!\d)"
    r"|\b(?:telefone|tel\.|fone|celular|whatsapp)\s*:?\s*\d{4,5}[-\s.]?\d{4}(?!\d)",
    re.IGNORECASE,
)
_OAB = re.compile(
    r"\bOAB\s*(?:/\s*[A-Z]{2}|-[A-Z]{2}|\s[A-Z]{2}\b)?\s*(?:n\.?\s*[ºo°]?\.?\s*)?\d{1,3}\.?\d{3}"
    r"|\bOAB\s*(?:n\.?\s*[ºo°]?\.?\s*)?\d{3,6}\s*/\s*[A-Z]{2}\b",
    re.IGNORECASE,
)
_ROTULO_PARTE = re.compile(
    r"(?<![\w])(?:apelante|apelad[oa]|recorrente|recorrid[oa]|agravante|agravad[oa]|"
    r"embargante|embargad[oa]|autor|autora|r[ée]u|r[ée]|requerente|requerid[oa]|"
    r"impetrante|impetrad[oa]|exequente|executad[oa]|interessad[oa]|"
    r"advogad[oa](?:\(a\))?|procurador(?:a|\(a\))?)s?\s*:",
    re.IGNORECASE,
)

VERIFICACOES = (
    ("email", _EMAIL.search),
    ("telefone", _TELEFONE.search),
    ("oab", _OAB.search),
    ("rotulo_parte", _ROTULO_PARTE.search),
)


def verificar_pii(texto: str) -> list[str]:
    """Tipos de PII residual encontrados (vazio se nada)."""
    motivos = [nome for nome, procurar in VERIFICACOES if procurar(texto)]
    if tem_cpf(texto):
        motivos.append("cpf")
    if tem_documento(texto):
        motivos.append("documento")
    return motivos
