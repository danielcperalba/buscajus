"""Detecção de número de processo na consulta (F4-02). Números fictícios (ano 2099)."""

import pytest

from buscajus.api.consulta import MAXIMO_CONSULTA, analisar_consulta, normalizar_consulta
from fixtures.djen import numero_cnj

DIGITOS, MASCARA = numero_cnj(11412)  # 0011412-DD.2099.8.16.9999, DV válido


@pytest.mark.parametrize(
    "consulta",
    [
        MASCARA,
        DIGITOS,
        f"  {MASCARA}  ",
        f"processo nº {MASCARA}",
        f"Processo n. {DIGITOS}",
        f"autos {MASCARA}.",
        MASCARA.replace(".", ""),  # máscara incompleta: só o hífen
        MASCARA.replace("-", ""),
    ],
)
def test_consulta_so_com_numero_completo(consulta: str) -> None:
    analisada = analisar_consulta(consulta)
    assert analisada.tipo == "processo"
    assert analisada.texto == ""
    assert analisada.numero is not None
    assert (analisada.numero.digitos, analisada.numero.mascara) == (DIGITOS, MASCARA)
    assert analisada.numero.completo and analisada.numero.valido


def test_numero_com_outros_termos_vira_filtro() -> None:
    analisada = analisar_consulta(f"partilha de bens {MASCARA} herança")
    assert analisada.tipo == "hibrida"
    assert analisada.texto == "partilha de bens herança"
    assert analisada.numero is not None and analisada.numero.digitos == DIGITOS


def test_dv_invalido_e_detectado_mas_marcado() -> None:
    errado = DIGITOS[:7] + "00" + DIGITOS[9:]
    analisada = analisar_consulta(errado)
    assert analisada.numero is not None and analisada.numero.valido is False


@pytest.mark.parametrize(
    ("consulta", "prefixo"),
    [
        (MASCARA[:10], DIGITOS[:9]),  # NNNNNNN-DD
        (MASCARA[:15], DIGITOS[:13]),  # NNNNNNN-DD.AAAA
        (MASCARA[:17], DIGITOS[:14]),  # NNNNNNN-DD.AAAA.J
        (MASCARA[:20], DIGITOS[:16]),  # NNNNNNN-DD.AAAA.J.TR
    ],
)
def test_numero_parcial_vira_prefixo(consulta: str, prefixo: str) -> None:
    analisada = analisar_consulta(consulta)
    assert analisada.tipo == "processo"
    assert analisada.numero is not None
    assert (analisada.numero.digitos, analisada.numero.completo) == (prefixo, False)
    assert analisada.numero.mascara is None and analisada.numero.valido is None


def test_parcial_com_texto() -> None:
    analisada = analisar_consulta(f"dano moral {MASCARA[:15]}")
    assert (analisada.tipo, analisada.texto) == ("hibrida", "dano moral")
    assert analisada.numero is not None and not analisada.numero.completo


@pytest.mark.parametrize(
    "consulta",
    [
        "disputa por herança familiar",
        DIGITOS + "1",  # 21 dígitos
        "9" + DIGITOS,
        "CNPJ 11.144.477/0001-35",
        "CPF 529.982.247-25",
        "11144477735000",
        "Lei 9.656/1998, art. 10, § 13",
        "julgado em 01/02/2099",
        "Acórdão 1234567",
        "0011412",  # só o sequencial: ambíguo, não é prefixo
        "telefone (61) 99999-1234",
    ],
)
def test_nao_e_numero_de_processo(consulta: str) -> None:
    analisada = analisar_consulta(consulta)
    assert analisada.numero is None
    assert analisada.tipo == "hibrida"
    assert analisada.texto == normalizar_consulta(consulta)


def test_normalizacao_da_consulta() -> None:
    assert normalizar_consulta(" herança\t\n familiar\x00 ") == "herança familiar"
    assert normalizar_consulta("Herança") == "Herança"  # NFD → NFC
    assert len(normalizar_consulta("a" * 2000)) == MAXIMO_CONSULTA
    assert analisar_consulta("").texto == ""


def test_so_o_primeiro_numero_e_usado() -> None:
    outro_digitos, outro_mascara = numero_cnj(22)
    analisada = analisar_consulta(f"{MASCARA} {outro_mascara}")
    assert analisada.numero is not None and analisada.numero.digitos == DIGITOS
    assert analisada.texto == outro_mascara and outro_digitos
