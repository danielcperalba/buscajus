"""Apoio aos testes do conector TJDFT: servidor respx com as fixtures sintéticas."""

import copy
import json
from collections.abc import Callable, Mapping
from datetime import date
from typing import Any

import httpx
import respx

from buscajus.core.config import ConfigTjdft
from buscajus.ingest.anonimizacao import Rejeicao
from fixtures.tjdft import carregar, dados

URL_API = "https://jurisdf.exemplo/api/v1/pesquisa"
DIA = date.fromisoformat(dados.DIA)
DIA_VIRADA = date.fromisoformat(dados.DIA_VIRADA)
DIA_REPETIDO = date.fromisoformat(dados.DIA_REPETIDO)
DIA_VAZIO = date.fromisoformat(dados.DIA_VAZIO)
HOJE = date(2026, 10, 20)

Resposta = dict[str, Any] | httpx.Response


def config_tjdft(**alteracoes: Any) -> ConfigTjdft:
    return ConfigTjdft(url_api=URL_API, **alteracoes)


def fixture(dia: date, pagina: int, sufixo: str = "") -> dict[str, Any]:
    return carregar(f"pesquisa-{dia.isoformat()}-p{pagina}{sufixo}.json")


def alterar_registro(
    resposta: dict[str, Any], n: int, mudar: Callable[[dict[str, Any]], None]
) -> dict[str, Any]:
    """Cópia da resposta com o registro ``n`` (dos dados sintéticos) alterado por ``mudar``."""
    nova = copy.deepcopy(resposta)
    alvo = next(r for r in nova["registros"] if r["uuid"].endswith(f"{n:012d}"))
    mudar(alvo)
    return nova


class ServidorTjdft:
    """Responde ao POST da pesquisa pela data e página do corpo.

    Cada (data, página) tem uma fila de respostas; a última se repete. Sem resposta
    configurada, devolve a fixture da pasta.
    """

    def __init__(self, roteador: respx.MockRouter) -> None:
        self.pedidos: list[tuple[str, int]] = []
        self.corpos: list[dict[str, Any]] = []
        self._respostas: dict[tuple[str, int], list[Resposta]] = {}
        roteador.post(URL_API).mock(side_effect=self._responder)

    def servir(self, dia: date, pagina: int, *respostas: Resposta) -> None:
        self._respostas[(dia.isoformat(), pagina)] = list(respostas)

    def _responder(self, pedido: httpx.Request) -> httpx.Response:
        corpo = json.loads(pedido.content)
        self.corpos.append(corpo)
        termos = {t["campo"]: t["valor"] for t in corpo["termosAcessorios"]}
        chave = (termos["dataPublicacao"], corpo["pagina"])
        self.pedidos.append(chave)
        fila = self._respostas.get(chave)
        if fila is None:
            resposta: Resposta = carregar(f"pesquisa-{chave[0]}-p{chave[1]}.json")
        else:
            resposta = fila.pop(0) if len(fila) > 1 else fila[0]
        if isinstance(resposta, httpx.Response):
            return resposta
        return httpx.Response(200, json=resposta)


class AnonimizadorFalso:
    """Não substitui nada; registra os uuids que viu e pode recusar alguns."""

    versao = "falso"

    def __init__(self, rejeitar: set[str] | None = None) -> None:
        self.vistos: list[str] = []
        self._rejeitar = rejeitar or set()

    def __call__(self, item: Mapping[str, Any]) -> dict[str, Any] | Rejeicao:
        self.vistos.append(item["uuid"])
        if item["uuid"] in self._rejeitar:
            return Rejeicao(item["uuid"], "CPF restante")
        return dict(item) | {"anonimizacao_versao": self.versao, "anonimizacao_substituicoes": 0}


def uuid(n: int) -> str:
    return f"0f1c7e00-2099-4000-8000-{n:012d}"
