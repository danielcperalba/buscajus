import gzip
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from buscajus.ingest.bruto import (
    ArmazenamentoBruto,
    ErroListaBranca,
    caminho_caderno,
    caminho_pagina,
)

LISTA_BRANCA = frozenset({"id", "texto", "numero_processo"})


@pytest.fixture
def bruto(tmp_path: Path) -> ArmazenamentoBruto:
    return ArmazenamentoBruto(tmp_path)


def test_caminhos_por_fonte() -> None:
    assert caminho_caderno("TJPR", date(2026, 10, 15), 2) == "djen/TJPR/2026-10-15/v2.jsonl.gz"
    assert (
        caminho_pagina("tjdft", "TJDFT", date(2026, 10, 20), 3)
        == "tjdft/TJDFT/2026-10-20/p00003.jsonl.gz"
    )


def test_grava_jsonl_gz_com_sha256(bruto: ArmazenamentoBruto, tmp_path: Path) -> None:
    itens = [{"id": 1, "texto": "Ementa: AÇÃO."}, {"id": 2, "texto": "outra"}]
    arquivo = bruto.gravar("djen/TJPR/2026-10-15/v1.jsonl.gz", itens, LISTA_BRANCA)

    caminho = tmp_path / "djen/TJPR/2026-10-15/v1.jsonl.gz"
    conteudo = caminho.read_bytes()
    assert arquivo.sha256 == hashlib.sha256(conteudo).hexdigest()
    assert arquivo.bytes == len(conteudo)
    assert arquivo.itens == 2
    linhas = gzip.decompress(conteudo).decode().splitlines()
    assert [json.loads(linha) for linha in linhas] == itens
    assert list(bruto.ler(arquivo.caminho_relativo)) == itens


def test_arquivo_so_contem_campos_da_lista_branca(bruto: ArmazenamentoBruto) -> None:
    arquivo = bruto.gravar("x/p.jsonl.gz", [{"id": 1, "texto": "t"}], LISTA_BRANCA)
    for item in bruto.ler(arquivo.caminho_relativo):
        assert set(item) <= LISTA_BRANCA


def test_recusa_item_com_campo_fora_da_lista_branca(
    bruto: ArmazenamentoBruto, tmp_path: Path
) -> None:
    itens = [{"id": 1, "texto": "t"}, {"id": 2, "texto": "t", "destinatarios": ["NOME"]}]
    with pytest.raises(ErroListaBranca, match="destinatarios") as erro:
        bruto.gravar("djen/TJPR/2026-10-15/v1.jsonl.gz", itens, LISTA_BRANCA)
    # A mensagem traz o nome do campo, nunca o valor.
    assert "NOME" not in str(erro.value)
    assert not any(tmp_path.rglob("*"))


def test_mesmo_conteudo_gera_mesmo_hash(bruto: ArmazenamentoBruto) -> None:
    itens = [{"texto": "t", "id": 1}]
    primeiro = bruto.gravar("a.jsonl.gz", itens, LISTA_BRANCA)
    segundo = bruto.gravar("a.jsonl.gz", [{"id": 1, "texto": "t"}], LISTA_BRANCA)
    assert primeiro.sha256 == segundo.sha256


def test_regravar_substitui_sem_deixar_temporario(
    bruto: ArmazenamentoBruto, tmp_path: Path
) -> None:
    bruto.gravar("a.jsonl.gz", [{"id": 1}], LISTA_BRANCA)
    bruto.gravar("a.jsonl.gz", [{"id": 2}], LISTA_BRANCA)
    assert list(bruto.ler("a.jsonl.gz")) == [{"id": 2}]
    assert [p.name for p in tmp_path.iterdir()] == ["a.jsonl.gz"]


@pytest.mark.parametrize("caminho", ["/etc/x.jsonl.gz", "../fora.jsonl.gz", "a/../../b.gz"])
def test_recusa_caminho_fora_do_diretorio(bruto: ArmazenamentoBruto, caminho: str) -> None:
    with pytest.raises(ValueError, match="relativo"):
        bruto.gravar(caminho, [], LISTA_BRANCA)
