"""Índice temporário da avaliação (F3-04) e comando ``buscajus eval``, com banco e sem modelo."""

import csv
import dataclasses
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine

from buscajus import cli
from buscajus.db.engine import obter_engine
from buscajus.embed.indice import (
    BuscaTextoPostgres,
    Documento,
    IndiceVetorialMemoria,
    documentos_ativos,
)
from buscajus.ingest.modelos import AcordaoNormalizado
from buscajus.ingest.upsert import upsert

from .ajuda import EmbedderSacoDePalavras

pytestmark = pytest.mark.banco

# Ementas sintéticas.
EMENTAS = {
    "1": "DIREITO CIVIL. INVENTÁRIO. PARTILHA DE BENS ENTRE HERDEIROS. Herança do pai.",
    "2": "DIREITO DO CONSUMIDOR. PLANO DE SAÚDE. NEGATIVA DE COBERTURA. Dano moral.",
    "3": "PENAL. VIOLÊNCIA DOMÉSTICA. LESÃO CORPORAL. Palavra da vítima.",
    "4": "DIREITO CIVIL. SUCESSÃO. Direito do companheiro à herança. Partilha.",
}
BASE = AcordaoNormalizado(
    fonte="tjdft",
    id_fonte="",
    tribunal="TJDFT",
    numero_processo="00010011020998079999",
    numero_processo_mascara="0001001-10.2099.8.07.9999",
    numero_processo_valido=True,
    ementa="",
    link_oficial="https://jurisdf.tjdft.jus.br/acordaos/x",
)


@pytest.fixture
def acordaos(banco: Engine) -> dict[str, str]:
    """Insere as ementas e devolve o id do acórdão (texto) de cada chave."""
    with banco.begin() as conexao:
        for chave, ementa in EMENTAS.items():
            acordao = dataclasses.replace(BASE, id_fonte=f"u{chave}", ementa=ementa)
            upsert(conexao, acordao, coleta_bruta_id=None, cancelado=False)
    return {d.texto: d.id for d in documentos_ativos(banco)}


def test_full_text_ignora_acento_e_usa_or(banco: Engine, acordaos: dict[str, str]) -> None:
    resultados = BuscaTextoPostgres(banco).buscar("heranca partilha", 10)
    ids = [r.id for r in resultados]
    assert set(ids) == {acordaos[EMENTAS["1"]], acordaos[EMENTAS["4"]]}
    assert BuscaTextoPostgres(banco).buscar("xyzw", 10) == []
    assert BuscaTextoPostgres(banco).buscar("'&|!", 10) == []  # sem erro de sintaxe


def test_indice_vetorial_um_resultado_por_acordao() -> None:
    longo = Documento("10", " ".join(["partilha herança"] * 300))  # vários trechos
    curto = Documento("11", "plano de saúde")
    indice = IndiceVetorialMemoria(
        EmbedderSacoDePalavras(), [longo, curto], tokens_por_trecho=100, sobreposicao=10
    )
    assert indice.trechos > 2
    resultados = indice.buscar("herança e partilha", 5)
    assert [r.id for r in resultados] == ["10", "11"]
    assert resultados[0].pontuacao > resultados[1].pontuacao
    assert indice.nome == "vetorial:falso/saco-de-palavras"
    assert IndiceVetorialMemoria(EmbedderSacoDePalavras(), []).buscar("x", 5) == []


@pytest.fixture
def ambiente(url_banco_teste: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("BUSCAJUS_DATABASE_URL", url_banco_teste)
    monkeypatch.setattr(
        cli, "EmbedderSentenceTransformers", lambda nome, **_: EmbedderSacoDePalavras(nome)
    )
    obter_engine.cache_clear()
    yield
    obter_engine.cache_clear()


@pytest.mark.usefixtures("ambiente")
def test_cli_eval_pool_e_metricas(
    acordaos: dict[str, str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    consultas = tmp_path / "consultas.yaml"
    consultas.write_text(
        "consultas:\n- {id: q1, texto: disputa por herança familiar}\n"
        "- {id: q2, texto: plano de saúde negou tratamento}\n",
        encoding="utf-8",
    )
    pool = tmp_path / "pool.csv"
    modelo = ["--modelo", "intfloat/multilingual-e5-small@rev1"]
    assert (
        cli.main(["eval", "pool", "--consultas", str(consultas), "--saida", str(pool), *modelo])
        == 0
    )
    assert json.loads(capsys.readouterr().out)["consultas"] == 2
    with pool.open(encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    sistemas = {s.split("#")[0] for linha in linhas for s in linha["sistemas"].split("; ")}
    assert sistemas == {"vetorial:intfloat/multilingual-e5-small", "texto"}

    # Julgamento: só as ementas de herança são relevantes para q1.
    for linha in linhas:
        relevante = linha["consulta_id"] == "q1" and "HERAN" in linha["trecho"].upper()
        linha["relevancia"] = "2" if relevante else "0"
    julgado = tmp_path / "julgado.csv"
    with julgado.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(linhas[0]))
        escritor.writeheader()
        escritor.writerows(linhas)
    argumentos = ["eval", "metricas", "--consultas", str(consultas), "--julgamentos", str(julgado)]
    assert cli.main([*argumentos, *modelo]) == 0
    relatorio = {r["sistema"]: r for r in json.loads(capsys.readouterr().out)}
    assert set(relatorio) == {"vetorial:intfloat/multilingual-e5-small", "texto"}
    assert relatorio["texto"]["consultas"] == 2


@pytest.mark.usefixtures("ambiente")
def test_cli_eval_sem_grupo_embeddings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def ausente(*_a: object, **_k: object) -> None:
        raise ModuleNotFoundError("sem", name="sentence_transformers")

    monkeypatch.setattr(cli, "EmbedderSentenceTransformers", ausente)
    consultas = tmp_path / "c.yaml"
    consultas.write_text("consultas:\n- {id: q1, texto: x}\n", encoding="utf-8")
    argumentos = ["eval", "pool", "--consultas", str(consultas), "--saida", str(tmp_path / "p")]
    assert cli.main([*argumentos, "--modelo", "m"]) == 2
    assert "uv sync --group embeddings" in capsys.readouterr().err
