"""Mascaramento de CPF (F1-39, ARCHITECTURE.md, seção 6.3).

- O formato ``000.000.000-00`` é **sempre** mascarado.
- Outras grafias com separadores (``000000000-00``, ``000.000.00000``) são mascaradas se o
  dígito verificador for válido.
- 11 dígitos seguidos só são mascarados se não estiverem colados a outros dígitos (para não
  casar pedaços de um número de processo ou CNPJ sem máscara) **e** se o DV for válido.
"""

import re

MASCARA = "***.***.***-**"

_FORMATADO = re.compile(r"(?<![\d.])\d{3}\.\d{3}\.\d{3}-\d{2}(?![\d-])")
_PARCIAL = re.compile(r"(?<![\d.])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?![\d-])")


def dv_valido(cpf: str) -> bool:
    digitos = [int(c) for c in cpf if c.isdigit()]
    if len(digitos) != 11 or len(set(digitos)) == 1:
        return False
    for posicao in (9, 10):
        soma = sum(
            d * peso for d, peso in zip(digitos[:posicao], range(posicao + 1, 1, -1), strict=True)
        )
        if (soma * 10 % 11) % 10 != digitos[posicao]:
            return False
    return True


def _deve_mascarar(trecho: str) -> bool:
    return bool(_FORMATADO.fullmatch(trecho)) or dv_valido(trecho)


def mascarar_cpf(texto: str) -> tuple[str, int]:
    """Devolve o texto com os CPFs mascarados e quantos foram mascarados."""
    contagem = 0

    def trocar(m: re.Match[str]) -> str:
        nonlocal contagem
        if not _deve_mascarar(m.group()):
            return m.group()
        contagem += 1
        return MASCARA

    return _PARCIAL.sub(trocar, texto), contagem


def tem_cpf(texto: str) -> bool:
    """Invariante: sobrou algum CPF sem máscara?"""
    return any(_deve_mascarar(m.group()) for m in _PARCIAL.finditer(texto))
