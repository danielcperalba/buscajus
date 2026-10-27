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
    # O ZIP fica no tmpfs do worker (1100 MB no compose). Maior caderno do TJPR visto no
    # F1-01: 163 MB (23/10/2026); acima do alerta, o download segue com aviso no log.
    limite_bytes_caderno: int = Field(default=1024 * 1024 * 1024, gt=0)
    alerta_bytes_caderno: int = Field(default=500 * 1024 * 1024, gt=0)
    # Downloads cujo SHA-256 não confere com o campo hash, antes de marcar erro.
    tentativas_hash: int = Field(default=3, ge=1)
    # Status de comunicação ativa (F1-01: "P" em 100%) e de cancelada (nenhum valor confirmado;
    # ativo = false e data_cancelamento preenchida bastam). Outro status → anomalia.
    status_ativos: list[str] = ["P"]
    status_cancelamento: list[str] = []

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
    url_api: str = "https://jurisdf.tjdft.jus.br/api/v1/pesquisa"
    # A API rejeita páginas com mais de 40 registros (HTTP 400).
    tamanho_pagina: int = Field(default=40, ge=1, le=40)
    # A documentação não informa limite de taxa: 1 requisição/s por conta própria.
    requisicoes_por_segundo: float = Field(default=1.0, gt=0)
    # Leituras completas do dia quando os uuids únicos não batem com hits.value (F2-04).
    tentativas_integridade: int = Field(default=3, ge=1)


class ConfigApi(BaseModel):
    # Dados sintéticos fixos no formato do contrato, para o frontend antes da busca real.
    mock: bool = False
    # Limite de taxa por IP (F4-13): consultas (busca, detalhe, processo, filtros, relatores)
    # e pedidos de remoção, em janelas deslizantes.
    consultas_por_minuto: int = Field(default=60, ge=1)
    remocoes_por_hora: int = Field(default=5, ge=1)
    # Atrás de um proxy reverso (Caddy), o IP do cliente vem de X-Forwarded-For.
    confiar_x_forwarded_for: bool = False
    # Dias que o e-mail de quem pediu a remoção fica guardado depois da resolução (seção 6.5).
    retencao_contato_dias: int = Field(default=90, ge=0)


class ConfigBusca(BaseModel):
    # Fusão RRF (seção 8.5): k e pesos dos ramos, ajustados no conjunto de avaliação (F6-07).
    rrf_k: float = Field(default=60, gt=0)
    peso_vetor: float = Field(default=1.0, ge=0)
    peso_texto: float = Field(default=1.0, ge=0)
    # Resultados por ramo antes da fusão.
    top_ramo: int = Field(default=100, ge=1)
    # Busca por prefixo do número do processo: no máximo este número de acórdãos.
    limite_prefixo: int = Field(default=50, ge=1)
    # Cache dos valores de /filtros.
    cache_filtros_segundos: float = Field(default=300, ge=0)


class ConfigEmbeddings(BaseModel):
    # Modelo ainda não fixado (F3-05/F3-06): nome no Hugging Face e revisão (commit).
    modelo: str | None = None
    revisao: str | None = None
    # "auto" usa GPU (cuda) se houver; senão CPU.
    dispositivo: str = "auto"
    tamanho_lote: int = Field(default=32, ge=1)
    # Fatiamento de ementas longas (F3-03), em tokens do próprio modelo.
    tokens_por_trecho: int = Field(default=450, ge=16)
    sobreposicao_tokens: int = Field(default=50, ge=0)

    @model_validator(mode="after")
    def _sobreposicao_menor_que_trecho(self) -> Self:
        if self.sobreposicao_tokens >= self.tokens_por_trecho:
            raise ValueError("embeddings.sobreposicao_tokens deve ser menor que tokens_por_trecho")
        return self


class ConfigAnonimizacao(BaseModel):
    # Modelo local de NER de pessoas (camada 2), escolhido no F1-36. Vazio: o pipeline do
    # DJEN não é criado e nenhum dado real é processado.
    modelo_ner: str | None = None


class ConfigAgendador(BaseModel):
    # Desligado até decidir onde os dados reais ficam (a coleta precisa rodar no Brasil).
    ativo: bool = False
    # Horário (America/Sao_Paulo) a partir do qual o caderno do dia é coletado.
    horario_djen: time = time(9, 0)
    # Horário da coleta diária do TJDFT (a maioria dos acórdãos sai à meia-noite em São Paulo).
    horario_tjdft: time = time(8, 0)
    # Dias do TJDFT recoletados todo dia (mudanças de segredo e registros publicados com
    # atraso); inclui a reconsulta do dia anterior.
    dias_recoleta_tjdft: int = Field(default=30, ge=1)
    # Conferência mensal (F2-14): no dia do mês indicado, compara o total da fonte com o
    # coletado nos dias de dias_recoleta_tjdft + 1 até dias_conferencia_tjdft atrás e recoleta
    # só os que mudaram.
    dia_conferencia_tjdft: int = Field(default=1, ge=1, le=28)
    dias_conferencia_tjdft: int = Field(default=90, ge=1)
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

    database_url: str = "postgresql+psycopg://buscajus:buscajus@127.0.0.1:5432/buscajus"
    nivel_log: NivelLog = "INFO"

    diretorio_raw: Path = Path("data/raw")
    diretorio_tmp_cadernos: Path = Path("data/tmp-cadernos")
    diretorio_modelos: Path = Path("data/modelos")

    http: ConfigHttp = ConfigHttp()
    anonimizacao: ConfigAnonimizacao = ConfigAnonimizacao()
    embeddings: ConfigEmbeddings = ConfigEmbeddings()
    api: ConfigApi = ConfigApi()
    busca: ConfigBusca = ConfigBusca()
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
