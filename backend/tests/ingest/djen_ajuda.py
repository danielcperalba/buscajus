"""Apoio aos testes do conector DJEN: rotas respx com as fixtures sintéticas."""

import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import respx

from buscajus.core.config import ConfigDjen
from buscajus.ingest.anonimizacao import Rejeicao
from buscajus.ingest.djen.campos import LISTA_BRANCA
from fixtures.djen import PASTA, dados

URL_API = "https://comunicaapi.exemplo"
DIA = date.fromisoformat(dados.DATA)
DIA_SEM_EMENTAS = date.fromisoformat(dados.DATA_SEM_EMENTAS)
HOJE = date(2026, 10, 20)


def config_djen(**alteracoes: Any) -> ConfigDjen:
    return ConfigDjen(url_api=URL_API, **alteracoes)


def ler_json(nome: str) -> Any:
    return json.loads((PASTA / nome).read_text(encoding="utf-8"))


def url_metadados(data: date, tribunal: str = dados.TRIBUNAL) -> str:
    return f"{URL_API}/api/v1/caderno/{tribunal}/{data.isoformat()}/D"


def servir_caderno(
    roteador: respx.MockRouter, data: date, versao: int = 1, *, metadados: str | None = None
) -> respx.Route:
    """Metadados + ZIP de um dia. Devolve a rota do ZIP."""
    meta = ler_json(metadados or f"metadados-{data.isoformat()}-v{versao}.json")
    roteador.get(url_metadados(data)).respond(200, json=meta)
    conteudo = (PASTA / f"caderno-{data.isoformat()}-v{versao}.zip").read_bytes()
    return roteador.get(meta["url"]).respond(200, content=conteudo)


class AnonimizadorFalso:
    """Só aplica a lista branca; registra os ids que viu. Não substitui nomes."""

    def __init__(self, rejeitar: set[int] | None = None, falhar_em: int | None = None) -> None:
        self.vistos: list[int] = []
        self._rejeitar = rejeitar or set()
        self._falhar_em = falhar_em

    def __call__(self, item: Mapping[str, Any]) -> dict[str, Any] | Rejeicao:
        self.vistos.append(item["id"])
        if item["id"] == self._falhar_em:
            raise RuntimeError("falha no anonimizador")
        if item["id"] in self._rejeitar:
            return Rejeicao(str(item["id"]), "nome de destinatário restante")
        return {k: v for k, v in item.items() if k in LISTA_BRANCA} | {
            "anonimizacao_versao": "falso",
            "anonimizacao_substituicoes": 0,
        }


def resposta_429() -> httpx.Response:
    return httpx.Response(429, json=ler_json("erro-429.json"))


def area_vazia(diretorio: Path) -> bool:
    return not diretorio.exists() or not any(diretorio.iterdir())
