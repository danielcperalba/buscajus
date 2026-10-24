"""Armazenamento bruto filtrado (ARCHITECTURE.md, seções 3.1 e 6.2).

Guarda, em JSONL.gz, só os itens aceitos, já anonimizados e com a lista branca de campos
aplicada. Este módulo não filtra nada: um item com campo fora da lista branca indica que
uma etapa anterior falhou, e a gravação é recusada inteira (falha fechada).

Layout, relativo a ``diretorio_raw``:

- DJEN: ``djen/{tribunal}/{data}/v{versao}.jsonl.gz`` (um arquivo por versão do caderno);
- fontes paginadas: ``{fonte}/{tribunal}/{data}/p{pagina:05d}.jsonl.gz``.
"""

import gzip
import hashlib
import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

from buscajus.core.erros import ErroSeguro


class ErroListaBranca(ErroSeguro):
    """Item com campo fora da lista branca; a mensagem traz só os nomes dos campos."""


@dataclass(frozen=True)
class ArquivoBruto:
    caminho_relativo: str
    sha256: str
    bytes: int
    itens: int


def caminho_caderno(tribunal: str, data: date, versao: int) -> str:
    return f"djen/{tribunal}/{data.isoformat()}/v{versao}.jsonl.gz"


def caminho_pagina(fonte: str, tribunal: str, data: date, pagina: int) -> str:
    return f"{fonte}/{tribunal}/{data.isoformat()}/p{pagina:05d}.jsonl.gz"


class ArmazenamentoBruto:
    def __init__(self, raiz: Path) -> None:
        self._raiz = raiz

    def gravar(
        self,
        caminho_relativo: str,
        itens: Sequence[Mapping[str, Any]],
        lista_branca: frozenset[str],
    ) -> ArquivoBruto:
        fora = sorted({campo for item in itens for campo in item} - lista_branca)
        if fora:
            raise ErroListaBranca(f"campos fora da lista branca: {', '.join(fora)}")

        destino = self._resolver(caminho_relativo)
        destino.parent.mkdir(parents=True, exist_ok=True)
        conteudo = _jsonl_gz(itens)
        # Escrita atômica: um arquivo nunca fica pela metade no lugar definitivo.
        temporario = destino.with_name(f".{destino.name}.tmp")
        temporario.write_bytes(conteudo)
        temporario.replace(destino)
        return ArquivoBruto(
            caminho_relativo=caminho_relativo,
            sha256=hashlib.sha256(conteudo).hexdigest(),
            bytes=len(conteudo),
            itens=len(itens),
        )

    def ler(self, caminho_relativo: str) -> Iterator[dict[str, Any]]:
        with gzip.open(self._resolver(caminho_relativo), "rt", encoding="utf-8") as arquivo:
            for linha in arquivo:
                yield json.loads(linha)

    def _resolver(self, caminho_relativo: str) -> Path:
        relativo = PurePosixPath(caminho_relativo)
        if relativo.is_absolute() or ".." in relativo.parts:
            raise ValueError("caminho do bruto deve ser relativo ao diretório raw")
        return self._raiz.joinpath(*relativo.parts)


def _jsonl_gz(itens: Sequence[Mapping[str, Any]]) -> bytes:
    linhas = "".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for item in itens
    )
    # mtime fixo: o mesmo conteúdo gera sempre o mesmo sha256.
    return gzip.compress(linhas.encode("utf-8"), mtime=0)
