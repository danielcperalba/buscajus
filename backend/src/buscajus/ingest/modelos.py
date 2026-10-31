"""Acórdão normalizado, comum a todas as fontes (ARCHITECTURE.md, seções 4.2 e 5.2)."""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

from buscajus.core.erros import ErroSeguro
from buscajus.ingest.conector import Fonte


class ItemInvalido(ErroSeguro):
    """Item do bruto sem os campos mínimos; contado como falha de parser."""


# Campos exibidos que entram no hash de conteúdo (mudança neles gera nova versão).
CAMPOS_CONTEUDO = (
    "ementa",
    "decisao",
    "relator",
    "relator_designado",
    "orgao_julgador",
    "classe_nome",
    "classe_codigo_cnj",
    "classe_citacao",
    "data_julgamento",
    "data_publicacao",
    "data_disponibilizacao",
    "local_publicacao",
    "link_oficial",
    "link_tribunal",
    "numero_processo",
)


@dataclass(frozen=True)
class AcordaoNormalizado:
    fonte: Fonte
    id_fonte: str
    tribunal: str
    numero_processo: str
    numero_processo_mascara: str
    numero_processo_valido: bool
    ementa: str
    link_oficial: str
    identificador_fonte: str | None = None
    hash_fonte: str | None = None
    tipo_documento_fonte: str | None = None
    orgao_julgador: str | None = None
    id_orgao_fonte: str | None = None
    classe_nome: str | None = None
    classe_codigo_cnj: int | None = None
    # Classe exibida na citação. DJEN: a do cabeçalho do texto, que difere de nomeClasse em
    # 44% das ementas do TJPR (F1-01); classe_nome/classe_codigo_cnj servem aos filtros.
    classe_citacao: str | None = None
    relator: str | None = None
    relator_chave: str | None = None
    # TJDFT: relator para o acórdão (nomeRelatorDesignado), quando o relator original foi
    # vencido; a citação usa "Rel. p/ acórdão" com ele. O relator original fica em relator.
    relator_designado: str | None = None
    relator_designado_chave: str | None = None
    turma_recursal: bool | None = None
    possui_inteiro_teor: bool | None = None
    data_julgamento: date | None = None
    data_publicacao: date | None = None
    data_disponibilizacao: date | None = None
    # TJDFT: veículo da publicação (localDePublicacao: "DJE" ou "PJe"), usado na citação.
    local_publicacao: str | None = None
    decisao: str | None = None
    link_tribunal: str | None = None
    anonimizacao_versao: str | None = None
    anonimizacao_substituicoes: int = 0
    ativo_fonte: bool | None = None
    status_fonte: str | None = None
    data_cancelamento: datetime | None = None

    @property
    def hash_conteudo(self) -> str:
        """sha256 dos campos exibidos normalizados (ARCHITECTURE.md, seção 4.5)."""
        conteudo = {campo: getattr(self, campo) for campo in CAMPOS_CONTEUDO}
        serializado = json.dumps(conteudo, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(serializado.encode()).hexdigest()

    def colunas(self) -> dict[str, Any]:
        return asdict(self) | {"hash_conteudo": self.hash_conteudo}
