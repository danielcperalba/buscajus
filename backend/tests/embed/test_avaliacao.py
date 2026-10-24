"""Ferramenta de avaliação (F3-04) e conjunto de consultas (F3-01), sem modelo real."""

import csv
import math
from pathlib import Path

import pytest
import yaml

from buscajus.embed.avaliacao import (
    CAMPOS_POOL,
    Consulta,
    avaliar,
    carregar_consultas,
    exportar_pool,
    gerar_pool,
    importar_julgamentos,
    mrr,
    ndcg,
    recall,
)
from buscajus.embed.indice import Resultado

CONSULTAS = Path(__file__).parents[2] / "eval" / "consultas.yaml"


class SistemaFixo:
    """Sistema falso com rankings fixos por consulta."""

    def __init__(self, nome: str, rankings: dict[str, list[str]]) -> None:
        self.nome = nome
        self._rankings = rankings

    def buscar(self, consulta: str, k: int) -> list[Resultado]:
        return [Resultado(d, 1.0 / (i + 1)) for i, d in enumerate(self._rankings[consulta][:k])]


def test_ndcg() -> None:
    relevancia = {"a": 2, "b": 1}
    assert ndcg(["a", "b", "c"], relevancia) == pytest.approx(1.0)
    invertido = (1 / math.log2(2) + 3 / math.log2(3)) / (3 / math.log2(2) + 1 / math.log2(3))
    assert ndcg(["b", "a"], relevancia) == pytest.approx(invertido)
    assert ndcg(["x"], relevancia) == 0.0
    assert ndcg(["a"], {}) == 0.0
    # Só os 10 primeiros contam.
    assert ndcg([*"xxxxxxxxxx", "a"], {"a": 2}) == 0.0


def test_recall_e_mrr() -> None:
    relevancia = {"a": 2, "b": 1, "c": 0}
    assert recall(["a", "x", "c"], relevancia) == 0.5
    assert recall(["x"], {"c": 0}) == 0.0
    assert mrr(["x", "c", "b", "a"], relevancia) == pytest.approx(1 / 3)
    assert mrr(["x"], relevancia) == 0.0


def test_pool_sem_repeticao_com_posicoes(tmp_path: Path) -> None:
    consultas = [Consulta("q1", "herança"), Consulta("q2", "pensão")]
    sistemas = [
        SistemaFixo("vetorial", {"herança": ["1", "2", "3"], "pensão": ["9"]}),
        SistemaFixo("texto", {"herança": ["3", "4"], "pensão": []}),
    ]
    pool = gerar_pool(consultas, sistemas, k=2)
    assert [(i.consulta.id, i.documento_id, i.sistemas) for i in pool] == [
        ("q1", "1", {"vetorial": 1}),
        ("q1", "3", {"texto": 1}),
        ("q1", "2", {"vetorial": 2}),
        ("q1", "4", {"texto": 2}),
        ("q2", "9", {"vetorial": 1}),
    ]
    destino = tmp_path / "pool.csv"
    exportar_pool(pool, {"1": "PARTILHA   DE BENS " * 50}, destino, tamanho_trecho=20)
    with destino.open(encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    assert list(linhas[0]) == list(CAMPOS_POOL)
    assert linhas[0]["trecho"] == "PARTILHA DE BENS PAR"
    assert linhas[1]["sistemas"] == "texto#1"
    assert {linha["relevancia"] for linha in linhas} == {""}


def test_importar_julgamentos(tmp_path: Path) -> None:
    arquivo = tmp_path / "julgado.csv"
    arquivo.write_text(
        "consulta_id,consulta,documento_id,sistemas,trecho,relevancia\n"
        "q1,herança,1,v#1,,2\nq1,herança,2,v#2,,\nq1,herança,3,t#1,, 0\n",
        encoding="utf-8",
    )
    assert importar_julgamentos(arquivo) == {("q1", "1"): 2, ("q1", "3"): 0}
    arquivo.write_text(
        "consulta_id,consulta,documento_id,sistemas,trecho,relevancia\nq1,x,1,,,3\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="relevância inválida"):
        importar_julgamentos(arquivo)


def test_avaliar_por_sistema() -> None:
    consultas = [Consulta("q1", "herança"), Consulta("q2", "pensão"), Consulta("q3", "sem")]
    julgamentos = {("q1", "1"): 2, ("q1", "2"): 0, ("q2", "9"): 1}
    sistemas = [
        SistemaFixo("bom", {"herança": ["1", "2"], "pensão": ["9"]}),
        SistemaFixo("ruim", {"herança": ["2", "x"], "pensão": ["x", "y", "9"]}),
    ]
    bom, ruim = avaliar(consultas, sistemas, julgamentos)
    assert bom.consultas == 2  # q3 não tem julgamento
    assert (bom.ndcg_10, bom.recall_50, bom.mrr) == (1.0, 1.0, 1.0)
    assert ruim.mrr == pytest.approx((0 + 1 / 3) / 2)
    assert ruim.recall_50 == pytest.approx(0.5)
    assert bom.latencia_p95_ms >= 0
    assert set(bom.resumo()) == {
        "sistema",
        "consultas",
        "ndcg@10",
        "recall@50",
        "mrr",
        "latencia_p50_ms",
        "latencia_p95_ms",
    }
    with pytest.raises(ValueError, match="nenhuma consulta"):
        avaliar(consultas, sistemas, {})


def test_consultas_versionadas() -> None:
    consultas = carregar_consultas(CONSULTAS)
    assert 45 <= len(consultas) <= 60
    assert len({c.texto for c in consultas}) == len(consultas)
    herança = next(c for c in consultas if c.texto == "disputa por herança familiar")
    assert herança.obrigatoria
    assert all(c.area and c.esperado for c in consultas)
    # Proposta inicial: continua pendente até a revisão jurídica.
    conteudo = yaml.safe_load(CONSULTAS.read_text(encoding="utf-8"))
    assert conteudo["status"] == "pendente de revisão jurídica"


def test_ids_repetidos_sao_rejeitados(tmp_path: Path) -> None:
    arquivo = tmp_path / "c.yaml"
    arquivo.write_text("consultas:\n- {id: a, texto: x}\n- {id: a, texto: y}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="repetidos"):
        carregar_consultas(arquivo)
