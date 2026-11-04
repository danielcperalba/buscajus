"""Caderno diário do DJEN: metadados, download, SHA-256 e leitura do ZIP.

A URL temporária do ZIP é sensível (dá acesso ao caderno inteiro, com nomes de partes) e
nunca é gravada nem logada; por isso fica fora do ``repr`` dos metadados.
"""

import hashlib
import io
import json
import logging
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import IO, Any

import httpx

from buscajus.ingest.conector import ErroColeta
from buscajus.ingest.http import ClienteHttp

log = logging.getLogger(__name__)

STATUS_PRONTO = "Processado"
STATUS_SEM_COMUNICACOES = "Sem comunicações"
STATUS_NAO_PRONTO = frozenset({"Não Processado", "Em processamento"})
STATUS_CANCELADO = "Cancelado"

# Cada arquivo do ZIP tem até 1.000 comunicações (poucos MB). A leitura é em streaming, uma
# comunicação por vez, então o tamanho do arquivo não pesa na memória nem no tmpfs (nada é
# descompactado em disco). O limite só barra uma bomba de descompressão: 4 GB descompactados
# num arquivo (o caderno inteiro tem até 1 GB compactado; o de 163 MB do F1-01 tinha 887 MB
# descompactados). Acima do alerta, o nome e o tamanho da entrada vão para o log.
LIMITE_BYTES_ENTRADA = 4 * 1024 * 1024 * 1024
ALERTA_BYTES_ENTRADA = 64 * 1024 * 1024
# Uma comunicação sozinha (texto com imagens embutidas, por exemplo): é o que fica em memória.
LIMITE_CARACTERES_ITEM = 256 * 1024 * 1024
BLOCO_LEITURA = 1024 * 1024
# Formato dos arquivos internos ({SIGLA}-D-{AAAA-MM-DD}_{n}.json): só nomes assim vão para o
# log e para a mensagem de erro.
NOME_ENTRADA = re.compile(r"[A-Z0-9]{2,12}-D-\d{4}-\d{2}-\d{2}_\d{1,6}\.json")


@dataclass(frozen=True)
class MetadadosDjen:
    versao: int
    hash: str
    status: str
    total: int | None
    url: str = field(repr=False)


def obter_metadados(
    cliente: ClienteHttp, url_api: str, tribunal: str, data: date
) -> MetadadosDjen | None:
    """Metadados do caderno; ``None`` se não houver caderno no dia (HTTP 404)."""
    resposta = cliente.requisitar(
        "GET",
        f"{url_api}/api/v1/caderno/{tribunal}/{data.isoformat()}/D",
        rotulo="metadados do caderno",
    )
    if resposta.status_code == httpx.codes.NOT_FOUND:
        return None
    if resposta.status_code != httpx.codes.OK:
        raise ErroColeta(f"metadados do caderno: HTTP {resposta.status_code}")
    try:
        corpo = resposta.json()
    except ValueError as exc:
        raise ErroColeta("metadados do caderno não são JSON") from exc
    return _metadados(corpo)


def _metadados(corpo: Any) -> MetadadosDjen:
    if not isinstance(corpo, dict):
        raise ErroColeta("metadados do caderno em formato inesperado")
    versao, hash_, status = corpo.get("versao"), corpo.get("hash"), corpo.get("status")
    total = corpo.get("total_comunicacoes", corpo.get("total"))
    url = corpo.get("url")
    if not isinstance(versao, int) or isinstance(versao, bool):
        raise ErroColeta("metadados do caderno: campo versao ausente ou inválido")
    if not isinstance(hash_, str) or not isinstance(status, str):
        raise ErroColeta("metadados do caderno: campo hash ou status ausente ou inválido")
    if total is not None and (not isinstance(total, int) or isinstance(total, bool)):
        raise ErroColeta("metadados do caderno: campo total_comunicacoes inválido")
    return MetadadosDjen(
        versao=versao,
        hash=hash_.strip().lower(),
        status=status.strip(),
        total=total,
        url=url if isinstance(url, str) else "",
    )


def sha256_arquivo(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def _nome_seguro(nome: str) -> str:
    """Nome da entrada para o diagnóstico, só se tiver o formato esperado (sem dado pessoal)."""
    return nome if NOME_ENTRADA.fullmatch(nome) else "(nome fora do padrão)"


def _megabytes(tamanho: int) -> str:
    return f"{tamanho / (1024 * 1024):.1f} MB"


def ler_comunicacoes(caminho: Path) -> Iterator[dict[str, Any]]:
    """Percorre as comunicações do ZIP, um arquivo interno por vez, em streaming.

    Cada arquivo é ``{"count": n, "items": [...]}`` e é lido uma comunicação por vez
    (:class:`_LeitorPagina`), sem carregar o arquivo inteiro em memória. Entradas acima de
    ``ALERTA_BYTES_ENTRADA`` são registradas no log (nome e tamanho); acima de
    ``LIMITE_BYTES_ENTRADA``, o caderno vira erro com o mesmo diagnóstico. As demais mensagens
    de erro não trazem nomes de arquivos internos nem conteúdo.
    """
    try:
        with zipfile.ZipFile(caminho) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if not info.filename.endswith(".json"):
                    raise ErroColeta("caderno com entrada que não é JSON")
                if info.file_size > LIMITE_BYTES_ENTRADA:
                    raise ErroColeta(
                        f"caderno com entrada maior que o limite de "
                        f"{_megabytes(LIMITE_BYTES_ENTRADA)} ({_nome_seguro(info.filename)}: "
                        f"{_megabytes(info.file_size)} descompactado, "
                        f"{_megabytes(info.compress_size)} no ZIP)"
                    )
                if info.file_size > ALERTA_BYTES_ENTRADA:
                    log.warning(
                        "entrada grande no caderno",
                        extra={
                            "entrada": _nome_seguro(info.filename),
                            "bytes": info.file_size,
                            "bytes_zip": info.compress_size,
                        },
                    )
                with (
                    zf.open(info) as binario,
                    io.TextIOWrapper(binario, encoding="utf-8-sig") as arquivo,
                ):
                    yield from _LeitorPagina(arquivo).itens()
    except zipfile.BadZipFile as exc:
        raise ErroColeta("arquivo do caderno não é um ZIP válido") from exc


_DECODIFICADOR = json.JSONDecoder()
_ESPACOS = frozenset(" \t\n\r")


class _LeitorPagina:
    """Lê ``{"count": n, "items": [...]}`` devolvendo um item por vez.

    Guarda em memória só o trecho ainda não consumido: no máximo uma comunicação (limitada a
    ``LIMITE_CARACTERES_ITEM``) mais um bloco de leitura.
    """

    def __init__(self, arquivo: IO[str]) -> None:
        self._arquivo = arquivo
        self._buffer = ""
        self._pos = 0
        self._fim = False

    def _ler(self, tamanho: int) -> bool:
        if self._fim:
            return False
        try:
            bloco = self._arquivo.read(tamanho)
        except UnicodeDecodeError as exc:
            raise ErroColeta("caderno com entrada JSON inválida") from exc
        if not bloco:
            self._fim = True
            return False
        self._buffer = self._buffer[self._pos :] + bloco
        self._pos = 0
        return True

    def _proximo(self) -> str:
        """Próximo caractere que não é espaço, sem consumi-lo ("" no fim do arquivo)."""
        while True:
            while self._pos < len(self._buffer) and self._buffer[self._pos] in _ESPACOS:
                self._pos += 1
            if self._pos < len(self._buffer):
                return self._buffer[self._pos]
            if not self._ler(BLOCO_LEITURA):
                return ""

    def _consumir(self, esperado: str) -> None:
        if self._proximo() != esperado:
            raise ErroColeta("caderno com entrada JSON inválida")
        self._pos += 1

    def _valor(self) -> Any:
        self._proximo()
        tamanho = BLOCO_LEITURA
        while True:
            try:
                valor, fim = _DECODIFICADOR.raw_decode(self._buffer, self._pos)
            except ValueError:
                pass
            else:
                # Um número no fim do buffer pode estar cortado ("12" de "123").
                if fim < len(self._buffer) or self._fim:
                    self._pos = fim
                    return valor
            if len(self._buffer) - self._pos > LIMITE_CARACTERES_ITEM:
                raise ErroColeta(
                    "caderno com comunicação maior que o limite de "
                    f"{_megabytes(LIMITE_CARACTERES_ITEM)} de texto"
                )
            if not self._ler(tamanho):
                raise ErroColeta("caderno com entrada JSON inválida")
            tamanho *= 2  # leituras crescentes: uma comunicação grande não é relida N vezes

    def itens(self) -> Iterator[dict[str, Any]]:
        if self._proximo() != "{":
            raise ErroColeta("caderno com entrada sem a lista items")
        self._pos += 1
        achou = False
        while self._proximo() != "}":
            chave = self._valor()
            if not isinstance(chave, str):
                raise ErroColeta("caderno com entrada JSON inválida")
            self._consumir(":")
            if chave == "items":
                if self._proximo() != "[":
                    raise ErroColeta("caderno com entrada sem a lista items")
                achou = True
                yield from self._lista()
            else:
                self._valor()
            if self._proximo() != ",":
                break
            self._pos += 1
        self._consumir("}")
        if self._proximo() != "":
            raise ErroColeta("caderno com entrada JSON inválida")
        if not achou:
            raise ErroColeta("caderno com entrada sem a lista items")

    def _lista(self) -> Iterator[dict[str, Any]]:
        self._consumir("[")
        if self._proximo() == "]":
            self._pos += 1
            return
        while True:
            item = self._valor()
            if not isinstance(item, dict):
                raise ErroColeta("caderno com comunicação que não é objeto")
            yield item
            separador = self._proximo()
            if separador not in (",", "]"):
                raise ErroColeta("caderno com entrada JSON inválida")
            self._pos += 1
            if separador == "]":
                return
