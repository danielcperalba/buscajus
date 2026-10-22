from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, Response, status
from pydantic import BaseModel
from sqlalchemy import Engine

from buscajus import __version__
from buscajus.core.config import obter_config
from buscajus.core.logging import configurar_logging
from buscajus.db.engine import banco_disponivel, obter_engine

Estado = Literal["ok", "erro"]


class Saude(BaseModel):
    status: Estado
    banco: Estado
    versao: str


rotas = APIRouter(prefix="/api/v1")


@rotas.get("/saude")
def saude(response: Response, engine: Annotated[Engine, Depends(obter_engine)]) -> Saude:
    banco: Estado = "ok" if banco_disponivel(engine) else "erro"
    if banco == "erro":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return Saude(status=banco, banco=banco, versao=__version__)


def criar_app() -> FastAPI:
    configurar_logging(obter_config().nivel_log)
    app = FastAPI(title="BuscaJus", version=__version__)
    app.include_router(rotas)
    return app
