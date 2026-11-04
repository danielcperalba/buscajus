"""F6-01: contrato dos conectores com respostas malformadas (sem rede, sem banco).

Os casos de sucesso, paginação, 429, hash divergente, nova versão e dia sem caderno estão em
test_djen_conector, test_tjdft_conector e test_fechamento_*; aqui ficam as respostas fora do
formato, que precisam virar erro seguro (sem conteúdo da fonte na mensagem).
"""

import io
import json
import zipfile
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from buscajus.core.config import ConfigHttp
from buscajus.ingest.conector import ErroColeta
from buscajus.ingest.djen import caderno
from buscajus.ingest.djen import normalizacao as norm_djen
from buscajus.ingest.http import ClienteHttp, TentativasEsgotadas

from .conftest import RelogioFalso

URL = "https://comunicaapi.exemplo"
DIA = date(2026, 10, 15)
METADADOS = f"{URL}/api/v1/caderno/TJPR/{DIA.isoformat()}/D"


@pytest.fixture
def cliente(relogio: RelogioFalso) -> Iterator[ClienteHttp]:
    with ClienteHttp(ConfigHttp(), 1.0, relogio=relogio) as cliente:
        yield cliente


def _metadados(**alteracoes: Any) -> dict[str, Any]:
    base = {"versao": 1, "hash": "AB" * 32, "status": "Processado", "total_comunicacoes": 3}
    return base | alteracoes


# --- Metadados do caderno ---------------------------------------------------------------


@respx.mock
def test_metadados_validos_normalizam_hash_e_status(cliente: ClienteHttp) -> None:
    respx.get(METADADOS).respond(200, json=_metadados(status=" Processado ", url=None))
    meta = caderno.obter_metadados(cliente, URL, "TJPR", DIA)
    assert meta is not None
    assert (meta.hash, meta.status, meta.total, meta.url) == ("ab" * 32, "Processado", 3, "")


@pytest.mark.parametrize(
    ("resposta", "mensagem"),
    [
        (httpx.Response(403, text="bloqueado"), "HTTP 403"),
        (httpx.Response(200, text="<html>"), "não são JSON"),
        (httpx.Response(200, json=[1, 2]), "formato inesperado"),
        (httpx.Response(200, json=_metadados(versao="1")), "versao"),
        (httpx.Response(200, json=_metadados(versao=True)), "versao"),
        (httpx.Response(200, json=_metadados(hash=None)), "hash ou status"),
        (httpx.Response(200, json=_metadados(status=3)), "hash ou status"),
        (httpx.Response(200, json=_metadados(total_comunicacoes="3")), "total_comunicacoes"),
    ],
)
@respx.mock
def test_metadados_malformados_viram_erro_seguro(
    cliente: ClienteHttp, resposta: httpx.Response, mensagem: str
) -> None:
    respx.get(METADADOS).mock(return_value=resposta)
    with pytest.raises(ErroColeta, match=mensagem) as erro:
        caderno.obter_metadados(cliente, URL, "TJPR", DIA)
    assert "bloqueado" not in str(erro.value) and "<html>" not in str(erro.value)


@respx.mock
def test_metadados_sem_caderno_e_5xx_persistente(cliente: ClienteHttp) -> None:
    respx.get(METADADOS).respond(404)
    assert caderno.obter_metadados(cliente, URL, "TJPR", DIA) is None
    respx.get(METADADOS).respond(503)
    with pytest.raises(TentativasEsgotadas, match="HTTP 503"):
        caderno.obter_metadados(cliente, URL, "TJPR", DIA)


# --- ZIP do caderno ---------------------------------------------------------------------


def _zip(destino: Path, entradas: dict[str, bytes | None]) -> Path:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for nome, conteudo in entradas.items():
            if conteudo is None:
                zf.writestr(zipfile.ZipInfo(nome), b"")  # diretório (nome termina em /)
            else:
                zf.writestr(nome, conteudo)
    destino.write_bytes(buffer.getvalue())
    return destino


def _pagina(*itens: Any) -> bytes:
    return json.dumps({"count": len(itens), "items": list(itens)}).encode()


def test_zip_valido_ignora_diretorios(tmp_path: Path) -> None:
    arquivo = _zip(tmp_path / "c.zip", {"pasta/": None, "TJPR-1.json": _pagina({"id": 1})})
    assert list(caderno.ler_comunicacoes(arquivo)) == [{"id": 1}]
    assert caderno.sha256_arquivo(arquivo) == caderno.sha256_arquivo(arquivo)


@pytest.mark.parametrize(
    ("entradas", "mensagem"),
    [
        ({"leia-me.txt": b"x"}, "não é JSON"),
        ({"TJPR-1.json": b"{quebrado"}, "JSON inválida"),
        ({"TJPR-1.json": b'{"count": 0}'}, "sem a lista items"),
        ({"TJPR-1.json": b"[]"}, "sem a lista items"),
        ({"TJPR-1.json": _pagina("texto solto")}, "não é objeto"),
    ],
)
def test_zip_malformado_vira_erro_seguro(
    tmp_path: Path, entradas: dict[str, bytes | None], mensagem: str
) -> None:
    arquivo = _zip(tmp_path / "c.zip", entradas)
    with pytest.raises(ErroColeta, match=mensagem) as erro:
        list(caderno.ler_comunicacoes(arquivo))
    assert "TJPR-1" not in str(erro.value) and "leia-me" not in str(erro.value)


def test_entrada_grande_demais(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(caderno, "LIMITE_BYTES_ENTRADA", 10)
    arquivo = _zip(tmp_path / "c.zip", {"TJPR-1.json": _pagina({"id": 1})})
    with pytest.raises(ErroColeta, match="maior que o limite") as erro:
        list(caderno.ler_comunicacoes(arquivo))
    # Nome fora do formato esperado não entra no diagnóstico.
    assert "TJPR-1" not in str(erro.value) and "nome fora do padrão" in str(erro.value)


def test_entrada_grande_tem_diagnostico_com_nome_e_tamanho(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    nome = "TJPR-D-2099-10-29_17.json"
    pagina = _pagina(*({"id": i, "texto": "x" * 50} for i in range(20)))
    arquivo = _zip(tmp_path / "c.zip", {nome: pagina})
    # Acima do alerta: processa normalmente e registra só nome e tamanho.
    monkeypatch.setattr(caderno, "ALERTA_BYTES_ENTRADA", 100)
    with caplog.at_level("WARNING", logger=caderno.__name__):
        assert len(list(caderno.ler_comunicacoes(arquivo))) == 20
    registro = next(r for r in caplog.records if r.getMessage() == "entrada grande no caderno")
    assert registro.entrada == nome and registro.bytes == len(pagina)  # type: ignore[attr-defined]
    assert "xxxx" not in caplog.text
    # Acima do limite: erro com nome e tamanho, sem conteúdo.
    monkeypatch.setattr(caderno, "LIMITE_BYTES_ENTRADA", 100)
    with pytest.raises(ErroColeta, match="maior que o limite") as erro:
        list(caderno.ler_comunicacoes(arquivo))
    assert nome in str(erro.value) and "descompactado" in str(erro.value)


def test_leitura_em_streaming_com_blocos_pequenos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Itens cortados em qualquer ponto do bloco (números, escapes, acentos) saem inteiros."""
    monkeypatch.setattr(caderno, "BLOCO_LEITURA", 7)
    itens = [
        {"id": 123456789, "valor": -1.5e3, "nulo": None, "ok": True},
        {"id": 2, "texto": 'Ementa de Acórdão "aspas" \\ barra', "lista": [1, [2, {}]]},
        {"id": 3, "tipoDocumento": "Ementa de Acórdão", "texto": "ç" * 40},
        {},
    ]
    corpo = json.dumps({"items": itens, "count": len(itens)}, indent=2).encode()
    arquivo = _zip(tmp_path / "c.zip", {"TJPR-1.json": b"\xef\xbb\xbf" + corpo})
    assert list(caderno.ler_comunicacoes(arquivo)) == itens

    vazia = _zip(tmp_path / "v.zip", {"TJPR-1.json": b'{"count": 0, "items": []}'})
    assert list(caderno.ler_comunicacoes(vazia)) == []


@pytest.mark.parametrize(
    ("conteudo", "mensagem"),
    [
        (b'{"count": 1, "items": [{"id": 1}]} lixo', "JSON inválida"),
        (b'{"count": 1, "items": [{"id": 1} {"id": 2}]}', "JSON inválida"),
        (b'{"count": 1, "items": [{"id": 1}', "JSON inválida"),
        (b'{"items": null}', "sem a lista items"),
        (b'{"count": 1 "items": []}', "JSON inválida"),
        (b'{"count": 1, "items": ["\xff"]}', "JSON inválida"),
    ],
)
def test_streaming_rejeita_json_malformado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, conteudo: bytes, mensagem: str
) -> None:
    monkeypatch.setattr(caderno, "BLOCO_LEITURA", 5)
    arquivo = _zip(tmp_path / "c.zip", {"TJPR-1.json": conteudo})
    with pytest.raises(ErroColeta, match=mensagem):
        list(caderno.ler_comunicacoes(arquivo))


def test_comunicacao_grande_demais(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(caderno, "BLOCO_LEITURA", 16)
    monkeypatch.setattr(caderno, "LIMITE_CARACTERES_ITEM", 200)
    pequena = {"id": 1, "texto": "x" * 50}
    arquivo = _zip(tmp_path / "c.zip", {"TJPR-1.json": _pagina(pequena, {"texto": "x" * 1000})})
    lidas: list[dict[str, Any]] = []
    with pytest.raises(ErroColeta, match="comunicação maior que o limite"):
        lidas.extend(caderno.ler_comunicacoes(arquivo))
    assert lidas == [pequena]


def test_arquivo_que_nao_e_zip(tmp_path: Path) -> None:
    arquivo = tmp_path / "c.zip"
    arquivo.write_bytes(b"isto nao e um zip")
    with pytest.raises(ErroColeta, match="não é um ZIP válido"):
        list(caderno.ler_comunicacoes(arquivo))


# --- Campos estruturados do DJEN --------------------------------------------------------


def test_conversoes_de_campos_do_djen() -> None:
    assert norm_djen._texto_curto(None) is None
    assert norm_djen._texto_curto("  &Oacute;rg&atilde;o   X  ") == "Órgão X"
    assert norm_djen._texto_curto("   ") is None
    assert norm_djen._data("2026-10-15T00:00:00") == date(2026, 10, 15)
    assert norm_djen._data("15/10/2026") is None
    assert norm_djen._data(None) is None
    assert norm_djen._data("2026-13-40") is None
    sem_fuso = norm_djen._data_hora("2026-10-15T10:00:00")
    assert sem_fuso is not None and sem_fuso.tzinfo is not None
    assert norm_djen._data_hora("ontem") is None
    assert norm_djen._data_hora("") is None
    assert norm_djen._inteiro(True) is None
    assert norm_djen._inteiro(" 460 ") == 460
    assert norm_djen._inteiro("4a") is None
    assert norm_djen._inteiro(7) == 7
