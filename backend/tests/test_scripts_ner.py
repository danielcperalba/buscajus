"""Scripts do F1-36 (amostragem e avaliação) sem modelos reais nem dados reais."""

import argparse
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from buscajus.ingest.anonimizacao.camada2 import Entidade
from buscajus.ingest.anonimizacao.nomes import trechos_protegidos
from buscajus.ingest.djen.parser import analisar
from buscajus.ingest.texto import chave
from fixtures.djen import dados, item_ementa

SCRIPTS = Path(__file__).parent.parent / "scripts"
REPO = Path(__file__).parents[2]


def _carregar(nome: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(nome, SCRIPTS / f"{nome}.py")
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="module")
def avaliacao() -> ModuleType:
    return _carregar("ner_avaliacao")


@pytest.fixture(scope="module")
def amostragem() -> ModuleType:
    return _carregar("ner_amostragem")


def test_marcacao_ida_e_volta(avaliacao: ModuleType) -> None:
    anotado = "A vítima [[Clotilde Ravanello]] e o {{Min. Bonifácio Cardeal}}."
    texto, marcas = avaliacao.ler_marcacao(anotado)
    assert texto == "A vítima Clotilde Ravanello e o Min. Bonifácio Cardeal."
    assert [(texto[m.inicio : m.fim], m.anonimizar) for m in marcas] == [
        ("Clotilde Ravanello", True),
        ("Min. Bonifácio Cardeal", False),
    ]
    assert avaliacao.marcar(texto, [Entidade(9, 27)]) == (
        "A vítima [[Clotilde Ravanello]] e o Min. Bonifácio Cardeal."
    )


def test_validacao(avaliacao: ModuleType) -> None:
    base = {"id_amostra": "a001", "estrato": "civel", "texto": "Texto da Fulana Tal."}
    assert avaliacao.problemas(base | {"texto_anotado": "Texto da [[Fulana Tal]]."}) == []
    assert avaliacao.problemas(base | {"texto_anotado": None}) == ["sem anotação"]
    assert "difere" in avaliacao.problemas(base | {"texto_anotado": "Texto da Fulana."})[0]
    desbalanceada = {"texto": "Texto da [[Fulana Tal.", "texto_anotado": "Texto da [[Fulana Tal."}
    assert "desbalanceada" in " ".join(avaliacao.problemas(base | desbalanceada))


def _registros() -> list[dict[str, Any]]:
    """Ementas sintéticas anotadas: vítimas e testemunhas a anonimizar; relator e ministro, não."""
    registros = []
    for i, ementa in enumerate(dados.EMENTAS, start=1):
        texto = analisar(item_ementa(ementa)["texto"]).ementa
        anonimizar = trechos_protegidos(texto, dados.NOMES_CAMADA_2)
        manter = trechos_protegidos(texto, ["Bonifácio Cardeal", "Teobaldo Siqueira Lins"])
        marcas = sorted([(a, b, True) for a, b in anonimizar] + [(a, b, False) for a, b in manter])
        partes, ultimo = [], 0
        for a, b, anon in marcas:
            partes += [texto[ultimo:a], "[[" if anon else "{{", texto[a:b], "]]" if anon else "}}"]
            ultimo = b
        partes.append(texto[ultimo:])
        estrato = "criminal" if "Criminal" in ementa.orgao else "civel"
        registros.append(
            {
                "id_amostra": f"a{i:03d}",
                "estrato": estrato,
                "texto": texto,
                "texto_anotado": "".join(partes),
            }
        )
    return registros


def _detector_falso(nomes: tuple[str, ...]) -> Any:
    def detectar(texto: str) -> list[tuple[Entidade, float]]:
        return [(Entidade(a, b), 0.8) for a, b in trechos_protegidos(texto, nomes)]

    return detectar


def test_metricas(avaliacao: ModuleType) -> None:
    registros = _registros()
    # Detecta duas das três vítimas/testemunhas e o ministro (que a exceção de título preserva).
    detectar = _detector_falso(
        ("Clotilde Ravanello", "Florisbela Mantovanelli", "Bonifácio Cardeal")
    )
    placares, _ = avaliacao.avaliar(registros, detectar, limiar=0.5)
    total = placares["total"]
    assert total.anonimizar == 3
    assert total.anonimizar_total == 2
    assert total.manter_preservados == total.manter == 2
    assert total.previstas == total.previstas_corretas == 2
    acima, _ = avaliacao.avaliar(registros, detectar, limiar=0.9)
    assert acima["total"].anonimizar_total == 0


def test_relatorio_so_tem_agregados(
    avaliacao: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entrada = tmp_path / "anotada.jsonl"
    avaliacao.gravar(entrada, _registros())
    monkeypatch.setattr(
        avaliacao, "carregar", lambda modelo, nome: _detector_falso(dados.NOMES_CAMADA_2)
    )
    relatorio = tmp_path / "avaliacao-ner.md"
    args = argparse.Namespace(entrada=entrada, relatorio=relatorio, spacy="x", lenerbr="y")
    assert avaliacao.cmd_avaliar(args) == 0
    conteudo = relatorio.read_text(encoding="utf-8")
    assert "## spacy" in conteudo and "limiar 0.9" in conteudo
    normalizado = chave(conteudo)
    nomes = [*dados.NOMES_CAMADA_1, *dados.NOMES_CAMADA_2, *dados.RELATORES, "Bonifacio Cardeal"]
    assert not [n for n in nomes if chave(n) in normalizado]
    assert "a001" not in conteudo
    # Nenhuma sequência de 6 palavras de qualquer ementa aparece no relatório.
    for registro in _registros():
        palavras = registro["texto"].split()
        for i in range(0, max(len(palavras) - 6, 0), 3):
            assert " ".join(palavras[i : i + 6]) not in conteudo


def test_estratos(amostragem: ModuleType) -> None:
    familia = {chave("11ª Câmara Cível"), chave("12ª Câmara Cível")}
    assert amostragem.estrato("3ª Câmara Criminal", familia) == "criminal"
    assert amostragem.estrato("12ª Câmara Cível", familia) == "familia"
    assert amostragem.estrato("3ª Turma Recursal dos Juizados Especiais", familia) == "civel"
    assert amostragem.SemNer().detectar("Clotilde Ravanello") == []


def test_amostragem_recusa_ci_e_repositorio(
    amostragem: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CI", "true")
    with pytest.raises(SystemExit, match="CI"):
        amostragem._verificar_ambiente(tmp_path / "fora")
    monkeypatch.delenv("CI")
    with pytest.raises(SystemExit, match="repositório"):
        amostragem._verificar_ambiente(REPO / "docs" / "amostra")
    amostragem._verificar_ambiente(REPO / "ner-avaliacao-privado")
    amostragem._verificar_ambiente(tmp_path / "fora")


def test_pasta_privada_esta_no_gitignore() -> None:
    assert (
        "ner-avaliacao-privado/" in (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    )
