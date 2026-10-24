"""As fixtures sintéticas do DJEN (F1-02) estão em dia e cobrem os casos previstos."""

import hashlib
import html
import importlib.util
import io
import json
import re
import unicodedata
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import pytest

from fixtures.djen import PASTA, arquivos, dados, numero_cnj

TIPO_EMENTA = "Ementa de Acórdão"


def normalizar(texto: str) -> str:
    texto = html.unescape(html.unescape(texto))
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return " ".join(texto.upper().split())


def itens(nome_zip: str) -> list[dict[str, Any]]:
    with zipfile.ZipFile(PASTA / nome_zip) as zf:
        return [i for nome in zf.namelist() for i in json.loads(zf.read(nome))["items"]]


@pytest.fixture(scope="module")
def caderno() -> list[dict[str, Any]]:
    return itens(f"caderno-{dados.DATA}-v1.zip")


def test_arquivos_versionados_batem_com_o_gerador() -> None:
    esperados = arquivos()
    presentes = {p.name for p in PASTA.iterdir() if p.suffix in {".zip", ".json"}}
    assert presentes == set(esperados)
    divergentes = [n for n, c in esperados.items() if (PASTA / n).read_bytes() != c]
    assert divergentes == [], "rode `uv run python -m fixtures.djen` em backend/tests"


def test_metadados_e_hash(caderno: list[dict[str, Any]]) -> None:
    meta = json.loads((PASTA / f"metadados-{dados.DATA}-v1.json").read_text())
    conteudo = (PASTA / f"caderno-{dados.DATA}-v1.zip").read_bytes()
    assert meta["hash"] == hashlib.sha256(conteudo).hexdigest()
    assert meta["total_comunicacoes"] == len(caderno)
    errado = json.loads((PASTA / f"metadados-{dados.DATA}-v1-hash-incorreto.json").read_text())
    assert errado["hash"] != meta["hash"]
    assert (
        json.loads((PASTA / f"metadados-{dados.DATA}-nao-processado.json").read_text())["status"]
        != "Processado"
    )


def test_tipo_documento_vem_escapado_no_json() -> None:
    with zipfile.ZipFile(PASTA / f"caderno-{dados.DATA}-v1.zip") as zf:
        bruto = zf.read(zf.namelist()[0]).decode()
    assert "Ementa de Ac\\u00f3rd\\u00e3o" in bruto
    assert "Ementa de Acórdão" not in bruto


def test_processos_ficticios(caderno: list[dict[str, Any]]) -> None:
    for item in caderno:
        assert re.fullmatch(r"\d{7}\d{2}2099816\d{4}", item["numero_processo"])
        assert item["numero_processo"].endswith("9999")


def test_formato_dos_cadernos_recentes(caderno: list[dict[str, Any]]) -> None:
    """F1-01: sem numeroprocessocommascara, meiocompleto e idOrgao; com dataenvio."""
    for item in caderno:
        assert not {"numeroprocessocommascara", "meiocompleto", "idOrgao"} & set(item)
        assert "dataenvio" in item
        assert item["status"] == "P"
    assert any(item["link"] is None for item in caderno)


def test_segunda_versao(caderno: list[dict[str, Any]]) -> None:
    v2 = {i["id"]: i for i in itens(f"caderno-{dados.DATA}-v2.zip")}
    assert dados.AUSENTE_NO_V2 not in v2
    assert dados.AUSENTE_NO_V2 in {i["id"] for i in caderno}
    assert v2[dados.CANCELADA_NO_V2]["ativo"] is False
    assert v2[dados.CANCELADA_NO_V2]["data_cancelamento"] is not None


def test_caderno_sem_ementas() -> None:
    assert all(
        i["tipoDocumento"] != TIPO_EMENTA for i in itens(f"caderno-{dados.DATA_SEM_EMENTAS}-v1.zip")
    )


def test_cobre_os_casos_de_anonimizacao(caderno: list[dict[str, Any]]) -> None:
    ementas = [i for i in caderno if i["tipoDocumento"] == TIPO_EMENTA]
    outras = [i for i in caderno if i["tipoDocumento"] != TIPO_EMENTA]
    assert len(ementas) == 20
    texto_ementas = " | ".join(normalizar(i["texto"]) for i in ementas)
    texto_outras = " | ".join(normalizar(i["texto"]) for i in outras)
    destinatarios = {normalizar(d["nome"]) for i in caderno for d in i["destinatarios"]} | {
        normalizar(a["advogado"]["nome"]) for i in caderno for a in i["destinatarioadvogados"]
    }

    for nome in dados.NOMES_CAMADA_1 + dados.NOMES_CAMADA_2:
        assert nome in texto_ementas, nome
    for nome in dados.NOMES_CAMADA_2:
        assert not any(nome in d for d in destinatarios), nome
    for preservado in dados.PRESERVADOS:
        assert normalizar(preservado) in texto_ementas, preservado
    for cpf in dados.CPFS + dados.NAO_CPFS:
        assert cpf in texto_ementas, cpf
    assert dados.MARCADOR_DESCARTADO in texto_outras
    assert dados.MARCADOR_DESCARTADO not in texto_ementas
    assert any("&amp;" in i["texto"] for i in ementas)
    assert any(re.search(r"&#\d+;", i["texto"]) for i in ementas)
    assert any("<table" not in i["texto"] for i in ementas)
    assert any("Data do Julgamento" not in i["texto"] for i in ementas)
    assert any(i["ativo"] is False for i in ementas)


def _spike() -> Any:
    caminho = Path(__file__).parent.parent / "scripts" / "spike_caderno_djen.py"
    spec = importlib.util.spec_from_file_location("spike_caderno_djen", caminho)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_script_do_spike_so_imprime_agregados(caderno: list[dict[str, Any]]) -> None:
    spike = _spike()
    agregados = spike.Agregados()
    for item in caderno * 25:  # repete para passar dos limiares de frequência
        agregados.item(item)
    saida = io.StringIO()
    with redirect_stdout(saida):
        agregados.imprimir()
    texto = saida.getvalue()
    normalizado = normalizar(texto)

    assert '"ementas": 500' in texto
    assert "\"'processo:'\": 475" in texto  # uma das 20 ementas não tem tabela
    nomes = {normalizar(d["nome"]) for i in caderno for d in i["destinatarios"]}
    nomes |= {
        normalizar(a["advogado"]["nome"]) for i in caderno for a in i["destinatarioadvogados"]
    }
    vazados = [n for n in nomes | set(dados.NOMES_CAMADA_2) if n in normalizado]
    assert vazados == []
    assert dados.MARCADOR_DESCARTADO not in normalizado
    for item in caderno:
        assert item["numero_processo"] not in texto
        assert numero_cnj(int(item["numero_processo"][:7]))[1] not in texto
        assert item["hash"] not in texto
    for relator in dados.RELATORES:
        assert normalizar(relator) not in normalizado
    assert "2099" not in texto
