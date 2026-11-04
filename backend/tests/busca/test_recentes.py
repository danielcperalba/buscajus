"""Acórdãos recentes (F5-13): ordem, situação, paginação e índice, com acórdãos sintéticos."""

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from buscajus.api.esquemas import ResultadoBusca
from buscajus.busca import servico as modulo_servico
from buscajus.busca.servico import SQL_RECENTES

from .conftest import acordao, inserir

pytestmark = pytest.mark.banco


def _recentes(cliente: TestClient, pagina: int | None = None) -> dict[str, Any]:
    parametros = {} if pagina is None else {"pagina": pagina}
    resposta = cliente.get("/api/v1/acordaos/recentes", params=parametros)
    assert resposta.status_code == 200, resposta.text
    corpo: dict[str, Any] = resposta.json()
    return corpo


def _id_fonte(corpo: dict[str, Any]) -> list[str]:
    """Os links sintéticos terminam no id_fonte (``https://exemplo.invalid/<id_fonte>``)."""
    return [r["link_oficial"].rsplit("/", 1)[1] for r in corpo["resultados"]]


def _situacao(banco: Engine, id_fonte: str, situacao: str) -> None:
    with banco.begin() as conexao:
        conexao.execute(
            text("UPDATE acordao SET situacao = CAST(:s AS situacao_acordao) WHERE id_fonte = :i"),
            {"s": situacao, "i": id_fonte},
        )


def test_ordem_pela_publicacao_com_desempate_por_id_e_so_ativos(
    cliente: TestClient, banco: Engine
) -> None:
    inserir(
        banco,
        acordao("r-a", "PRIMEIRO de 20/10.", sequencial=201, publicacao=date(2026, 10, 20)),
        # DJEN: vale a disponibilização, não o julgamento (que é antigo).
        acordao(
            "r-djen",
            "DJEN de 22/10.",
            fonte="djen",
            sequencial=202,
            julgamento=date(2026, 1, 5),
            publicacao=date(2026, 10, 22),
        ),
        acordao("r-c", "SEGUNDO de 20/10.", sequencial=203, publicacao=date(2026, 10, 20)),
        # Julgado por último, mas sem data de publicação: vai para o fim.
        acordao(
            "r-sem-data",
            "Sem publicação.",
            sequencial=204,
            julgamento=date(2026, 10, 30),
            publicacao=None,
        ),
        *(
            acordao(f"r-{s}", f"{s} de 25/10.", sequencial=210 + i, publicacao=date(2026, 10, 25))
            for i, s in enumerate(("quarentena", "cancelado", "removido", "duplicado"))
        ),
    )
    for situacao in ("quarentena", "cancelado", "removido", "duplicado"):
        _situacao(banco, f"r-{situacao}", situacao)

    corpo = _recentes(cliente)
    assert _id_fonte(corpo) == ["r-djen", "r-c", "r-a", "r-sem-data"]
    assert (corpo["total"], corpo["total_paginas"]) == (4, 1)


def test_paginas_de_dez_sem_repeticao(cliente: TestClient, banco: Engine) -> None:
    inserir(
        banco,
        *(
            acordao(
                f"p{i:02d}",
                f"PREVIDÊNCIA {i}.",
                sequencial=300 + i,
                publicacao=date(2026, 9, 1 + i % 5),  # empates: o id desempata
            )
            for i in range(25)
        ),
    )
    paginas = [_recentes(cliente, n) for n in (1, 2, 3)]
    assert [len(p["resultados"]) for p in paginas] == [10, 10, 5]
    for numero, pagina in enumerate(paginas, start=1):
        assert pagina["pagina"] == numero
        assert (pagina["por_pagina"], pagina["total"], pagina["total_paginas"]) == (10, 25, 3)
    ids = [r["id"] for p in paginas for r in p["resultados"]]
    assert len(set(ids)) == 25
    # Todos do TJDFT: a data de publicação é data_publicacao.
    chaves = [(r["data_publicacao"], r["id"]) for p in paginas for r in p["resultados"]]
    assert chaves == sorted(chaves, reverse=True)
    # Além da última página: vazia, sem erro.
    alem = _recentes(cliente, 4)
    assert (alem["resultados"], alem["total_paginas"]) == ([], 3)


def test_total_limitado_a_cem_paginas(
    cliente: TestClient, banco: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # O teto real é 1.000 (100 páginas de 10); reduzido aqui para não inserir mil acórdãos.
    monkeypatch.setattr(modulo_servico, "LIMITE_RECENTES", 20)
    inserir(banco, *(acordao(f"t{i}", f"TETO {i}.", sequencial=400 + i) for i in range(25)))
    corpo = _recentes(cliente)
    assert (corpo["total"], corpo["total_paginas"]) == (20, 2)


@pytest.mark.parametrize("pagina", ["0", "-1", "101", "abc"])
def test_pagina_fora_do_limite_e_422(cliente: TestClient, pagina: str) -> None:
    resposta = cliente.get("/api/v1/acordaos/recentes", params={"pagina": pagina})
    assert resposta.status_code == 422


def test_pagina_cem_e_aceita(cliente: TestClient, banco: Engine) -> None:
    inserir(banco, acordao("u1", "ÚNICO."))
    corpo = _recentes(cliente, 100)
    assert (corpo["pagina"], corpo["resultados"], corpo["total"]) == (100, [], 1)


def test_formato_igual_ao_item_da_busca(cliente: TestClient, banco: Engine) -> None:
    inserir(
        banco,
        acordao(
            "f-djen",
            "RECURSO INOMINADO. <b>Partilha</b> de bens.",
            fonte="djen",
            sequencial=500,
            orgao="3ª Turma Recursal",
            classe=(460, "Recurso Inominado Cível"),
            julgamento=None,
            publicacao=date(2026, 10, 14),
        ),
    )
    corpo = _recentes(cliente)
    assert set(corpo) == {"pagina", "por_pagina", "total", "total_paginas", "resultados"}
    (item,) = corpo["resultados"]
    assert set(item) == set(ResultadoBusca.model_fields)
    assert (item["tribunal"], item["fonte"], item["orgao_julgador"]) == (
        "TJPR",
        "djen",
        "3ª Turma Recursal",
    )
    assert item["classe"] == {"codigo": 460, "nome": "Recurso Inominado Cível"}
    assert item["numero_processo"].endswith(".2099.8.16.9999")
    assert (item["data_publicacao"], item["data_disponibilizacao"]) == (None, "2026-10-14")
    # Trecho: o começo da ementa, escapado e sem destaque.
    assert item["trecho"] == "RECURSO INOMINADO. &lt;b&gt;Partilha&lt;/b&gt; de bens."
    assert item["citacao"].endswith("DJEN de 14/10/2026.")
    assert item["aviso"].startswith("Texto reproduzido")


def test_lista_vazia(cliente: TestClient) -> None:
    corpo = _recentes(cliente)
    assert (corpo["total"], corpo["total_paginas"], corpo["resultados"]) == (0, 0, [])


def test_indice_serve_a_ordem_sem_ordenar(banco: Engine) -> None:
    """Com varredura sequencial e ordenação desligadas, só o índice da 0008 serve a consulta."""
    inserir(banco, *(acordao(f"i{i}", f"ÍNDICE {i}.", sequencial=600 + i) for i in range(5)))
    with banco.begin() as conexao:
        conexao.execute(text("SET LOCAL enable_seqscan = off"))
        conexao.execute(text("SET LOCAL enable_sort = off"))
        plano = conexao.scalar(
            text(f"EXPLAIN (FORMAT JSON) {SQL_RECENTES}"), {"limite": 10, "inicio": 0}
        )
    nos: list[dict[str, Any]] = []
    pendentes = [plano[0]["Plan"]]
    while pendentes:
        no = pendentes.pop()
        nos.append(no)
        pendentes.extend(no.get("Plans", []))
    assert any(no.get("Index Name") == "acordao_recentes_idx" for no in nos)
    assert not any(no["Node Type"] in ("Sort", "Incremental Sort") for no in nos)
