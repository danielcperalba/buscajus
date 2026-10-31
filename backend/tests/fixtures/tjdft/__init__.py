"""Gerador das fixtures sintéticas da API do TJDFT (F2-02).

Os arquivos desta pasta são respostas de ``POST /api/v1/pesquisa`` geradas a partir de
``dados.py``. Para regerar (de ``backend/tests``)::

    uv run python -m fixtures.tjdft

Um teste confere que os arquivos versionados batem com o gerador.
"""

import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from fixtures.djen import numero_cnj
from fixtures.tjdft import dados

PASTA = Path(__file__).parent
TAMANHO = 40
NOMES_CLASSES = {
    dados.APELACAO_CIVEL: "Apelação Cível",
    dados.AGRAVO_INSTRUMENTO: "Agravo de Instrumento",
    dados.APELACAO_CRIMINAL: "Apelação Criminal",
    dados.RECURSO_INOMINADO: "Recurso Inominado Cível",
    dados.EMBARGOS_DECLARACAO: "Embargos de Declaração Cível",
    dados.HABEAS_CORPUS: "Habeas Corpus Criminal",
    dados.AGRAVO_INTERNO: "Agravo Interno Cível",
}


def uuid(n: int) -> str:
    return f"0f1c7e00-2099-4000-8000-{n:012d}"


def registro(r: dados.Registro) -> dict[str, Any]:
    """Registro na ordem de campos da API; designado e revisor só quando existem."""
    _, processo = numero_cnj(r.n, justica=8, tribunal=7)
    saida: dict[str, Any] = {
        "sequencial": 7000 + r.n,
        "base": "acordaos",
        "subbase": "acordaos-tr" if r.turma_recursal else "acordaos",
        "uuid": uuid(r.n),
        "identificador": f"99{r.n:05d}",
        "dataJulgamento": r.julgamento,
        "dataPublicacao": r.publicacao,
        "decisao": r.decisao,
        "ementa": r.ementa,
        "localDePublicacao": r.local,
        "processo": processo,
        "nomeRelator": r.relator,
        "relatorAtivo": True,
        "uf": "DF",
        "segredoJustica": r.segredo,
        "turmaRecursal": r.turma_recursal,
        "descricaoOrgaoJulgador": r.orgao,
        "versao": "01",
        "codigoClasseCnj": r.classe,
        "codigoSistjOrgaoJulgador": dados.ORGAOS[r.orgao],
        "marcadores": {"decisao": [], "ementa": [], "termosAuxiliares": []},
        "possuiInteiroTeor": not r.segredo,
    }
    if r.designado:
        saida["nomeRelatorDesignado"] = r.designado
    if r.revisor:
        saida["nomeRevisor"] = r.revisor
    return saida | r.extras


def _contagem(valores: Sequence[Any]) -> list[dict[str, Any]]:
    return [{"nome": nome, "total": total} for nome, total in Counter(valores).most_common()]


def agregacoes(registros: Sequence[dados.Registro]) -> dict[str, Any]:
    """Agregações da consulta inteira (não só da página), como na API."""
    recursais = sum(r.turma_recursal for r in registros)
    filhos = [{"nome": "acordaos", "total": len(registros) - recursais}]
    if recursais:
        filhos.append({"nome": "acordaos-tr", "total": recursais})
    return {
        "base": [{"nome": "acordaos", "total": len(registros), "filhos": filhos}]
        if registros
        else [],
        "classe": _contagem([NOMES_CLASSES[r.classe] for r in registros]),
        "orgaoJulgador": _contagem([r.orgao for r in registros]),
        "relator": _contagem([r.relator for r in registros]),
        "relatorDesignado": _contagem([r.designado for r in registros if r.designado]),
        "revisor": _contagem([r.revisor for r in registros if r.revisor]),
        "segredoJustica": _contagem([int(r.segredo) for r in registros]),
    }


def resposta(
    registros_dia: Sequence[dados.Registro],
    pagina: int,
    registros_pagina: Sequence[dados.Registro] | None = None,
    total: int | None = None,
) -> dict[str, Any]:
    """Página ``pagina`` da consulta de um dia (ou ``registros_pagina``, se informado)."""
    if registros_pagina is None:
        registros_pagina = registros_dia[pagina * TAMANHO : (pagina + 1) * TAMANHO]
    return {
        "hits": {"value": len(registros_dia) if total is None else total},
        "agregacoes": agregacoes(registros_dia),
        "paginacao": {"pagina": pagina, "tamanho": TAMANHO},
        "registros": [registro(r) for r in registros_pagina],
    }


def arquivos() -> dict[str, bytes]:
    """Todos os arquivos da pasta de fixtures, por nome."""

    def js(objeto: Any) -> bytes:
        return (json.dumps(objeto, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    saida = {
        f"pesquisa-{dados.DIA}-p{p}.json": js(resposta(dados.REGISTROS_DIA, p)) for p in range(3)
    }
    saida[f"pesquisa-{dados.DIA_VIRADA}-p0.json"] = js(resposta(dados.REGISTROS_VIRADA, 0))
    repetido = dados.REGISTROS_REPETIDO
    saida[f"pesquisa-{dados.DIA_REPETIDO}-p0.json"] = js(resposta(repetido, 0))
    saida[f"pesquisa-{dados.DIA_REPETIDO}-p1.json"] = js(resposta(repetido, 1))
    duplicado = next(r for r in repetido if r.n == dados.REPETIDO)
    saida[f"pesquisa-{dados.DIA_REPETIDO}-p1-repetida.json"] = js(
        resposta(repetido, 1, registros_pagina=[duplicado])
    )
    saida[f"pesquisa-{dados.DIA_VAZIO}-p0.json"] = js(resposta((), 0))
    return saida


def gravar(pasta: Path = PASTA) -> list[str]:
    nomes = []
    for nome, conteudo in sorted(arquivos().items()):
        (pasta / nome).write_bytes(conteudo)
        nomes.append(nome)
    return nomes


def carregar(nome: str) -> dict[str, Any]:
    conteudo: dict[str, Any] = json.loads((PASTA / nome).read_text(encoding="utf-8"))
    return conteudo
