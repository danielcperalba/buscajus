"""Recorte da ementa nos acórdãos do eproc do TJRJ (F1-50), com HTML sintético.

O formato imita o medido nos cadernos reais só por agregados: partes e advogados antes do
título EMENTA, a ementa em parágrafos, o título ACÓRDÃO e a linha "Rio de Janeiro, <data>.".
Nomes são marcadores; processos do ano 2099.
"""

import json
import zipfile
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest

from buscajus.core.config import ConfigDjen
from buscajus.ingest.djen.caderno import MetadadosDjen
from buscajus.ingest.djen.conector import ConectorDjen
from buscajus.ingest.djen.parser import analisar
from buscajus.ingest.djen.recorte import RECORTADORES, recortar_eproc, recortar_tjrj
from buscajus.ingest.http import ClienteHttp

CABECALHO = (
    "<div><p>APELAÇÃO CÍVEL Nº 0001234-56.2099.8.19.0001/RJ</p>"
    "<p>RELATORA: DESEMBARGADORA SICRANA SINTETICA</p>"
    "<p>APELANTE: FULANO MARCADOR DE TAL</p><p>ADVOGADO(A): BELTRANO MARCADOR (OAB RJ999999)</p>"
    "<p>APELADO: BANCO SINTETICO S.A.</p></div>"
)
EMENTA = (
    "<p><strong>EMENTA</strong></p>"
    "<p>DIREITO DO CONSUMIDOR. APELAÇÃO CÍVEL. NEGATIVAÇÃO INDEVIDA. RECURSO DESPROVIDO.</p>"
    "<p>I. CASO EM EXAME</p><p>1. Apelação contra sentença que reconheceu dano moral.</p>"
    "<p>II. QUESTÃO EM DISCUSSÃO</p><p>2. Saber se a inscrição foi indevida.</p>"
    "<p>Tese de julgamento: &ldquo;A inscrição indevida gera dano moral.&rdquo;</p>"
)
ACORDAO = (
    "<p><strong>ACÓRDÃO</strong></p>"
    "<p>Vistos e relatados estes autos em que são partes as acima indicadas, a Egrégia "
    "1ª Câmara de Direito Privado decidiu negar provimento ao recurso de FULANO MARCADOR.</p>"
    "<p>Rio de Janeiro, 05 de novembro de 2026.</p>"
    "<p>DESEMBARGADORA SICRANA SINTETICA, Relatora</p>"
)


def _html(*partes: str) -> str:
    return "<div>" + "".join(partes) + "</div>"


def test_recorta_so_a_ementa_e_a_data() -> None:
    recortado = recortar_eproc(_html(CABECALHO, EMENTA, ACORDAO))
    assert recortado is not None
    for fora in ("FULANO", "BELTRANO", "SICRANA", "OAB", "Vistos", "BANCO SINTETICO"):
        assert fora not in recortado

    analisado = analisar(recortado)
    assert analisado.origem == "tabela"
    assert analisado.data_julgamento == date(2026, 11, 5)
    assert analisado.ementa.startswith("DIREITO DO CONSUMIDOR. APELAÇÃO CÍVEL.")
    # Um parágrafo por bloco da fonte (o site separa os tópicos por essas quebras).
    assert "I. CASO EM EXAME\n\n1. Apelação contra sentença" in analisado.ementa
    assert analisado.ementa.endswith("“A inscrição indevida gera dano moral.”")
    assert analisado.relator is None


def test_blocos_aninhados_e_quebras_de_linha() -> None:
    ementa = (
        "<div><div><p>EMENTA:</p></div><div><p>PENAL. HABEAS CORPUS.<br>ORDEM DENEGADA "
        "por ausência de constrangimento ilegal.</p></div></div>"
    )
    recortado = recortar_eproc(_html(CABECALHO, ementa, ACORDAO))
    assert recortado is not None
    assert analisar(recortado).ementa == (
        "PENAL. HABEAS CORPUS.\nORDEM DENEGADA por ausência de constrangimento ilegal."
    )


def test_texto_com_marcacao_escapada_nao_vira_html() -> None:
    ementa = (
        "<p>EMENTA</p>"
        "<p>CIVIL. Cláusula &lt;script&gt;alert(1)&lt;/script&gt; nula, recurso provido.</p>"
    )
    recortado = recortar_eproc(_html(ementa, ACORDAO))
    assert recortado is not None
    assert "<script>" not in recortado
    assert "<script>alert(1)</script>" in analisar(recortado).ementa


@pytest.mark.parametrize(
    ("linha", "esperada"),
    [
        ("Rio de Janeiro, 1º de março de 2026.", date(2026, 3, 1)),
        ("Rio de Janeiro, 9 de dezembro de 2025", date(2025, 12, 9)),
        ("Niterói, 9 de dezembro de 2025.", None),
        ("Rio de Janeiro, 9 de brumário de 2025.", None),
    ],
)
def test_data_do_julgamento(linha: str, esperada: date | None) -> None:
    acordao = f"<p>ACÓRDÃO</p><p>Decidiu negar provimento.</p><p>{linha}</p>"
    recortado = recortar_eproc(_html(EMENTA, acordao))
    assert recortado is not None
    assert analisar(recortado).data_julgamento == esperada


@pytest.mark.parametrize(
    "texto",
    [
        "",
        _html(CABECALHO, ACORDAO),  # sem EMENTA
        _html(CABECALHO, EMENTA),  # sem ACÓRDÃO
        _html(ACORDAO, EMENTA),  # fora de ordem
        _html("<p>EMENTA</p>", ACORDAO),  # ementa vazia
        "texto sem marcação nenhuma",
    ],
)
def test_formato_inesperado_nao_aproveita_o_item(texto: str) -> None:
    assert recortar_eproc(texto) is None
    assert recortar_tjrj({"id": 1, "texto": texto}) is None


def test_conector_so_entrega_a_ementa_ao_anonimizador(tmp_path: Path) -> None:
    """O cabeçalho com partes nunca chega ao anonimizador nem ao bruto (F1-50)."""
    itens = [
        {"id": 1, "tipoDocumento": "Acórdão", "texto": _html(CABECALHO, EMENTA, ACORDAO)},
        {"id": 2, "tipoDocumento": "Acórdão", "texto": _html(CABECALHO, ACORDAO)},
        {"id": 3, "tipoDocumento": "Despacho", "texto": "<p>FULANO MARCADOR</p>"},
    ]
    arquivo = tmp_path / "caderno.zip"
    with zipfile.ZipFile(arquivo, "w") as zf:
        zf.writestr("TJRJ-D-2099-01-05_1.json", json.dumps({"count": 3, "items": itens}))
    vistos: list[Mapping[str, Any]] = []

    def anonimizar(item: Mapping[str, Any]) -> dict[str, Any]:
        vistos.append(item)
        return dict(item)

    config = ConfigDjen(tribunais=["TJRJ"])
    conector = ConectorDjen(config, cast(ClienteHttp, None), anonimizar, tmp_path)
    meta = MetadadosDjen(versao=1, hash="h", status="Processado", total=3, url="")
    aceitos, contadores = conector._ler(arquivo, meta, "TJRJ")

    assert [i["id"] for i in aceitos] == [1]
    assert (contadores.recebidos, contadores.aceitos) == (3, 1)
    assert (contadores.descartados, contadores.falhas_parser) == (1, 1)
    assert [v["id"] for v in vistos] == [1]
    assert "FULANO" not in vistos[0]["texto"] and "BANCO SINTETICO" not in vistos[0]["texto"]


def test_recortador_preserva_os_demais_campos() -> None:
    item = {"id": 7, "hash": "h", "tipoDocumento": "Acórdão", "texto": _html(EMENTA, ACORDAO)}
    recortado = RECORTADORES["TJRJ"](item)
    assert recortado is not None
    assert {k: v for k, v in recortado.items() if k != "texto"} == {
        k: v for k, v in item.items() if k != "texto"
    }
    assert recortado["texto"].startswith("<table>")
    assert "TJPR" not in RECORTADORES
