"""Busca com o banco (F4-03, F4-04, F4-07 a F4-11, F4-13): acórdãos sintéticos."""

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine

from buscajus.api import app as modulo_app
from buscajus.api.consulta import NumeroNaConsulta
from buscajus.api.esquemas import FiltrosBusca
from buscajus.api.limite import LimitadorJanela
from buscajus.busca.servico import ServicoPostgres

from .conftest import ACORDAOS, acordao, inserir, numero

pytestmark = pytest.mark.banco


def _busca(cliente: TestClient, **parametros: Any) -> dict[str, Any]:
    resposta = cliente.get("/api/v1/busca", params=parametros)
    assert resposta.status_code == 200, resposta.text
    corpo: dict[str, Any] = resposta.json()
    return corpo


def _ids(corpo: dict[str, Any]) -> list[int]:
    return [r["id"] for r in corpo["resultados"]]


# --- Ramo full-text (F4-04) e /busca (F4-08) ------------------------------------------


def test_busca_sem_acento_com_or_e_so_ativos(cliente: TestClient, ids: dict[str, int]) -> None:
    corpo = _busca(cliente, q="disputa por heranca familiar")
    assert corpo["tipo"] == "hibrida" and corpo["numero_processo"] is None
    encontrados = set(_ids(corpo))
    assert {ids["heranca"], ids["heranca_embargos"], ids["companheira"]} <= encontrados
    for nome in ("cancelado", "removido", "quarentena", "duplicado", "plano"):
        assert ids[nome] not in encontrados
    assert corpo["total"] == len(encontrados) == 3


def test_resultado_tem_trecho_destacado_citacao_e_aviso(
    cliente: TestClient, ids: dict[str, int]
) -> None:
    corpo = _busca(cliente, q="partilha herança")
    primeiro = corpo["resultados"][0]
    assert primeiro["id"] == ids["heranca"]  # os dois termos: melhor posição
    assert "<mark>" in primeiro["trecho"]
    assert primeiro["citacao"].startswith("TJDFT, 3ª Turma Cível, Apelação Cível nº ")
    assert primeiro["citacao"].endswith("publ. PJe 21/10/2026.")
    assert primeiro["aviso"].startswith("Texto reproduzido")
    tjpr = next(r for r in corpo["resultados"] if r["id"] == ids["tjpr_partilha"])
    # O ts_headline descarta as tags da ementa; o único HTML do trecho é <mark>.
    assert "<script>" not in tjpr["trecho"]
    assert tjpr["trecho"].replace("<mark>", "").replace("</mark>", "").count("<") == 0
    assert tjpr["citacao"].endswith("DJEN de 14/10/2026.")


def test_frase_entre_aspas_e_exclusao(cliente: TestClient, ids: dict[str, int]) -> None:
    assert _ids(_busca(cliente, q='"partilha de bens"')) == [ids["tjpr_partilha"]]
    sem_testamento = set(_ids(_busca(cliente, q="herança -testamento")))
    assert ids["companheira"] not in sem_testamento and ids["heranca"] in sem_testamento


def test_consulta_sem_resultado_e_invalida(cliente: TestClient, ids: dict[str, int]) -> None:
    assert _busca(cliente, q="xyzw")["total"] == 0
    assert _busca(cliente, q="-herança")["total"] == 0
    assert cliente.get("/api/v1/busca", params={"q": "   "}).status_code == 422


def test_paginacao(cliente: TestClient, banco: Engine) -> None:
    inserir(
        banco,
        *(
            acordao(f"p{i}", f"PREVIDÊNCIA COMPLEMENTAR. Resgate {i}.", sequencial=100 + i)
            for i in range(25)
        ),
    )
    primeira = _busca(cliente, q="previdência")
    segunda = _busca(cliente, q="previdência", pagina=2)
    assert (primeira["total"], len(primeira["resultados"]), len(segunda["resultados"])) == (
        25,
        20,
        5,
    )
    assert not set(_ids(primeira)) & set(_ids(segunda))
    assert _busca(cliente, q="previdência", pagina=3)["resultados"] == []
    assert cliente.get("/api/v1/busca", params={"q": "x", "pagina": 11}).status_code == 422


# --- Número de processo (F4-03) -------------------------------------------------------


def test_numero_completo_e_busca_exata_por_data(cliente: TestClient, ids: dict[str, int]) -> None:
    digitos, mascara = numero(10)
    for consulta in (mascara, digitos, f"processo nº {mascara}"):
        corpo = _busca(cliente, q=consulta)
        assert (corpo["tipo"], corpo["numero_processo"]) == ("processo", mascara)
        # Do mais recente (embargos, 15/10) ao mais antigo (apelação, 08/10).
        assert _ids(corpo) == [ids["heranca_embargos"], ids["heranca"]]
        assert "<mark>" not in corpo["resultados"][0]["trecho"]


def test_prefixo_e_numero_com_texto(cliente: TestClient, ids: dict[str, int]) -> None:
    _, mascara = numero(10)
    corpo = _busca(cliente, q=mascara[:15])
    assert corpo["tipo"] == "processo" and ids["heranca"] in _ids(corpo)
    filtrado = _busca(cliente, q=f"embargos {mascara}")
    assert filtrado["tipo"] == "hibrida"
    assert _ids(filtrado) == [ids["heranca_embargos"]]
    assert _busca(cliente, q=numero(999)[1])["total"] == 0


def test_rota_de_processo(cliente: TestClient, ids: dict[str, int]) -> None:
    digitos, mascara = numero(10)
    corpo = cliente.get(f"/api/v1/processos/{mascara}").json()
    assert corpo["numero_processo"] == mascara
    assert [a["id"] for a in corpo["acordaos"]] == [ids["heranca_embargos"], ids["heranca"]]
    assert cliente.get(f"/api/v1/processos/{digitos}").json() == corpo
    prefixo = cliente.get(f"/api/v1/processos/{mascara[:10]}").json()
    assert prefixo["numero_processo"] == digitos[:9]
    assert cliente.get(f"/api/v1/processos/{numero(999)[1]}").status_code == 404
    # Só ativos: o processo do removido não aparece.
    assert cliente.get(f"/api/v1/processos/{numero(15)[1]}").status_code == 404


def test_prefixo_limitado(banco: Engine, ids: dict[str, int]) -> None:
    servico = ServicoPostgres(banco)
    servico._config = servico._config.model_copy(update={"limite_prefixo": 2})
    with banco.connect() as conexao:
        assert len(_prefixo(servico, conexao)) == 2


def _prefixo(servico: ServicoPostgres, conexao: Connection) -> list[int]:
    return servico._ids_do_processo(
        conexao, NumeroNaConsulta("00000", completo=False), FiltrosBusca(), 200
    )


# --- Filtros (F4-07) ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("parametros", "esperados"),
    [
        ({"tribunal": "tjpr"}, {"tjpr_partilha"}),
        ({"orgao": "6ª Turma Cível"}, {"companheira"}),
        ({"classe": 1689}, {"heranca_embargos"}),
        ({"relator": "Sicrano de Tal"}, {"companheira"}),
        ({"relator": "beltrana de tal"}, {"companheira"}),  # relator designado
        ({"data_inicio": "2026-10-10"}, {"heranca_embargos", "tjpr_partilha"}),
        ({"data_fim": "2026-09-30"}, {"companheira"}),
        ({"tribunal": "TJDFT", "data_inicio": "2026-10-01", "data_fim": "2026-10-09"}, {"heranca"}),
    ],
)
def test_filtros(
    cliente: TestClient, ids: dict[str, int], parametros: dict[str, Any], esperados: set[str]
) -> None:
    corpo = _busca(cliente, q="herança partilha", **parametros)
    assert set(_ids(corpo)) == {ids[n] for n in esperados}


def test_periodo_invertido(cliente: TestClient) -> None:
    resposta = cliente.get(
        "/api/v1/busca", params={"q": "x", "data_inicio": "2026-10-10", "data_fim": "2026-10-01"}
    )
    assert (resposta.status_code, resposta.json()["erro"]) == (422, "periodo_invalido")


# --- Ramo vetorial atrás da interface -------------------------------------------------


class RamoVetorialFalso:
    disponivel = True

    def __init__(self, ids: list[int]) -> None:
        self._ids = ids
        self.chamadas: list[FiltrosBusca] = []

    def buscar(
        self,
        conexao: Connection,
        consulta: str,
        filtros: FiltrosBusca,
        numero: NumeroNaConsulta | None,
        *,
        limite: int,
    ) -> list[tuple[int, float]]:
        self.chamadas.append(filtros)
        return [(i, 1.0) for i in self._ids[:limite]]


def test_ramo_vetorial_entra_na_fusao(banco: Engine, ids: dict[str, int]) -> None:
    falso = RamoVetorialFalso([ids["plano"], ids["heranca"]])
    app = modulo_app.criar_app()
    app.state.servico = ServicoPostgres(banco, ramo_vetorial=falso)
    with TestClient(app) as cliente:
        corpo = _busca(cliente, q="herança", tribunal="TJDFT")
    resultados = _ids(corpo)
    assert resultados[0] == ids["heranca"]  # nos dois ramos
    assert ids["plano"] in resultados  # só no vetorial
    plano = next(r for r in corpo["resultados"] if r["id"] == ids["plano"])
    assert plano["trecho"].startswith("DIREITO DO CONSUMIDOR")  # sem destaque: início
    assert falso.chamadas[0].tribunal == "TJDFT"  # mesmos filtros nos dois ramos


def test_ramo_vetorial_desligado_por_padrao(banco: Engine) -> None:
    assert ServicoPostgres(banco)._vetorial.disponivel is False


# --- Detalhe (F4-09) ------------------------------------------------------------------


def test_detalhe(cliente: TestClient, ids: dict[str, int]) -> None:
    corpo = cliente.get(f"/api/v1/acordaos/{ids['companheira']}").json()
    assert corpo["ementa"].startswith("DIREITO CIVIL. UNIÃO ESTÁVEL")
    assert corpo["decisao"] == "CONHECIDO. DESPROVIDO. UNÂNIME."
    assert corpo["relator_designado"] == "Beltrana de Tal"
    assert "Rel. p/ acórdão Beltrana de Tal" in corpo["citacao"]
    cancelado = cliente.get(f"/api/v1/acordaos/{ids['cancelado']}")
    assert cancelado.status_code == 410
    assert cancelado.json()["erro"] == "cancelado" and cancelado.json()["link_oficial"]
    removido = cliente.get(f"/api/v1/acordaos/{ids['removido']}")
    assert (removido.status_code, removido.json()["erro"]) == (410, "removido")
    assert removido.json()["link_oficial"] is None
    for nome in ("quarentena", "duplicado"):
        assert cliente.get(f"/api/v1/acordaos/{ids[nome]}").status_code == 404
    assert cliente.get("/api/v1/acordaos/999999").status_code == 404


# --- Filtros e relatores (F4-11) ------------------------------------------------------


def test_filtros_com_cache(cliente: TestClient, banco: Engine, ids: dict[str, int]) -> None:
    filtros = cliente.get("/api/v1/filtros").json()
    assert filtros["tribunais"] == [
        {"valor": "TJDFT", "rotulo": "TJDFT", "total": 4},
        {"valor": "TJPR", "rotulo": "TJPR", "total": 1},
    ]
    assert {"valor": "1689", "rotulo": "Embargos de Declaração Cível", "total": 1} in filtros[
        "classes"
    ]
    assert {o["valor"] for o in filtros["orgaos"]} == {
        "3ª Turma Cível",
        "6ª Turma Cível",
        "3ª Turma Recursal",
    }
    inserir(banco, acordao("novo", "Outro.", sequencial=50, orgao="1ª Turma Cível"))
    assert cliente.get("/api/v1/filtros").json() == filtros  # do cache


def test_relatores(cliente: TestClient, ids: dict[str, int]) -> None:
    assert cliente.get("/api/v1/relatores", params={"prefixo": "fula"}).json() == [
        {"nome": "Fulano de Tal", "chave": "fulano de tal"}
    ]
    nomes = [
        r["nome"] for r in cliente.get("/api/v1/relatores", params={"prefixo": "de tal"}).json()
    ]
    assert nomes == ["Fulano de Tal", "Sicrano de Tal"]
    assert cliente.get("/api/v1/relatores", params={"prefixo": "100%"}).json() == []


# --- Limite de taxa (F4-13) -----------------------------------------------------------


def test_limite_de_taxa_por_ip_e_por_tipo(banco: Engine, ids: dict[str, int]) -> None:
    app = modulo_app.criar_app()
    app.state.servico = ServicoPostgres(banco)
    app.state.limitadores = {
        "consulta": LimitadorJanela(2, 60),
        "remocao": LimitadorJanela(1, 3600),
    }
    pedido = {
        "referencia": numero(10)[1],
        "motivo": "Meu nome aparece no texto.",
        "email": "pessoa@exemplo.invalid",
    }
    with TestClient(app) as cliente:
        assert cliente.get("/api/v1/busca", params={"q": "herança"}).status_code == 200
        assert cliente.get(f"/api/v1/acordaos/{ids['heranca']}").status_code == 200
        bloqueada = cliente.get("/api/v1/filtros")
        assert bloqueada.status_code == 429
        assert bloqueada.json()["erro"] == "limite_excedido"
        assert int(bloqueada.headers["retry-after"]) >= 1
        # A remoção tem limite próprio.
        assert cliente.post("/api/v1/remocao", json=pedido).status_code == 201
        assert cliente.post("/api/v1/remocao", json=pedido).status_code == 429
        assert cliente.get("/api/v1/saude").status_code in (200, 503)  # sem limite


def test_limites_padrao_na_configuracao() -> None:
    app = modulo_app.criar_app()
    assert app.state.config.api.consultas_por_minuto == 60
    assert app.state.config.api.remocoes_por_hora == 5


def test_data_referencia_do_tjpr_e_a_disponibilizacao(ids: dict[str, int]) -> None:
    item = ACORDAOS["tjpr_partilha"]
    assert item.data_julgamento is None and item.data_disponibilizacao == date(2026, 10, 14)


@pytest.mark.parametrize("proxies", [0, 1])
def test_ips_falsos_em_sequencia_continuam_no_limite(
    banco: Engine, ids: dict[str, int], monkeypatch: pytest.MonkeyPatch, proxies: int
) -> None:
    """Segurança: variar o X-Forwarded-For a cada requisição não escapa do limite."""
    monkeypatch.setenv("BUSCAJUS_API__PROXIES_CONFIAVEIS", str(proxies))
    app = modulo_app.criar_app()
    app.state.servico = ServicoPostgres(banco)
    app.state.limitadores["consulta"] = LimitadorJanela(3, 60)
    # Com um proxy, ele acrescenta o IP real (sempre o mesmo) depois do que o cliente mandou.
    real = "203.0.113.9"
    with TestClient(app) as cliente:
        status = []
        for i in range(6):
            falso = f"198.51.100.{i}"
            cabecalho = f"{falso}, {real}" if proxies else falso
            resposta = cliente.get("/api/v1/filtros", headers={"x-forwarded-for": cabecalho})
            status.append(resposta.status_code)
    assert status == [200, 200, 200, 429, 429, 429]
    assert app.state.limitadores["consulta"].chaves == 1


# --- F6-05: consultas extremas ------------------------------------------------------


@pytest.mark.parametrize(
    "consulta",
    [
        "'&|!():*<>\\\"",
        "herança' OR 1=1 --",
        "herança & partilha | !testamento",
        '"frase sem fim',
        "-",
        "%_\\",
        "😀 herança",
    ],
)
def test_caracteres_especiais_nao_quebram_a_busca(
    cliente: TestClient, ids: dict[str, int], consulta: str
) -> None:
    corpo = _busca(cliente, q=consulta)
    assert {r["id"] for r in corpo["resultados"]} <= {
        ids[n] for n in ("heranca", "heranca_embargos", "companheira", "tjpr_partilha", "plano")
    }


def test_consulta_muito_longa(cliente: TestClient, ids: dict[str, int]) -> None:
    longa = ("herança " * 100).strip()  # 799 caracteres: a API corta em 500
    corpo = _busca(cliente, q=longa)
    assert len(corpo["consulta"]) == 500
    assert ids["heranca"] in _ids(corpo)
    excessiva = cliente.get("/api/v1/busca", params={"q": "x" * 1001})
    assert excessiva.status_code == 422


def test_cobertura_por_fonte_e_tribunal(cliente: TestClient, ids: dict[str, int]) -> None:
    """F7-04: a cobertura vem do banco (só acórdãos exibíveis)."""
    cobertura = cliente.get("/api/v1/cobertura").json()
    assert [(c["tribunal"], c["fonte"], c["acordaos"]) for c in cobertura] == [
        ("TJDFT", "tjdft", 4),
        ("TJPR", "djen", 1),
    ]
    tjdft = cobertura[0]
    assert (tjdft["desde"], tjdft["ate"]) == ("2026-09-01", "2026-10-15")
    assert tjdft["fonte_nome"] == "Jurisprudência do TJDFT"
