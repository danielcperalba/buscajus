"""Camada 2 com o modelo de NER (F1-36, F1-37).

Os testes sem marcador não usam modelo real. Os marcados com ``ner`` carregam o modelo fixado
na configuração a partir de ``BUSCAJUS_TEST_DIRETORIO_MODELOS`` (preenchido por
``buscajus modelos baixar-ner``; job ``backend-ner`` do CI) e rodam sobre dados sintéticos.
"""

import importlib.util
import os
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from buscajus.core.config import ConfigAnonimizacao
from buscajus.ingest.anonimizacao import Rejeicao
from buscajus.ingest.anonimizacao.modelo_ner import (
    Palavra,
    carregar_detector,
    juntar_palavras,
    variante_caixa,
    versao_detector,
)
from buscajus.ingest.anonimizacao.pipeline import AnonimizadorDjen, ErroAnonimizacao
from buscajus.ingest.djen.parser import analisar
from buscajus.ingest.texto import chave
from buscajus.ingest.tjdft.anonimizacao import AnonimizadorTjdft
from fixtures.djen import dados, item_ementa
from fixtures.tjdft import dados as dados_tjdft

from .tjdft_ajuda import DIA, fixture

SCRIPT = Path(__file__).parents[2] / "scripts" / "ner_avaliacao.py"


def test_variante_de_caixa_tem_o_mesmo_comprimento() -> None:
    texto = "A VÍTIMA MARIA DAS GRAÇAS FONSECA RECONHECEU O RÉU (art. 157 do Cp)."
    variante = variante_caixa(texto)
    assert len(variante) == len(texto)
    assert variante == "A Vítima Maria das Graças Fonseca Reconheceu O Réu (art. 157 do Cp)."
    assert variante_caixa("Texto já em caixa mista.") == "Texto já em caixa mista."


def _palavras(texto: str, pessoas: dict[str, float]) -> list[Palavra]:
    return [
        Palavra(m.start(), m.end(), pessoas.get(m.group(), 0.0))
        for m in re.finditer(r"\w+|[^\w\s]", texto)
    ]


def test_palavras_viram_entidades_com_particulas_no_meio() -> None:
    texto = "A vítima Joana D'Arc da Silva e o réu Fulano, vulgo Tonhão."
    probs = {"Joana": 0.9, "D": 0.6, "Arc": 0.6, "Silva": 0.8, "Fulano": 0.3, "Tonhão": 0.15}
    entidades = juntar_palavras(texto, _palavras(texto, probs), limiar=0.1)
    assert [texto[e.inicio : e.fim] for e in entidades] == [
        "Joana D'Arc da Silva",
        "Fulano",
        "Tonhão",
    ]
    acima = juntar_palavras(texto, _palavras(texto, probs), limiar=0.5)
    assert [texto[e.inicio : e.fim] for e in acima] == ["Joana D'Arc da Silva"]


def test_particula_sozinha_nao_vira_entidade() -> None:
    texto = "Recurso de Fulano e de Beltrano."
    entidades = juntar_palavras(texto, _palavras(texto, {"Fulano": 0.9, "Beltrano": 0.9}), 0.5)
    assert [texto[e.inicio : e.fim] for e in entidades] == ["Fulano", "Beltrano"]


def test_sem_modelo_configurado_nao_ha_detector(tmp_path: Path) -> None:
    assert carregar_detector(ConfigAnonimizacao(modelo_ner=None), tmp_path) is None


def test_modelo_sem_revisao_falha_fechado(tmp_path: Path) -> None:
    with pytest.raises(ErroAnonimizacao, match="revisão"):
        carregar_detector(ConfigAnonimizacao(revisao_ner=None), tmp_path)


def test_pesos_ausentes_falham_fechado_sem_baixar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sem rede: o carregamento é local_files_only, então nem tenta baixar.
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    with pytest.raises(ErroAnonimizacao, match="NER"):
        carregar_detector(ConfigAnonimizacao(), tmp_path)
    assert not any((tmp_path / "ner").rglob("*.safetensors"))


def test_versao_do_detector_identifica_modelo_revisao_e_limiar() -> None:
    config = ConfigAnonimizacao()
    assert versao_detector(config) == "bertimbau-base-lener_br@824f48e-l0.1"


# --- Com o modelo real (marcador ner) ------------------------------------------------------


@pytest.fixture(scope="module")
def detector() -> Any:
    pytest.importorskip("transformers")
    diretorio = os.environ.get("BUSCAJUS_TEST_DIRETORIO_MODELOS")
    if not diretorio:
        pytest.skip("BUSCAJUS_TEST_DIRETORIO_MODELOS não definida")
    return carregar_detector(ConfigAnonimizacao(), Path(diretorio))


@pytest.fixture(scope="module")
def avaliacao() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ner_avaliacao", SCRIPT)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.mark.ner
def test_nenhum_nome_sintetico_escapa(detector: Any, avaliacao: ModuleType) -> None:
    """Meta do F1-37: 0 vazamentos no conjunto sintético, com as exceções preservadas."""
    placares, _ = avaliacao.avaliar(detector.detectar)
    total = placares["total"]
    assert total.anonimizar > 100
    assert total.vazados == 0
    assert total.manter_preservados == total.manter


@pytest.mark.ner
def test_camada2_real_no_djen(detector: Any) -> None:
    anonimizar = AnonimizadorDjen(detector)
    for ementa in dados.EMENTAS:
        resultado = anonimizar(item_ementa(ementa))
        assert not isinstance(resultado, Rejeicao), ementa.id
        texto = chave(analisar(resultado["texto"]).ementa)
        for nome in dados.NOMES_CAMADA_1 + dados.NOMES_CAMADA_2:
            assert chave(nome) not in texto, (ementa.id, nome)
        assert analisar(resultado["texto"]).relator == ementa.relator
    assert anonimizar.substituicoes["camada2"] > 0


@pytest.mark.ner
def test_camada2_real_no_tjdft(detector: Any) -> None:
    anonimizar = AnonimizadorTjdft(detector)
    for registro in fixture(DIA, 0)["registros"]:
        if registro.get("segredoJustica") is not False:
            continue
        resultado = anonimizar(registro)
        assert isinstance(resultado, dict)
        corrido = chave(f"{resultado.get('ementa') or ''} {resultado.get('decisao') or ''}")
        for nome in (dados_tjdft.VITIMA, dados_tjdft.REU):
            assert chave(nome) not in corrido
