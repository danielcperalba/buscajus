"""Limpeza e normalização: HTML (F1-18), processo (F1-21) e relator (F1-22)."""

import pytest

from buscajus.ingest.processo import NumeroProcessoInvalido, normalizar_numero
from buscajus.ingest.relator import normalizar_relator
from buscajus.ingest.texto import chave, decodificar, normalizar_espacos

# --- F1-18 ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("SUCESS&Atilde;O", "SUCESSÃO"),
        ("a&ccedil;&atilde;o", "ação"),
        ("Processo:&nbsp;123", "Processo:\xa0123"),
        ("GUSM&amp;Atilde;O", "GUSMÃO"),
        ("a&#231;&#227;o", "ação"),
        ("a&#xE7;&#xE3;o", "ação"),
        ("&amp;#231;", "ç"),
        ("Fulano &amp; Cia", "Fulano & Cia"),
        ("R$ 10 & 20", "R$ 10 & 20"),
    ],
)
def test_decodifica_entidades(entrada: str, esperado: str) -> None:
    assert decodificar(entrada) == esperado


def test_segunda_passada_so_quando_sobram_entidades() -> None:
    # "&amp;lt;" decodificado uma vez vira "&lt;", que é entidade; a segunda passada vale.
    assert decodificar("&amp;lt;b&amp;gt;") == "<b>"
    # Texto que, depois de uma passada, não tem entidade não é tocado de novo.
    assert decodificar("&amp; nada") == "& nada"


def test_nfc_e_controles() -> None:
    decomposto = "Aco" + chr(0x301) + "rda" + chr(0x303) + "o"  # acentos combinantes
    assert decodificar(decomposto) == "Acórdão"
    assert decodificar("linha\x00um\x07\r\nlinha\tdois\x7f") == "linhaum\nlinha\tdois"


def test_normaliza_espacos_e_linhas() -> None:
    texto = "  A\xa0\xa0 B  \n\n\n\n C  \nindeni-\nzação\nAUXÍLIO-\nACIDENTE"
    assert normalizar_espacos(texto) == "A B\n\nC\nindenização\nAUXÍLIO-\nACIDENTE"


def test_chave_sem_acento_e_caixa() -> None:
    assert chave("  JOÃO   da Silva ") == "joao da silva"


# --- F1-21 ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "entrada",
    ["0001001-10.2099.8.16.9999", "00010011020998169999", " 0001001-10 2099.8.16 9999 "],
)
def test_numero_valido_com_e_sem_mascara(entrada: str) -> None:
    numero = normalizar_numero(entrada)
    assert numero.digitos == "00010011020998169999"
    assert numero.mascara == "0001001-10.2099.8.16.9999"
    assert numero.valido


def test_numero_com_dv_invalido_e_aceito_mas_marcado() -> None:
    numero = normalizar_numero("0001001-11.2099.8.16.9999")
    assert numero.mascara == "0001001-11.2099.8.16.9999"
    assert not numero.valido


def test_numero_real_conhecido_do_formato() -> None:
    # Exemplo da seção 9 do ARCHITECTURE.md: DV 20 confere.
    assert normalizar_numero("0011412-20.2025.8.16.0069").valido


@pytest.mark.parametrize("entrada", ["", "123", "0001001-10.2099.8.16.99990"])
def test_numero_sem_20_digitos(entrada: str) -> None:
    with pytest.raises(NumeroProcessoInvalido, match="esperado 20"):
        normalizar_numero(entrada)


# --- F1-22 ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "exibicao", "chave_esperada"),
    [
        (
            "Desembargador Aristeu Prudente Valença",
            "Des. Aristeu Prudente Valença",
            "aristeu prudente valenca",
        ),
        (
            "Desembargadora Celestina Moura Brandão",
            "Desa. Celestina Moura Brandão",
            "celestina moura brandao",
        ),
        (
            "DESEMBARGADORA CELESTINA MOURA BRANDÃO",
            "Desa. Celestina Moura Brandão",
            "celestina moura brandao",
        ),
        ("Des. Teobaldo Siqueira Lins", "Des. Teobaldo Siqueira Lins", "teobaldo siqueira lins"),
        ("Desembargador(a) Fulano de Tal", "Des. Fulano de Tal", "fulano de tal"),
        (
            "Juiz Evandro Pimentel Assunção",
            "Juiz Evandro Pimentel Assunção",
            "evandro pimentel assuncao",
        ),
        (
            "JUÍZA LEONOR BITTENCOURT FARIA",
            "Juíza Leonor Bittencourt Faria",
            "leonor bittencourt faria",
        ),
        (
            "Juíza de Direito Substituta em Segundo Grau Leonor Bittencourt Faria",
            "Juíza de Direito Substituta em Segundo Grau Leonor Bittencourt Faria",
            "leonor bittencourt faria",
        ),
        ("  JOSÉ  DOS  SANTOS   E SILVA  ", "José dos Santos e Silva", "jose dos santos e silva"),
        ("MARIA-JOSÉ DA COSTA", "Maria-José da Costa", "maria-jose da costa"),
        ("Dr. Fulano de Tal", "Fulano de Tal", "fulano de tal"),
        ("Fulano de TAL", "Fulano de TAL", "fulano de tal"),
    ],
)
def test_normaliza_relator(entrada: str, exibicao: str, chave_esperada: str) -> None:
    relator = normalizar_relator(entrada)
    assert relator is not None
    assert (relator.exibicao, relator.chave) == (exibicao, chave_esperada)


def test_mesma_pessoa_mesma_chave() -> None:
    a = normalizar_relator("Desembargadora CELESTINA MOURA BRANDÃO")
    b = normalizar_relator("Desa. Celestina Moura Brandao")
    assert a is not None and b is not None
    assert a.chave == b.chave


@pytest.mark.parametrize("entrada", [None, "", "   ", " , "])
def test_relator_vazio(entrada: str | None) -> None:
    assert normalizar_relator(entrada) is None
