"""Anonimização do TJDFT (F2-12): camada 2 (NER) e CPF na ementa e na decisão."""

import re
from typing import Any

import pytest

from buscajus.ingest.anonimizacao import Rejeicao
from buscajus.ingest.anonimizacao.cpf import MASCARA
from buscajus.ingest.anonimizacao.pipeline import ErroAnonimizacao
from buscajus.ingest.tjdft import anonimizacao
from buscajus.ingest.tjdft.anonimizacao import AnonimizadorTjdft, criar_anonimizador
from fixtures.tjdft import dados

from .anonimizacao_ajuda import DetectorFalso
from .tjdft_ajuda import DIA, fixture, uuid

# O falso "reconhece" as pessoas citadas e também nomes que precisam ficar: magistrados do
# próprio acórdão, o desembargador citado no precedente e o epônimo.
NOMES_DETECTADOS = (
    dados.VITIMA,
    dados.REU,
    dados.REL_CRIMINAL,
    dados.DESIGNADO,
    dados.REVISOR,
    dados.DES_PRECEDENTE,
    "MARIA DA PENHA",
)


def registro(n: int) -> dict[str, Any]:
    regs = fixture(DIA, 0)["registros"]
    encontrado: dict[str, Any] = next(r for r in regs if r["uuid"] == uuid(n))
    return encontrado


@pytest.fixture
def anonimizar() -> AnonimizadorTjdft:
    return criar_anonimizador(DetectorFalso(NOMES_DETECTADOS))


def test_sem_ner_nao_ha_anonimizador() -> None:
    with pytest.raises(ErroAnonimizacao, match="NER"):
        criar_anonimizador(None)


def test_pessoas_e_cpfs_saem_e_excecoes_ficam(anonimizar: AnonimizadorTjdft) -> None:
    resultado = anonimizar(registro(5))
    assert isinstance(resultado, dict)
    ementa, decisao = resultado["ementa"], resultado["decisao"]
    for nome in dados.DEVEM_SUMIR:
        assert nome not in ementa
    assert "vítima T.C.P., inscrita" in ementa
    assert "O réu G.P.S. (CPF" in ementa
    for cpf in dados.CPFS:
        # O CNPJ sintético contém os 11 dígitos de um CPF, de propósito: ali não se mascara.
        assert not re.search(rf"(?<!\d){re.escape(cpf)}(?!\d)", ementa)
    assert ementa.count(MASCARA) == 2
    for numero in dados.NAO_CPFS:
        assert numero in ementa
    for preservado in dados.PRESERVADOS:
        assert preservado in ementa + decisao
    assert resultado["anonimizacao_versao"] == "cpf-1+ner-falso-1"
    assert resultado["anonimizacao_substituicoes"] == 4


def test_campos_fora_do_texto_nao_mudam(anonimizar: AnonimizadorTjdft) -> None:
    original = registro(5)
    resultado = anonimizar(original)
    assert isinstance(resultado, dict)
    iguais = set(original) - {"ementa", "decisao"}
    assert {c: resultado[c] for c in iguais} == {c: original[c] for c in iguais}


def test_registro_sem_pessoas_fica_igual(anonimizar: AnonimizadorTjdft) -> None:
    original = registro(1)
    resultado = anonimizar(original)
    assert isinstance(resultado, dict)
    assert (resultado["ementa"], resultado["decisao"]) == (original["ementa"], original["decisao"])
    assert resultado["anonimizacao_substituicoes"] == 0


def test_texto_em_formato_inesperado_e_recusado(anonimizar: AnonimizadorTjdft) -> None:
    resultado = anonimizar(registro(1) | {"ementa": ["lista"]})
    assert resultado == Rejeicao(uuid(1), "texto em formato inesperado")


def test_cpf_que_sobra_recusa_o_registro(
    anonimizar: AnonimizadorTjdft, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(anonimizacao, "mascarar_cpf", lambda texto: (texto, 0))
    resultado = anonimizar(registro(5))
    assert resultado == Rejeicao(uuid(5), "CPF restante no texto")


def test_decisao_nula_e_aceita(anonimizar: AnonimizadorTjdft) -> None:
    resultado = anonimizar(registro(1) | {"decisao": None})
    assert isinstance(resultado, dict) and resultado["decisao"] is None
