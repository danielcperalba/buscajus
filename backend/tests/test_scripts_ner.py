"""Script do F1-36 (avaliação com ementas sintéticas) sem modelos reais."""

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

from buscajus.ingest.anonimizacao.camada2 import Entidade
from fixtures.ner import EMENTAS

SCRIPT = Path(__file__).parent.parent / "scripts" / "ner_avaliacao.py"
REPO = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def avaliacao() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ner_avaliacao", SCRIPT)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_marcacao(avaliacao: ModuleType) -> None:
    texto, marcas = avaliacao.ler_marcacao("A vítima [[Clotilde Ravanello]] e o {{Min. Fulano}}.")
    assert texto == "A vítima Clotilde Ravanello e o Min. Fulano."
    assert [(texto[m.inicio : m.fim], m.anonimizar) for m in marcas] == [
        ("Clotilde Ravanello", True),
        ("Min. Fulano", False),
    ]


def test_fixtures_bem_formadas(avaliacao: ModuleType) -> None:
    contextos = " ".join(e.texto for e in EMENTAS).lower()
    for contexto in ("vítima", "testemunha", "corréu", "o menor j.", "vulgo", '"[['):
        assert contexto in contextos, contexto
    for ementa in EMENTAS:
        texto, _marcas = avaliacao.ler_marcacao(ementa.texto)
        assert not re.search(r"\[\[|\]\]|\{\{|\}\}", texto), ementa.texto[:40]
        assert ementa.estrato in ("criminal", "familia", "civel")
    assert {e.fonte for e in EMENTAS} == {"djen", "tjdft"}


def _detector_perfeito(avaliacao: ModuleType, perder: int = 0) -> object:
    """'Detecta' exatamente os nomes marcados com [[ ]], menos os ``perder`` primeiros."""
    ouro: dict[str, list[Entidade]] = {}
    for ementa in EMENTAS:
        texto, marcas = avaliacao.ler_marcacao(ementa.texto)
        ouro[texto] = [Entidade(m.inicio, m.fim) for m in marcas if m.anonimizar]
    perdidos = set(list(ouro)[:perder])

    def detectar(texto: str) -> list[Entidade]:
        return ouro[texto][1:] if texto in perdidos else ouro[texto]

    return detectar


def test_metricas(avaliacao: ModuleType) -> None:
    placares, _ = avaliacao.avaliar(_detector_perfeito(avaliacao))
    total = placares["total"]
    assert total.vazados == 0 and total.manter_preservados == total.manter
    assert total.previstas == total.previstas_corretas == total.anonimizar
    placares, _ = avaliacao.avaliar(_detector_perfeito(avaliacao, perder=3))
    assert placares["total"].vazados == 3
    assert placares["total"].linha()["vazados"] == "3"


def test_scripts_da_anotacao_manual_foram_removidos() -> None:
    assert not (SCRIPT.parent / "ner_amostragem.py").exists()
    assert not (REPO / "docs" / "ner-anotacao.md").exists()


def test_pasta_privada_esta_no_gitignore() -> None:
    assert (
        "ner-avaliacao-privado/" in (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    )
