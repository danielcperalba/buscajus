"""Caderno diário do DJEN: metadados, download, SHA-256 e leitura do ZIP.

A URL temporária do ZIP é sensível (dá acesso ao caderno inteiro, com nomes de partes) e
nunca é gravada nem logada; por isso fica fora do ``repr`` dos metadados.
"""

import hashlib
import json
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from buscajus.ingest.conector import ErroColeta
from buscajus.ingest.http import ClienteHttp

STATUS_PRONTO = "Processado"
STATUS_SEM_COMUNICACOES = "Sem comunicações"
STATUS_NAO_PRONTO = frozenset({"Não Processado", "Em processamento"})
STATUS_CANCELADO = "Cancelado"

# Cada arquivo do ZIP tem até 1.000 comunicações (poucos MB); acima disso, algo está errado.
LIMITE_BYTES_ENTRADA = 64 * 1024 * 1024


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


def ler_comunicacoes(caminho: Path) -> Iterator[dict[str, Any]]:
    """Percorre as comunicações do ZIP, um arquivo interno por vez.

    Cada arquivo é ``{"count": n, "items": [...]}``. As mensagens de erro não trazem nomes
    de arquivos internos nem conteúdo.
    """
    try:
        with zipfile.ZipFile(caminho) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if not info.filename.endswith(".json"):
                    raise ErroColeta("caderno com entrada que não é JSON")
                if info.file_size > LIMITE_BYTES_ENTRADA:
                    raise ErroColeta("caderno com entrada maior que o limite")
                with zf.open(info) as arquivo:
                    try:
                        pagina = json.load(arquivo)
                    except ValueError as exc:
                        raise ErroColeta("caderno com entrada JSON inválida") from exc
                itens = pagina.get("items") if isinstance(pagina, dict) else None
                if not isinstance(itens, list):
                    raise ErroColeta("caderno com entrada sem a lista items")
                for item in itens:
                    if not isinstance(item, dict):
                        raise ErroColeta("caderno com comunicação que não é objeto")
                    yield item
    except zipfile.BadZipFile as exc:
        raise ErroColeta("arquivo do caderno não é um ZIP válido") from exc
