"""Contrato da API (F4-01; ARCHITECTURE.md, seções 9 e 10).

Esquemas de resposta e de pedido de ``/api/v1``. O frontend gera os tipos a partir do OpenAPI
versionado em ``frontend/openapi.json`` (``buscajus api openapi``).
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Fonte = Literal["djen", "tjdft"]
AVISO = "Texto reproduzido da fonte oficial. Consulte o documento original."
LIMITE_RESULTADOS = 200
POR_PAGINA = 20


class Esquema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Erro(Esquema):
    erro: str = Field(description="Código do erro, estável (ex.: nao_encontrado)")
    mensagem: str


class Indisponivel(Esquema):
    """Acórdão que existiu mas não pode ser exibido (HTTP 410)."""

    erro: Literal["cancelado", "removido"]
    mensagem: str
    link_oficial: str | None = Field(
        default=None, description="Fonte oficial, quando ainda faz sentido indicá-la"
    )


class SituacaoAcordao(Esquema):
    """Situação exibível de um acórdão, sem o conteúdo (para o site responder 404/410 cedo)."""

    situacao: Literal["ativo", "cancelado", "removido"]


class Classe(Esquema):
    codigo: int | None = Field(description="Código da classe na TPU do CNJ")
    nome: str | None


class Acordao(Esquema):
    """Campos comuns ao resultado de busca e ao detalhe."""

    id: int
    fonte: Fonte
    tribunal: str = Field(examples=["TJPR", "TJDFT"])
    numero_processo: str = Field(description="Número CNJ com máscara")
    orgao_julgador: str | None
    classe: Classe
    relator: str | None
    relator_designado: str | None = Field(
        description="TJDFT: relator para o acórdão (a citação usa 'Rel. p/ acórdão')"
    )
    turma_recursal: bool | None
    data_julgamento: date | None
    data_publicacao: date | None = Field(description="TJDFT; nula no DJEN (não é calculada)")
    data_disponibilizacao: date | None = Field(description="DJEN")
    link_oficial: str = Field(description="DJEN: certidão do CNJ; TJDFT: página do acórdão")
    link_tribunal: str | None = Field(description="DJEN: documento no sistema do tribunal")
    citacao: str = Field(description="Copiar exatamente como veio (regra da seção 9)")
    aviso: str = AVISO


class ResultadoBusca(Acordao):
    trecho: str = Field(
        description="Trecho da ementa; o único HTML possível é <mark> em volta dos termos"
    )


class DetalheAcordao(Acordao):
    ementa: str
    decisao: str | None = Field(description="TJDFT: dispositivo")
    possui_inteiro_teor: bool | None


class FiltrosBusca(Esquema):
    tribunal: str | None = None
    orgao: str | None = None
    classe: int | None = None
    relator: str | None = Field(default=None, description="relator_chave")
    data_inicio: date | None = None
    data_fim: date | None = None


class RespostaBusca(Esquema):
    consulta: str = Field(description="Consulta normalizada")
    tipo: Literal["hibrida", "processo"] = Field(
        description="processo: a consulta era um número de processo (busca exata ou prefixo)"
    )
    numero_processo: str | None = Field(
        description="Número detectado na consulta (com máscara, ou os dígitos do prefixo)"
    )
    filtros: FiltrosBusca
    pagina: int
    por_pagina: int = POR_PAGINA
    total: int = Field(description=f"Até {LIMITE_RESULTADOS}; não há páginas além disso")
    resultados: list[ResultadoBusca]


class AcordaosDoProcesso(Esquema):
    numero_processo: str
    acordaos: list[ResultadoBusca] = Field(description="Do mais recente ao mais antigo")


class OpcaoFiltro(Esquema):
    valor: str
    rotulo: str
    total: int


class Filtros(Esquema):
    tribunais: list[OpcaoFiltro]
    orgaos: list[OpcaoFiltro]
    classes: list[OpcaoFiltro]


class CoberturaTribunal(Esquema):
    """Acórdãos exibíveis de uma fonte e tribunal, e o período (data de referência)."""

    fonte: Fonte
    fonte_nome: str
    fonte_url: str
    tribunal: str
    acordaos: int
    desde: date | None
    ate: date | None


class Relator(Esquema):
    nome: str
    chave: str = Field(description="Valor do filtro 'relator' na busca")


class PedidoRemocao(Esquema):
    referencia: str = Field(
        min_length=5, max_length=300, description="Número do processo ou link do resultado"
    )
    motivo: str = Field(min_length=10, max_length=2000)
    email: str = Field(
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        description="Usado só para responder; apagado após a resolução",
    )


class RemocaoRecebida(Esquema):
    protocolo: int
    status: Literal["pendente"]
    mensagem: str
