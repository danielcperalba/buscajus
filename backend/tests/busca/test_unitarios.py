"""Citação (F4-10), fusão RRF (F4-06), tsquery e trecho (F4-04) e limite de taxa (F4-13)."""

from datetime import date
from typing import Any

import pytest
from starlette.requests import Request

from buscajus.api.limite import LimitadorJanela, ip_do_cliente, verificar
from buscajus.api.servico import ErroApi
from buscajus.busca.citacao import citar
from buscajus.busca.fusao import pagina, rrf
from buscajus.busca.texto import expressao_tsquery, inicio_da_ementa, marcar

TJPR: dict[str, Any] = {
    "fonte": "djen",
    "tribunal": "TJPR",
    "orgao_julgador": "3ª Turma Recursal dos Juizados Especiais",
    "classe_citacao": "Recurso Inominado",
    "classe_nome": "Recurso Inominado Cível",
    "numero_processo_mascara": "0011412-20.2025.8.16.0069",
    "relator": "Fulano de Tal",
    "data_julgamento": date(2026, 10, 6),
    "data_disponibilizacao": date(2026, 10, 14),
}
TJDFT: dict[str, Any] = {
    "fonte": "tjdft",
    "tribunal": "TJDFT",
    "orgao_julgador": "3ª Turma Cível",
    "classe_citacao": "Apelação Cível",
    "numero_processo_mascara": "0701234-56.2023.8.07.0001",
    "relator": "Fulano de Tal",
    "data_julgamento": date(2026, 10, 8),
    "data_publicacao": date(2026, 10, 21),
    "local_publicacao": "PJe",
}


@pytest.mark.parametrize(
    ("acordao", "esperado"),
    [
        (
            TJPR,
            "TJPR, 3ª Turma Recursal dos Juizados Especiais, Recurso Inominado nº "
            "0011412-20.2025.8.16.0069, Rel. Fulano de Tal, j. 06/10/2026, DJEN de 14/10/2026.",
        ),
        (
            TJPR | {"data_julgamento": None},
            "TJPR, 3ª Turma Recursal dos Juizados Especiais, Recurso Inominado nº "
            "0011412-20.2025.8.16.0069, Rel. Fulano de Tal, DJEN de 14/10/2026.",
        ),
        (
            TJDFT,
            "TJDFT, 3ª Turma Cível, Apelação Cível nº 0701234-56.2023.8.07.0001, "
            "Rel. Fulano de Tal, j. 08/10/2026, publ. PJe 21/10/2026.",
        ),
        (
            TJDFT | {"relator_designado": "Beltrana de Tal", "local_publicacao": "DJE"},
            "TJDFT, 3ª Turma Cível, Apelação Cível nº 0701234-56.2023.8.07.0001, "
            "Rel. p/ acórdão Beltrana de Tal, j. 08/10/2026, publ. DJE 21/10/2026.",
        ),
        (
            TJDFT | {"local_publicacao": None},
            "TJDFT, 3ª Turma Cível, Apelação Cível nº 0701234-56.2023.8.07.0001, "
            "Rel. Fulano de Tal, j. 08/10/2026, publ. 21/10/2026.",
        ),
        (
            TJDFT | {"data_publicacao": None, "data_julgamento": None},
            "TJDFT, 3ª Turma Cível, Apelação Cível nº 0701234-56.2023.8.07.0001, "
            "Rel. Fulano de Tal.",
        ),
        (
            TJPR | {"classe_citacao": None, "relator": None, "orgao_julgador": None},
            "TJPR, Recurso Inominado Cível nº 0011412-20.2025.8.16.0069, j. 06/10/2026, "
            "DJEN de 14/10/2026.",
        ),
        (
            TJPR | {"relator": "Des. Fulano de Tal", "data_julgamento": None},
            "TJPR, 3ª Turma Recursal dos Juizados Especiais, Recurso Inominado nº "
            "0011412-20.2025.8.16.0069, Rel. Des. Fulano de Tal, DJEN de 14/10/2026.",
        ),
    ],
    ids=[
        "djen",
        "djen-sem-julgamento",
        "tjdft",
        "designado",
        "sem-local",
        "sem-datas",
        "faltas",
        "titulo",
    ],
)
def test_citacao(acordao: dict[str, Any], esperado: str) -> None:
    assert citar(acordao) == esperado
    assert "None" not in citar(acordao)


def test_designado_so_vale_no_tjdft() -> None:
    assert "Rel. Fulano de Tal" in citar(TJPR | {"relator_designado": "Outro"})


# --- RRF ------------------------------------------------------------------------------


def test_rrf_soma_os_ramos() -> None:
    fundidos = rrf({"texto": [1, 2, 3], "vetor": [3, 4]}, k=60)
    # 2 e 4 empatam (2º lugar num ramo cada): desempate pelo menor id.
    assert [d for d, _ in fundidos] == [3, 1, 2, 4]
    pontos = dict(fundidos)
    assert pontos[3] == pytest.approx(1 / 63 + 1 / 61)
    assert pontos[1] == pytest.approx(1 / 61)


def test_rrf_pesos_desempates_e_limite() -> None:
    # Mesmo escore: vence a melhor posição; depois o menor id.
    assert [d for d, _ in rrf({"a": [7, 8], "b": [8, 7]})] == [7, 8]
    assert [d for d, _ in rrf({"a": [5], "b": [4]})] == [4, 5]
    pesado = rrf({"texto": [1, 2], "vetor": [2]}, {"texto": 1.0, "vetor": 0.0})
    assert [d for d, _ in pesado] == [1, 2]
    assert len(rrf({"a": list(range(500))}, limite=200)) == 200
    assert rrf({}) == []
    # Documento repetido num ramo conta uma vez.
    assert dict(rrf({"a": [1, 1, 2]}))[1] == pytest.approx(1 / 61)


def test_paginacao_por_recorte() -> None:
    ids = list(range(45))
    assert pagina(ids, 1, 20) == list(range(20))
    assert pagina(ids, 3, 20) == list(range(40, 45))
    assert pagina(ids, 4, 20) == []


# --- tsquery e trecho -----------------------------------------------------------------


def test_expressao_com_frase_e_exclusao() -> None:
    expressao = expressao_tsquery('herança "partilha de bens" -testamento')
    assert expressao is not None
    sql, parametros = expressao
    assert parametros == {
        "q_palavras": "herança",
        "q_frase0": "partilha de bens",
        "q_exclusao0": "testamento",
    }
    assert "phraseto_tsquery" in sql and "&& !! plainto_tsquery" in sql
    assert expressao_tsquery("-testamento") is None
    assert expressao_tsquery("   ") is None
    # Hífen dentro da palavra não é exclusão.
    assert expressao_tsquery("pré-natal")[1] == {"q_palavras": "pré-natal"}  # type: ignore[index]


def test_trecho_escapado_so_com_mark() -> None:
    assert marcar("a <b> herança & c") == "a &lt;b&gt; <mark>herança</mark> &amp; c"
    assert inicio_da_ementa("<i>x</i>") == "&lt;i&gt;x&lt;/i&gt;"
    longo = inicio_da_ementa("palavra " * 100, tamanho=30)
    assert longo.endswith(" …") and len(longo) <= 32


# --- Limite de taxa -------------------------------------------------------------------


def test_limitador_janela_deslizante() -> None:
    agora = [0.0]
    limitador = LimitadorJanela(2, 60, relogio=lambda: agora[0])
    assert limitador.registrar("ip") is None
    assert limitador.registrar("ip") is None
    assert limitador.registrar("ip") == pytest.approx(60)
    assert limitador.registrar("outro") is None
    agora[0] = 30
    assert limitador.registrar("ip") == pytest.approx(30)
    agora[0] = 60.5
    assert limitador.registrar("ip") is None
    with pytest.raises(ErroApi) as erro:
        verificar(limitador, "ip")
        verificar(limitador, "ip")
    assert erro.value.status == 429 and erro.value.cabecalhos["Retry-After"] == "60"


def _request(cabecalhos: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(k.encode(), v.encode()) for k, v in cabecalhos.items()],
            "client": ("10.0.0.1", 1234),
        }
    )


def test_ip_do_cliente() -> None:
    pedido = _request({"x-forwarded-for": "203.0.113.9, 10.0.0.2"})
    assert ip_do_cliente(pedido, confiar_x_forwarded_for=False) == "10.0.0.1"
    assert ip_do_cliente(pedido, confiar_x_forwarded_for=True) == "203.0.113.9"
    assert ip_do_cliente(_request({}), confiar_x_forwarded_for=True) == "10.0.0.1"
