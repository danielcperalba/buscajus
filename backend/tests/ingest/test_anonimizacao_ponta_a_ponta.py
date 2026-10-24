"""Caderno sintético → conector → anonimização real (NER falso) → bruto e banco."""

import gzip
import json
import logging
import re
from pathlib import Path

import pytest
import respx
from sqlalchemy import Engine, text

from buscajus.core.config import ConfigHttp
from buscajus.ingest.anonimizacao.pipeline import criar_anonimizador
from buscajus.ingest.bruto import ArmazenamentoBruto
from buscajus.ingest.djen.campos import LISTA_BRANCA
from buscajus.ingest.djen.conector import ConectorDjen
from buscajus.ingest.http import ClienteHttp
from buscajus.ingest.runner import Orquestrador, Resultado
from buscajus.ingest.texto import chave
from fixtures.djen import dados

from .anonimizacao_ajuda import DetectorFalso
from .conftest import RelogioFalso
from .djen_ajuda import DIA, HOJE, area_vazia, config_djen, servir_caderno

pytestmark = pytest.mark.banco


@respx.mock
def test_nada_de_pessoal_chega_ao_bruto_nem_ao_banco(
    banco: Engine, tmp_path: Path, relogio: RelogioFalso, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    servir_caderno(respx.mock, DIA)
    cliente = ClienteHttp(ConfigHttp(), 1.0, relogio=relogio)
    tmp = tmp_path / "tmp-cadernos"
    conector = ConectorDjen(
        config_djen(), cliente, criar_anonimizador(DetectorFalso()), tmp, hoje=lambda: HOJE
    )
    raw = tmp_path / "raw"
    (resumo,) = Orquestrador(banco, conector, ArmazenamentoBruto(raw)).executar(
        conector.planejar("TJPR", DIA, DIA)
    )
    assert resumo.resultado is Resultado.CONCLUIDA
    assert resumo.contadores.aceitos == 20
    assert resumo.contadores.rejeitados_anonimizacao == []

    (arquivo,) = raw.rglob("*.jsonl.gz")
    linhas = [json.loads(linha) for linha in gzip.decompress(arquivo.read_bytes()).splitlines()]
    assert len(linhas) == 20
    assert all(set(item) <= LISTA_BRANCA for item in linhas)

    with banco.connect() as conexao:
        banco_texto = " ".join(
            str(v)
            for t in ("caderno_djen", "coleta_bruta")
            for linha in conexao.execute(text(f"SELECT * FROM {t}"))  # noqa: S608
            for v in linha
        )
    logs = " ".join(f"{r.getMessage()} {vars(r)}" for r in caplog.records)
    bruto = chave(" ".join(item["texto"] for item in linhas)).upper()

    # Destinatários PF (inclusive parciais, MEI sem o sufixo, espólio sem o prefixo),
    # advogados, vítimas e testemunhas: nenhum sobra no bruto.
    for nome in dados.NOMES_CAMADA_1 + dados.NOMES_CAMADA_2:
        assert nome not in bruto, nome
    for cpf in dados.CPFS:
        assert not re.search(rf"(?<![\d.]){re.escape(cpf)}(?![\d-])", bruto), cpf
    for preservado in (*dados.PRESERVADOS, *dados.RELATORES):
        assert chave(preservado).upper() in bruto, preservado
    for numero in dados.NAO_CPFS:
        assert numero in bruto
    # Nem no banco nem nos logs aparecem nomes, marcadores de descartadas ou a URL.
    destinatarios = {chave(p.nome).upper() for e in dados.EMENTAS for p in e.destinatarios} | {
        chave(o.nome).upper() for x in dados.OUTRAS for o in x.destinatarios
    }
    for alvo in (chave(banco_texto).upper(), chave(logs).upper()):
        assert dados.MARCADOR_DESCARTADO not in alvo
        assert not [d for d in destinatarios if d in alvo]
        assert "X-AMZ" not in alvo
    assert area_vazia(tmp)
