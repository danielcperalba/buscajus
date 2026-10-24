"""Classificação heurística PF × PJ dos destinatários (F1-34, ARCHITECTURE.md, seção 6.3).

A consulta pública do DJEN traz só nome e polo. Regras, nesta ordem:

1. CNPJ no nome, natureza societária (``LTDA``, ``S.A.``, ``EIRELI``, ``CONDOMÍNIO``,
   ``MASSA FALIDA``…) ou ente público (``MUNICÍPIO DE``, ``INSS``, ``MINISTÉRIO PÚBLICO``…)
   → PJ. Razão social com nome de pessoa continua PJ.
2. ``ESPÓLIO DE`` + nome, nome + ``ME``/``MEI``/``EI`` ou nome + 11 dígitos → PF, com o
   prefixo, o sufixo e o número removidos para casar no texto.
3. Marcadores de setor (``BANCO``, ``SEGURADORA``, ``COMÉRCIO``…) → PJ.
4. Nome com cara de pessoa (2 a 8 palavras só de letras) → PF; o resto → ``ambíguo``,
   tratado como PF (o nome é substituído).

Errar para o lado de PF custa um nome de empresa trocado por iniciais; errar para PJ deixa
um nome de pessoa no texto. Por isso, marcadores que também são sobrenomes comuns só contam
no início do nome.
"""

import re
from dataclasses import dataclass
from typing import Literal

from buscajus.ingest.texto import sem_acentos

Classe = Literal["PF", "PJ", "ambiguo"]

# Natureza societária e entes públicos: valem em qualquer posição.
_PJ_SEMPRE = [
    r"LTDA",
    r"S\s*[./]\s*A\.?",
    r"EIRELI",
    r"EPP",
    r"CIA",
    r"SOCIEDADE",
    r"COOPERATIVA",
    r"ASSOCIACAO",
    r"FUNDACAO",
    r"CONDOMINIO",
    r"MASSA FALIDA",
    r"SINDICATO",
    r"CONSORCIO",
    r"FEDERACAO",
    r"CONFEDERACAO",
    r"ORGANIZACAO",
    r"PARTIDO",
    r"MUNICIPIO",
    r"PREFEITURA",
    r"CAMARA MUNICIPAL",
    r"ASSEMBLEIA LEGISLATIVA",
    r"UNIAO FEDERAL",
    r"FAZENDA PUBLICA",
    r"FAZENDA NACIONAL",
    r"INSS",
    r"INSTITUTO NACIONAL",
    r"MINISTERIO",
    r"DEFENSORIA",
    r"PROCURADORIA",
    r"ADVOCACIA[- ]GERAL",
    r"AUTARQUIA",
    r"SECRETARIA",
    r"DEPARTAMENTO",
    r"DETRAN",
    r"AGENCIA",
    r"TRIBUNAL",
    r"JUSTICA PUBLICA",
    r"DELEGACIA",
    r"POLICIA",
    r"CONSELHO",
    r"COMERCIO",
    r"INDUSTRIA",
    r"SERVICOS",
    r"PARTICIPACOES",
    r"EMPREENDIMENTOS",
    r"INCORPORADORA",
    r"ENGENHARIA",
    r"TRANSPORTES?",
    r"TELECOMUNICACOES",
    r"ALIMENTOS",
    r"SEGUROS",
    r"FINANCEIRA",
    r"PREVIDENCIA",
    r"SANEAMENTO",
    r"ENERGIA",
    r"COMUNICACOES",
    r"TECNOLOGIA",
    r"INFORMATICA",
    r"DISTRIBUIDORA",
    r"IMOBILIARIA",
    r"CONSTRUTORA",
    r"TRANSPORTADORA",
    r"AGROPECUARIA",
    r"HOLDING",
    r"ADMINISTRADORA",
    r"CORRETORA",
]
# Setor ou instituição que também pode ser sobrenome: só no início do nome.
_PJ_NO_INICIO = [
    r"BANCO",
    r"SEGURADORA",
    r"CAIXA",
    r"IGREJA",
    r"HOSPITAL",
    r"CLINICA",
    r"COLEGIO",
    r"ESCOLA",
    r"UNIVERSIDADE",
    r"FACULDADE",
    r"INSTITUTO",
    r"EMPRESA",
    r"COMPANHIA",
    r"FARMACIA",
    r"LABORATORIO",
    r"EDITORA",
    r"ESTADO D[OAE]",
    r"DISTRITO FEDERAL",
    r"UNIAO",
    r"JUIZO",
    r"CENTRO",
]

_PJ = re.compile(r"(?<![A-Z0-9])(?:" + "|".join(_PJ_SEMPRE) + r")(?![A-Z0-9])")
_PJ_INICIO = re.compile(r"^(?:" + "|".join(_PJ_NO_INICIO) + r")(?![A-Z0-9])")
_CNPJ = re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)")
_ESPOLIO = re.compile(r"^ESPOLIO\s+(?:(?:DE|DO|DA)\s+)?(?P<nome>.+)$")
_CPF_NO_FIM = re.compile(r"[\s,-]*(?:CPF[\s:nº.]*)?(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}$")
_SUFIXO_EMPRESARIO = re.compile(r"[\s,-]+(?:ME|MEI|EI)\.?$")
_PALAVRA = re.compile(r"^[A-Z][A-Z'-]*$")


@dataclass(frozen=True)
class Classificacao:
    classe: Classe
    # Para PF e ambíguo: o nome a procurar no texto (sem prefixo, sufixo nem número).
    nome: str

    @property
    def substituir(self) -> bool:
        return self.classe != "PJ"


def _normalizar(nome: str) -> str:
    return " ".join(sem_acentos(nome).upper().split())


def classificar(nome: str) -> Classificacao:
    normalizado = _normalizar(nome)
    if not normalizado:
        return Classificacao("ambiguo", "")
    if _CNPJ.search(normalizado) or _PJ.search(normalizado):
        return Classificacao("PJ", normalizado)

    pessoa = normalizado
    espolio = _ESPOLIO.match(pessoa)
    if espolio:
        pessoa = espolio.group("nome")
    marcado_como_pf = bool(espolio)
    for padrao in (_CPF_NO_FIM, _SUFIXO_EMPRESARIO, _CPF_NO_FIM):
        sem_sufixo = padrao.sub("", pessoa).strip(" ,-")
        if sem_sufixo != pessoa:
            pessoa, marcado_como_pf = sem_sufixo, True
    if marcado_como_pf:
        return Classificacao("PF", pessoa)

    if _PJ_INICIO.search(normalizado):
        return Classificacao("PJ", normalizado)
    palavras = normalizado.split()
    if 2 <= len(palavras) <= 8 and all(_PALAVRA.match(p) for p in palavras):
        return Classificacao("PF", normalizado)
    return Classificacao("ambiguo", normalizado)
