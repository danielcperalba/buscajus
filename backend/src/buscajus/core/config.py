"""Configuração da aplicação, lida de variáveis de ambiente (prefixo ``BUSCAJUS_``).

Campos aninhados usam ``__`` como separador, por exemplo
``BUSCAJUS_DJEN__TRIBUNAIS='["TJPR"]'``. Ver ``.env.example`` na raiz do repositório.
"""

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

NivelLog = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

# O TJDFT tem conector próprio; coletá-lo também pelo DJEN duplicaria acórdãos
# (ARCHITECTURE.md, seção 3.5).
TRIBUNAIS_COM_CONECTOR_PROPRIO = {"TJDFT": "tjdft"}


class ConfigDjen(BaseModel):
    ativo: bool = True
    tribunais: list[str] = ["TJPR"]
    # Primeiro dia com "Ementa de Acórdão" no caderno de cada tribunal (seção 3.2).
    inicio_ementas: dict[str, date] = {"TJPR": date(2025, 7, 23)}
    tipos_documento_aceitos: list[str] = ["Ementa de Acórdão"]
    requisicoes_por_segundo: float = Field(default=1.0, gt=0)

    @field_validator("tribunais")
    @classmethod
    def _siglas_em_maiusculas(cls, tribunais: list[str]) -> list[str]:
        return [sigla.strip().upper() for sigla in tribunais]

    @field_validator("inicio_ementas")
    @classmethod
    def _chaves_em_maiusculas(cls, inicio: dict[str, date]) -> dict[str, date]:
        return {sigla.strip().upper(): data for sigla, data in inicio.items()}

    @model_validator(mode="after")
    def _todo_tribunal_tem_data_de_inicio(self) -> Self:
        sem_inicio = [t for t in self.tribunais if t not in self.inicio_ementas]
        if sem_inicio:
            raise ValueError(
                "djen.inicio_ementas não define a data de início das ementas para: "
                + ", ".join(sem_inicio)
            )
        return self


class ConfigTjdft(BaseModel):
    ativo: bool = True
    # A API rejeita páginas com mais de 40 registros (HTTP 400).
    tamanho_pagina: int = Field(default=40, ge=1, le=40)
    requisicoes_por_segundo: float = Field(default=1.0, gt=0)


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BUSCAJUS_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://buscajus:buscajus@localhost:5432/buscajus"
    nivel_log: NivelLog = "INFO"

    diretorio_raw: Path = Path("data/raw")
    diretorio_tmp_cadernos: Path = Path("data/tmp-cadernos")
    diretorio_modelos: Path = Path("data/modelos")

    djen: ConfigDjen = ConfigDjen()
    tjdft: ConfigTjdft = ConfigTjdft()

    @model_validator(mode="after")
    def _sem_tribunal_em_dois_conectores(self) -> Self:
        if not self.djen.ativo:
            return self
        conflitos = [
            sigla
            for sigla, conector in TRIBUNAIS_COM_CONECTOR_PROPRIO.items()
            if sigla in self.djen.tribunais and getattr(self, conector).ativo
        ]
        if conflitos:
            raise ValueError(
                f"{', '.join(conflitos)} não pode ser coletado pelo DJEN enquanto o conector "
                "próprio estiver ativo (duplicaria acórdãos). Remova de djen.tribunais ou "
                "desative o conector próprio."
            )
        return self


@lru_cache
def obter_config() -> Config:
    return Config()
