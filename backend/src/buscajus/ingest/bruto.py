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
from collections.abc import Collection, Iterator, Mapping, Sequence
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

        return self._escrever(caminho_relativo, itens)

    def reescrever_sem(
        self, caminho_relativo: str, campo_id: str, ids: Collection[str]
    ) -> ArquivoBruto | None:
        """Regrava o arquivo sem os itens cujo ``campo_id`` está em ``ids`` (F2-13).

        Devolve o arquivo novo, ou ``None`` se o arquivo não existe ou não tinha nenhum deles.
        """
        if not self._resolver(caminho_relativo).exists():
            return None
        alvo = {str(i).lower() for i in ids}
        itens = list(self.ler(caminho_relativo))
        restantes = [i for i in itens if str(i.get(campo_id)).lower() not in alvo]
        if len(restantes) == len(itens):
            return None
        return self._escrever(caminho_relativo, restantes)

    def listar(self, diretorio_relativo: str) -> list[str]:
        """Arquivos brutos de um diretório (relativo), registrados ou não em ``coleta_bruta``."""
        diretorio = self._resolver(diretorio_relativo)
        if not diretorio.is_dir():
            return []
        return sorted(
            f"{diretorio_relativo.rstrip('/')}/{arquivo.name}"
            for arquivo in diretorio.glob("*.jsonl.gz")
        )

    def _escrever(self, caminho_relativo: str, itens: Sequence[Mapping[str, Any]]) -> ArquivoBruto:
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
