"""Anonimização sem NER real: F1-34, F1-35, F1-39, interface da camada 2 e F1-38."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from buscajus.ingest.anonimizacao import Rejeicao
from buscajus.ingest.anonimizacao import camada2 as c2
from buscajus.ingest.anonimizacao.classificacao import classificar
from buscajus.ingest.anonimizacao.cpf import MASCARA, dv_valido, mascarar_cpf, tem_cpf
from buscajus.ingest.anonimizacao.nomes import Casador, iniciais, substituir
from buscajus.ingest.anonimizacao.pipeline import (
    AnonimizadorDjen,
    ErroAnonimizacao,
    criar_anonimizador,
    nomes_a_substituir,
)
from buscajus.ingest.djen.campos import LISTA_BRANCA
from buscajus.ingest.djen.parser import analisar
from buscajus.ingest.texto import chave
from fixtures.djen import dados, item_ementa

from .anonimizacao_ajuda import DetectorFalso

CASOS = json.loads(
    (Path(__file__).parents[1] / "fixtures/anonimizacao/casos_pf_pj.json").read_text(
        encoding="utf-8"
    )
)["casos"]


def normalizado(texto: str) -> str:
    return chave(texto).upper()


@pytest.fixture
def anonimizador() -> AnonimizadorDjen:
    return criar_anonimizador(DetectorFalso())


def _por_id(id_comunicacao: int) -> dict[str, Any]:
    return item_ementa(next(e for e in dados.EMENTAS if e.id == id_comunicacao))


# --- F1-34: classificação PF × PJ -------------------------------------------------------


@pytest.mark.parametrize("caso", CASOS, ids=[c["entrada"] for c in CASOS])
def test_casos_dificeis(caso: dict[str, str]) -> None:
    resultado = classificar(caso["entrada"])
    assert resultado.classe == caso["classe"]
    if caso["classe"] != "PJ":
        assert resultado.nome == caso["nome"]
        assert resultado.substituir


def test_destinatarios_da_fixture() -> None:
    """PJ e entes públicos da fixture ficam; os nomes que devem sumir são substituídos."""
    pj = {normalizado(p) for p in dados.PRESERVADOS} | {normalizado(dados.MP.nome)}
    marcadores_pj = ("S.A", "S/A", "LTDA", "EIRELI", "COOPERATIVA", "IMOBILIARIA")
    for ementa in dados.EMENTAS:
        for pessoa in ementa.destinatarios:
            nome = normalizado(pessoa.nome)
            esperado_pj = nome in pj or any(m in nome for m in marcadores_pj)
            assert (classificar(pessoa.nome).classe == "PJ") is esperado_pj, pessoa.nome


# --- F1-35: camada 1 --------------------------------------------------------------------


def test_iniciais_ignoram_particulas() -> None:
    assert iniciais("JOSÉ DA SILVA SANTOS") == "J.S.S."
    assert iniciais("Maria das Dores Zanfirelli") == "M.D.Z."
    assert iniciais("JOÃO PEDRO ESCARLATINO DE ANDRADE") == "J.P.E.A."


@pytest.mark.parametrize(
    "texto",
    [
        "o réu JOÃO PEDRO ESCARLATINO DE ANDRADE recorreu",
        "o réu JOAO PEDRO ESCARLATINO DE ANDRADE recorreu",
        "o réu João Pedro Escarlatino de Andrade recorreu",
        "o réu joão escarlatino recorreu",
        "o réu JOÃO ANDRADE recorreu",
        "o réu Pedro\xa0Escarlatino recorreu",
        "o réu JOÃO PEDRO ESCARLATINO ANDRADE recorreu",
    ],
)
def test_variacoes_do_nome(texto: str) -> None:
    resultado, n = substituir(texto, Casador(["JOAO PEDRO ESCARLATINO DE ANDRADE"]))
    assert resultado == "o réu J.P.E.A. recorreu"
    assert n == 1


def test_token_isolado_nao_e_substituido() -> None:
    texto = "o réu Escarlatino e a testemunha Andrade"
    assert substituir(texto, Casador(["JOAO PEDRO ESCARLATINO DE ANDRADE"])) == (texto, 0)


def test_nao_casa_pedaco_de_palavra() -> None:
    texto = "JOAOZINHO ANDRADES"
    assert substituir(texto, Casador(["JOAO ANDRADE"])) == (texto, 0)


def test_trecho_protegido_nao_e_substituido() -> None:
    texto = "aplicação da Lei Maria da Penha; a vítima Maria da Penha Souza"
    resultado, n = substituir(texto, Casador(["MARIA DA PENHA SOUZA"]), ["Lei Maria da Penha"])
    assert resultado == "aplicação da Lei Maria da Penha; a vítima M.P.S."
    assert n == 1


# --- F1-39: CPF --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("CPF 529.982.247-25.", f"CPF {MASCARA}."),
        (
            "CPF 123.456.789-00 (DV inválido, mas formatado)",
            f"CPF {MASCARA} (DV inválido, mas formatado)",
        ),
        ("CPF 11144477735", f"CPF {MASCARA}"),
        ("CPF 111444777-35", f"CPF {MASCARA}"),
        ("GUMERCINDO PALHARINI 52998224725 ME", f"GUMERCINDO PALHARINI {MASCARA} ME"),
        ("número 12345678900 sem DV válido", "número 12345678900 sem DV válido"),
        ("autos 52998224725209981699", "autos 52998224725209981699"),
        ("CNPJ 11144477735000", "CNPJ 11144477735000"),
        ("processo 0001001-10.2099.8.16.9999", "processo 0001001-10.2099.8.16.9999"),
        ("CNPJ 11.444.777/0001-61", "CNPJ 11.444.777/0001-61"),
        ("telefone (41) 99999-0000", "telefone (41) 99999-0000"),
        ("valor R$ 529.982.247,25", "valor R$ 529.982.247,25"),
        ("11111111111", "11111111111"),
    ],
)
def test_mascaramento(texto: str, esperado: str) -> None:
    assert mascarar_cpf(texto)[0] == esperado
    assert not tem_cpf(esperado)


def test_dv() -> None:
    assert dv_valido("529.982.247-25")
    assert not dv_valido("529.982.247-24")
    assert not dv_valido("000.000.000-00")


# --- Camada 2 (interface e exceções) -----------------------------------------------------


def test_camada2_substitui_e_respeita_excecoes() -> None:
    texto = (
        "A vítima Clotilde Ravanello reconheceu o réu (HC 712.345/SP, Rel. Min. Bonifácio "
        "Cardeal). Lei Maria da Penha. Voto do Des. Teobaldo Siqueira Lins."
    )
    resultado, n = c2.aplicar(texto, DetectorFalso())
    assert "Clotilde" not in resultado and "C.R." in resultado
    assert "Rel. Min. Bonifácio Cardeal" in resultado
    assert "Lei Maria da Penha" in resultado
    assert "Des. Teobaldo Siqueira Lins" in resultado
    assert n == 1


def test_camada2_protege_o_relator_mesmo_sem_titulo() -> None:
    texto = "Conforme Teobaldo Siqueira Lins, relator."
    assert c2.aplicar(texto, DetectorFalso(), ["teobaldo siqueira lins"]) == (texto, 0)


# --- F1-38: pipeline, invariante, falha segura e lista branca -----------------------------


def test_sem_ner_o_pipeline_nao_existe() -> None:
    with pytest.raises(ErroAnonimizacao, match="NER"):
        criar_anonimizador(None)


@pytest.mark.parametrize("ementa", dados.EMENTAS, ids=lambda e: str(e.id))
def test_caminho_feliz_em_toda_a_fixture(
    anonimizador: AnonimizadorDjen, ementa: dados.Ementa
) -> None:
    item = item_ementa(ementa)
    resultado = anonimizador(item)
    assert not isinstance(resultado, Rejeicao), ementa.id
    assert set(resultado) <= LISTA_BRANCA
    assert "destinatarios" not in resultado and "destinatarioadvogados" not in resultado
    assert resultado["anonimizacao_versao"] == "c1-1+cpf-1+doc-1+ner-falso-1"

    texto = normalizado(analisar(resultado["texto"]).ementa)
    for nome in dados.NOMES_CAMADA_1 + dados.NOMES_CAMADA_2:
        assert nome not in texto, (ementa.id, nome)
    for cpf in dados.CPFS:
        assert not re.search(rf"(?<![\d.]){re.escape(cpf)}(?![\d-])", texto), cpf
    # O cabeçalho continua legível pelo parser, com o relator intacto.
    analisado = analisar(resultado["texto"])
    assert analisado.relator == ementa.relator
    original = analisar(item["texto"])
    assert analisado.data_julgamento == original.data_julgamento
    assert analisado.processo == original.processo


def test_preservados_e_nao_cpfs_ficam(anonimizador: AnonimizadorDjen) -> None:
    textos = []
    for ementa in dados.EMENTAS:
        resultado = anonimizador(item_ementa(ementa))
        assert not isinstance(resultado, Rejeicao)
        textos.append(analisar(resultado["texto"]).ementa)
    corrido = normalizado(" | ".join(textos))
    for preservado in dados.PRESERVADOS:
        assert normalizado(preservado) in corrido, preservado
    for numero in dados.NAO_CPFS:
        assert numero in corrido, numero


def test_conta_substituicoes(anonimizador: AnonimizadorDjen) -> None:
    resultado = anonimizador(_por_id(900007))  # nome do MEI + CPF formatado
    assert not isinstance(resultado, Rejeicao)
    assert resultado["anonimizacao_substituicoes"] == 2
    sem_nomes = anonimizador(_por_id(900011) | {"destinatarios": []})
    assert not isinstance(sem_nomes, Rejeicao)


def test_nomes_a_substituir_inclui_advogados_e_ignora_pj() -> None:
    nomes = nomes_a_substituir(_por_id(900001))
    assert "ANACLETO BORGONOVI QUINTELA" in nomes
    assert "LEOCADIO BARRANCOS VIEIRA" in nomes
    assert not any("MINISTERIO" in n for n in nomes)


def test_falha_segura_quando_o_nome_fica_partido_no_html(anonimizador: AnonimizadorDjen) -> None:
    item = _por_id(900001)
    item["texto"] = item["texto"].replace(
        "ANACLETO BORGONOVI QUINTELA", "<b>ANACLETO</b> <i>QUINTELA</i>"
    )
    resultado = anonimizador(item)
    assert resultado == Rejeicao(
        "900001", "nome de destinatário, CPF ou documento restante no texto"
    )


def test_falha_segura_com_nome_em_linha_protegida(anonimizador: AnonimizadorDjen) -> None:
    item = _por_id(900001)
    item["texto"] = item["texto"].replace("3&ordf; C&acirc;mara Criminal", "Anacleto Quintela")
    resultado = anonimizador(item)
    assert isinstance(resultado, Rejeicao)
    # A rejeição nunca traz conteúdo.
    assert "ANACLETO" not in resultado.motivo.upper()


def test_falha_segura_com_cpf_partido(anonimizador: AnonimizadorDjen) -> None:
    item = _por_id(900016)
    item["texto"] = item["texto"].replace("11144477735", "111.444.777-35")
    assert not isinstance(anonimizador(item), Rejeicao)


def test_html_continua_valido_e_sem_entidades_duplas(anonimizador: AnonimizadorDjen) -> None:
    resultado = anonimizador(_por_id(900009))
    assert not isinstance(resultado, Rejeicao)
    assert "&amp;" not in resultado["texto"]
    assert "MASSA FALIDA DE CONSTRUTORA HORIZONTE IMAGINÁRIO LTDA" in resultado["texto"]
    assert "I.G.T." in resultado["texto"]


def test_texto_nulo_segue_sem_destinatarios(anonimizador: AnonimizadorDjen) -> None:
    """Sem texto não há o que anonimizar: o item segue e vira falha de parser adiante."""
    for texto in (None, "", "   "):
        item = {"id": 1, "texto": texto, "destinatarios": [{"nome": "ANACLETO QUINTELA"}]}
        resultado = anonimizador(item)
        assert not isinstance(resultado, Rejeicao)
        assert resultado["texto"] is None
        assert "destinatarios" not in resultado


def test_texto_em_formato_inesperado_e_rejeitado(anonimizador: AnonimizadorDjen) -> None:
    assert isinstance(anonimizador({"id": 1, "texto": 123}), Rejeicao)
