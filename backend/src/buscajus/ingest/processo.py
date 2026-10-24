"""Número de processo no padrão CNJ (F1-21, ARCHITECTURE.md, seção 5.2).

``NNNNNNN-DD.AAAA.J.TR.OOOO``; dígito verificador pela Res. CNJ 65/2008:
``DD = 98 − (NNNNNNNAAAAJTROOOO00 mod 97)``. Número com DV inválido é aceito, mas marcado.
"""

from dataclasses import dataclass

from buscajus.core.erros import ErroSeguro


class NumeroProcessoInvalido(ErroSeguro):
    pass


@dataclass(frozen=True)
class NumeroProcesso:
    digitos: str
    mascara: str
    valido: bool


def digito_verificador(sequencial: str, ano: str, justica: str, tribunal: str, origem: str) -> int:
    return 98 - int(f"{sequencial}{ano}{justica}{tribunal}{origem}00") % 97


def normalizar_numero(valor: str) -> NumeroProcesso:
    """Só dígitos, máscara CNJ e validação do DV. Exige 20 dígitos."""
    digitos = "".join(c for c in valor if c.isdigit())
    if len(digitos) != 20:
        raise NumeroProcessoInvalido(f"número de processo com {len(digitos)} dígitos (esperado 20)")
    n, dd, aaaa, j, tr, oooo = (
        digitos[:7],
        digitos[7:9],
        digitos[9:13],
        digitos[13],
        digitos[14:16],
        digitos[16:],
    )
    valido = int(dd) == digito_verificador(n, aaaa, j, tr, oooo)
    return NumeroProcesso(digitos, f"{n}-{dd}.{aaaa}.{j}.{tr}.{oooo}", valido)
