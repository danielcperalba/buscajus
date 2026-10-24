"""Área temporária dos cadernos (``tmp-cadernos``, tmpfs no worker).

O ZIP do caderno tem nomes de partes de todas as comunicações do dia: só existe aqui, é
apagado ao fim do processamento (inclusive em erro) e os órfãos são apagados quando o worker
inicia (ARCHITECTURE.md, seção 6.2).
"""

import logging
import shutil
import uuid
from pathlib import Path

log = logging.getLogger(__name__)


def preparar(diretorio: Path) -> Path:
    diretorio.mkdir(parents=True, exist_ok=True, mode=0o700)
    return diretorio


def novo_arquivo(diretorio: Path, prefixo: str) -> Path:
    return preparar(diretorio) / f"{prefixo}-{uuid.uuid4().hex}.zip"


def limpar_orfaos(diretorio: Path) -> int:
    """Apaga tudo o que estiver na área temporária e devolve quantos itens foram apagados."""
    if not diretorio.exists():
        return 0
    apagados = 0
    for caminho in diretorio.iterdir():
        if caminho.is_dir() and not caminho.is_symlink():
            shutil.rmtree(caminho)
        else:
            caminho.unlink(missing_ok=True)
        apagados += 1
    if apagados:
        log.warning("arquivos órfãos apagados da área temporária", extra={"apagados": apagados})
    return apagados
