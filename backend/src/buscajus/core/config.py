"""Configuração da aplicação, lida de variáveis de ambiente (prefixo ``BUSCAJUS_``).

Campos aninhados usam ``__`` como separador, por exemplo
``BUSCAJUS_DJEN__TRIBUNAIS='["TJPR"]'``. Ver ``.env.example`` na raiz do repositório.
"""

from datetime import date, time
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

NivelLog = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

# O TJDFT tem conector próprio; coletá-lo também pelo DJEN duplicaria acórdãos
# (ARCHITECTURE.md, seção 3.5).
TRIBUNAIS_COM_CONECTOR_PROPRIO = {"TJDFT": "tjdft"}


# Identificação do projeto no User-Agent das requisições às fontes (ARCHITECTURE.md, seção 3.1).
URL_PROJETO = "https://github.com/danielcperalba/buscajus"


class ConfigHttp(BaseModel):
    # Contato opcional (e-mail ou URL) incluído no User-Agent.
    contato: str | None = None
    timeout_segundos: float = Field(default=30, gt=0)
    timeout_conexao_segundos: float = Field(default=10, gt=0)
    timeout_download_segundos: float = Field(default=300, gt=0)
    max_tentativas: int = Field(default=5, ge=1)
    # Erros 5xx e timeouts: espera antes de cada nova tentativa (o último valor se repete).
    backoff_segundos: list[float] = Field(default=[5, 15, 45], min_length=1)
    # 429 sem Retry-After; com Retry-After, a espera pedida é limitada ao máximo.
    espera_429_segundos: float = Field(default=60, ge=0)
    espera_maxima_429_segundos: float = Field(default=600, ge=0)
    # Pausa preventiva quando x-ratelimit-remaining chega a zero.
    pausa_limite_esgotado_segundos: float = Field(default=60, ge=0)


class ConfigDjen(BaseModel):
    ativo: bool = True
    url_api: str = "https://comunicaapi.pje.jus.br"
    tribunais: list[str] = ["TJPR"]
    # Primeiro dia com "Ementa de Acórdão" no caderno de cada tribunal (seção 3.2).
    inicio_ementas: dict[str, date] = {"TJPR": date(2025, 7, 23)}
    tipos_documento_aceitos: list[str] = ["Ementa de Acórdão"]
    requisicoes_por_segundo: float = Field(default=1.0, gt=0)
    # O ZIP fica no tmpfs do worker (256 MB no compose); o maior caderno do TJPR tem ~57 MB.
    limite_bytes_caderno: int = Field(default=200 * 1024 * 1024, gt=0)
    # Downloads cujo SHA-256 não confere com o campo hash, antes de marcar erro.
    tentativas_hash: int = Field(default=3, ge=1)
    # Valores de status de comunicação cancelada (a confirmar no F1-01); ativo = false e
    # data_cancelamento preenchida também indicam cancelamento.
    status_cancelamento: list[str] = ["C"]

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


class ConfigAnonimizacao(BaseModel):
    # Modelo local de NER de pessoas (camada 2), escolhido no F1-36. Vazio: o pipeline do
    # DJEN não é criado e nenhum dado real é processado.
    modelo_ner: str | None = None


class ConfigAgendador(BaseModel):
    # Desligado até decidir onde os dados reais ficam (a coleta precisa rodar no Brasil).
    ativo: bool = False
    # Horário (America/Sao_Paulo) a partir do qual o caderno do dia é coletado.
    horario_djen: time = time(9, 0)
    # Dias anteriores revisitados na coleta diária (cadernos publicados com atraso).
    dias_retroativos: int = Field(default=3, ge=0)
    # Janela da checagem de versões dos cadernos (F1-16).
    dias_verificacao_versao: int = Field(default=30, ge=1)
    intervalo_segundos: float = Field(default=60, gt=0)


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

    http: ConfigHttp = ConfigHttp()
    anonimizacao: ConfigAnonimizacao = ConfigAnonimizacao()
    agendador: ConfigAgendador = ConfigAgendador()
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
