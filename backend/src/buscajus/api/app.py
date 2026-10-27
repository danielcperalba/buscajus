import json
from collections.abc import Callable
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, Path, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import Engine

from buscajus import __version__
from buscajus.api.consulta import MAXIMO_CONSULTA, analisar_consulta
from buscajus.api.esquemas import (
    LIMITE_RESULTADOS,
    POR_PAGINA,
    AcordaosDoProcesso,
    DetalheAcordao,
    Erro,
    Filtros,
    FiltrosBusca,
    Indisponivel,
    PedidoRemocao,
    Relator,
    RemocaoRecebida,
    RespostaBusca,
)
from buscajus.api.limite import LimitadorJanela, ip_do_cliente, verificar
from buscajus.api.mock import ServicoMock
from buscajus.api.servico import ErroApi, ServicoBusca
from buscajus.busca.servico import ServicoPostgres
from buscajus.core.config import Config, obter_config
from buscajus.core.logging import configurar_logging
from buscajus.db.engine import banco_disponivel, obter_engine

Estado = Literal["ok", "erro"]
MAXIMO_PAGINAS = LIMITE_RESULTADOS // POR_PAGINA
# Prefixo mínimo do número do processo: NNNNNNN-DD (seção 8.2).
MINIMO_DIGITOS_PROCESSO = 9


class Saude(BaseModel):
    status: Estado
    banco: Estado
    versao: str


def _erros(*codigos: int) -> dict[int | str, dict[str, object]]:
    return {codigo: {"model": Erro} for codigo in codigos}


rotas = APIRouter(prefix="/api/v1")


def obter_servico(request: Request) -> ServicoBusca:
    servico: ServicoBusca = request.app.state.servico
    return servico


Servico = Annotated[ServicoBusca, Depends(obter_servico)]


def _limite(nome: str) -> Callable[[Request], None]:
    """Dependência que conta o pedido no limitador ``nome`` do IP do cliente (F4-13)."""

    def verificar_limite(request: Request) -> None:
        config: Config = request.app.state.config
        ip = ip_do_cliente(request, confiar_x_forwarded_for=config.api.confiar_x_forwarded_for)
        verificar(request.app.state.limitadores[nome], ip)

    return verificar_limite


LimiteConsulta = Depends(_limite("consulta"))
LimiteRemocao = Depends(_limite("remocao"))


@rotas.get("/saude")
def saude(response: Response, engine: Annotated[Engine, Depends(obter_engine)]) -> Saude:
    banco: Estado = "ok" if banco_disponivel(engine) else "erro"
    if banco == "erro":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return Saude(status=banco, banco=banco, versao=__version__)


@rotas.get("/busca", responses=_erros(422, 429), dependencies=[LimiteConsulta])
def buscar(
    servico: Servico,
    q: Annotated[str, Query(min_length=1, max_length=MAXIMO_CONSULTA * 2)],
    tribunal: str | None = None,
    orgao: str | None = None,
    classe: Annotated[int | None, Query(description="Código da classe na TPU")] = None,
    relator: Annotated[str | None, Query(description="relator_chave (ver /relatores)")] = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    pagina: Annotated[int, Query(ge=1, le=MAXIMO_PAGINAS)] = 1,
) -> RespostaBusca:
    """Busca híbrida, ou por número de processo quando a consulta é um número (F4-02)."""
    consulta = analisar_consulta(q)
    if not consulta.original:
        raise ErroApi(422, "consulta_vazia", "informe o que procurar")
    if data_inicio and data_fim and data_inicio > data_fim:
        raise ErroApi(422, "periodo_invalido", "data_inicio depois de data_fim")
    filtros = FiltrosBusca(
        tribunal=tribunal,
        orgao=orgao,
        classe=classe,
        relator=relator,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )
    return servico.buscar(consulta, filtros, pagina)


@rotas.get(
    "/acordaos/{acordao_id}",
    responses={**_erros(404, 429), 410: {"model": Indisponivel}},
    dependencies=[LimiteConsulta],
)
def detalhe(servico: Servico, acordao_id: Annotated[int, Path(ge=1)]) -> DetalheAcordao:
    """Detalhe; 410 para cancelado ou removido, 404 para inexistente ou em quarentena."""
    resultado = servico.detalhe(acordao_id)
    if resultado is None:
        raise ErroApi(404, "nao_encontrado", "acórdão não encontrado")
    if isinstance(resultado, Indisponivel):
        raise _Indisponivel(resultado)
    return resultado


@rotas.get("/processos/{numero}", responses=_erros(404, 422, 429), dependencies=[LimiteConsulta])
def processo(servico: Servico, numero: Annotated[str, Path(max_length=40)]) -> AcordaosDoProcesso:
    """Acórdãos de um processo, com ou sem máscara (prefixo a partir de NNNNNNN-DD)."""
    digitos = "".join(c for c in numero if c.isdigit())
    if not MINIMO_DIGITOS_PROCESSO <= len(digitos) <= 20:
        raise ErroApi(422, "numero_invalido", "use o número CNJ, com ou sem máscara")
    resultado = servico.processo(digitos)
    if resultado is None:
        raise ErroApi(404, "nao_encontrado", "nenhum acórdão para este processo")
    return resultado


@rotas.get("/filtros", responses=_erros(429), dependencies=[LimiteConsulta])
def filtros(servico: Servico) -> Filtros:
    return servico.filtros()


@rotas.get("/relatores", responses=_erros(429), dependencies=[LimiteConsulta])
def relatores(
    servico: Servico, prefixo: Annotated[str, Query(min_length=2, max_length=100)]
) -> list[Relator]:
    return servico.relatores(prefixo)


@rotas.post("/remocao", status_code=201, responses=_erros(422, 429), dependencies=[LimiteRemocao])
def remocao(servico: Servico, pedido: PedidoRemocao) -> RemocaoRecebida:
    """Pedido de remoção (canal da seção 6.5)."""
    return servico.registrar_remocao(pedido)


class _Indisponivel(Exception):
    def __init__(self, corpo: Indisponivel) -> None:
        self.corpo = corpo


def openapi_json(app: FastAPI) -> str:
    """OpenAPI como versionado em ``frontend/openapi.json`` (``buscajus api openapi``)."""
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"


def criar_app() -> FastAPI:
    config = obter_config()
    configurar_logging(config.nivel_log)
    app = FastAPI(title="BuscaJus", version=__version__)
    app.state.config = config
    app.state.servico = (
        ServicoMock() if config.api.mock else ServicoPostgres(obter_engine(), config.busca)
    )
    app.state.limitadores = {
        "consulta": LimitadorJanela(config.api.consultas_por_minuto, 60),
        "remocao": LimitadorJanela(config.api.remocoes_por_hora, 3600),
    }

    @app.exception_handler(ErroApi)
    def _erro_api(_request: Request, exc: ErroApi) -> JSONResponse:
        corpo = Erro(erro=exc.erro, mensagem=exc.mensagem)
        return JSONResponse(corpo.model_dump(), status_code=exc.status, headers=exc.cabecalhos)

    @app.exception_handler(_Indisponivel)
    def _indisponivel(_request: Request, exc: _Indisponivel) -> JSONResponse:
        return JSONResponse(exc.corpo.model_dump(), status_code=410)

    app.include_router(rotas)
    return app
