"""Descrição de erros segura para logs e para o banco.

Exceções genéricas (``ValueError``, ``KeyError``, erros do lxml…) podem carregar trechos do
conteúdo processado na mensagem. Por isso só as subclasses de :class:`ErroSeguro`, cujas
mensagens o próprio código controla, têm a mensagem registrada; das demais ficam só o tipo
e o local de origem.
"""

import traceback
from pathlib import Path

TAMANHO_MAXIMO = 500


class ErroSeguro(Exception):
    """Erro cuja mensagem nunca contém conteúdo de comunicações, ementas ou URLs sensíveis."""


def descrever_erro(exc: BaseException) -> str:
    if isinstance(exc, ErroSeguro):
        return f"{type(exc).__name__}: {exc}"[:TAMANHO_MAXIMO]
    quadros = traceback.extract_tb(exc.__traceback__)
    if not quadros:
        return type(exc).__name__
    origem = quadros[-1]
    return f"{type(exc).__name__} em {Path(origem.filename).name}:{origem.lineno}"
