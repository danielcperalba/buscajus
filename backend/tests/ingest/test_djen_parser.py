"""Parser do texto do DJEN: cabeçalho (F1-19) e isolamento da ementa (F1-20)."""

from datetime import date

import pytest

from buscajus.ingest.djen.parser import FalhaParser, analisar, processo_confere
from fixtures.djen import dados, item_ementa, numero_cnj

CORPO = "EMENTA: DIREITO CIVIL. APELAÇÃO CÍVEL. PARTILHA DE BENS. Recurso desprovido."


def _ementa(id_comunicacao: int) -> dados.Ementa:
    return next(e for e in dados.EMENTAS if e.id == id_comunicacao)


def _tabela(*linhas: str, ementa: str = CORPO) -> str:
    return (
        "<table><tbody>"
        + "".join(linhas)
        + f'<tr><td colspan="2"><strong>Ementa:</strong><br>{ementa}</td></tr></tbody></table>'
    )


def _linha(rotulo: str, valor: str) -> str:
    return f"<tr><td><strong>{rotulo}:</strong>&nbsp;</td><td>{valor}</td></tr>"


# --- F1-19: cabeçalho -----------------------------------------------------------------


@pytest.mark.parametrize("ementa", dados.EMENTAS, ids=lambda e: str(e.id))
def test_fixtures(ementa: dados.Ementa) -> None:
    item = item_ementa(ementa)
    resultado = analisar(item["texto"])
    _, mascara = numero_cnj(ementa.sequencial)
    assert resultado.processo == mascara
    assert processo_confere(resultado.processo, item["numero_processo"])
    assert resultado.classe == ementa.classe
    assert resultado.relator == ementa.relator
    esperado = (
        date(*reversed([int(p) for p in ementa.data_julgamento.split("/")]))
        if ementa.data_julgamento
        else None
    )
    assert resultado.data_julgamento == esperado
    assert not resultado.data_julgamento_invalida
    assert resultado.ementa.startswith("EMENTA:")
    assert resultado.fallback is (ementa.formato == "sem_tabela")
    # O cabeçalho não vaza para a ementa.
    assert "Órgão Julgador" not in resultado.ementa
    assert "Relator" not in resultado.ementa.split("\n")[0]


def test_cobertura_da_data_no_caderno_de_referencia() -> None:
    com_rotulo = [e for e in dados.EMENTAS if e.data_julgamento]
    extraidas = [e for e in com_rotulo if analisar(item_ementa(e)["texto"]).data_julgamento]
    assert len(extraidas) / len(com_rotulo) >= 0.99


@pytest.mark.parametrize(
    ("rotulo_relator", "rotulo_data"),
    [
        ("Relator(a)", "Data do Julgamento"),
        ("Relatora", "Data de Julgamento"),
        ("Relator", "DATA DO JULGAMENTO"),
        ("RELATOR(A)", "Data do julgamento"),
    ],
)
def test_variacoes_de_rotulo(rotulo_relator: str, rotulo_data: str) -> None:
    texto = _tabela(
        _linha("Processo", "0001001-10.2099.8.16.9999(Apelação Cível)"),
        _linha(rotulo_relator, "Des. Fulano Fictício"),
        _linha(rotulo_data, "06/10/2026"),
    )
    resultado = analisar(texto)
    assert resultado.relator == "Des. Fulano Fictício"
    assert resultado.data_julgamento == date(2026, 10, 6)


def test_rotulos_fora_da_lista_branca_sao_descartados() -> None:
    texto = _tabela(
        _linha("Processo", "0001001-10.2099.8.16.9999(Apelação Cível)"),
        _linha("Apelante", "NOME FICTÍCIO DE PARTE"),
        _linha("Advogado", "OUTRO NOME FICTÍCIO"),
        _linha("Relator(a)", "Des. Fulano Fictício"),
    )
    resultado = analisar(texto)
    assert "NOME FICTÍCIO DE PARTE" not in resultado.ementa
    assert "OUTRO NOME" not in resultado.ementa
    assert resultado.relator == "Des. Fulano Fictício"


def test_rotulo_e_valor_na_mesma_celula() -> None:
    texto = _tabela(
        "<tr><td>Relator(a): Des. Fulano Fictício</td></tr>",
        "<tr><td>Data do Julgamento: 06/10/2026</td></tr>",
    )
    resultado = analisar(texto)
    assert resultado.relator == "Des. Fulano Fictício"
    assert resultado.data_julgamento == date(2026, 10, 6)


@pytest.mark.parametrize("valor", ["31/02/2026", "06-10-2026", "seis de outubro", "6/10/26"])
def test_data_invalida_fica_nula_e_marcada(valor: str) -> None:
    resultado = analisar(_tabela(_linha("Data do Julgamento", valor)))
    assert resultado.data_julgamento is None
    assert resultado.data_julgamento_invalida


def test_processo_separado_da_classe_e_conferido() -> None:
    texto = _tabela(_linha("Processo", "0042094-26.2099.8.16.9999 (Recurso Inominado (Cível))"))
    resultado = analisar(texto)
    assert resultado.processo == "0042094-26.2099.8.16.9999"
    assert resultado.classe == "Recurso Inominado (Cível)"
    assert processo_confere(resultado.processo, "00420942620998169999")
    assert not processo_confere(resultado.processo, "00000000000000000000")


def test_processo_sem_classe() -> None:
    resultado = analisar(_tabela(_linha("Processo", "0042094-26.2099.8.16.9999")))
    assert (resultado.processo, resultado.classe) == ("0042094-26.2099.8.16.9999", None)


# --- F1-20: isolamento da ementa ------------------------------------------------------


def test_ementa_com_paragrafos_e_espacos() -> None:
    corpo = (
        "EMENTA:&nbsp;&nbsp;DIREITO   CIVIL.<br><br><br><p>1. Primeiro.</p><div>2. Segundo.</div>"
    )
    resultado = analisar(_tabela(ementa=corpo))
    assert resultado.ementa == "EMENTA: DIREITO CIVIL.\n\n1. Primeiro.\n\n2. Segundo."


def test_texto_depois_da_tabela_entra_na_ementa() -> None:
    texto = (
        "<table><tr><td>Processo:</td><td>0001001-10.2099.8.16.9999(Apelação)</td></tr>"
        "</table>" + f"<p>{CORPO}</p>"
    )
    resultado = analisar(texto)
    assert resultado.ementa == CORPO
    assert resultado.origem == "tabela"


def test_sem_tabela_com_rotulos_no_texto() -> None:
    texto = (
        "<p>Processo: 0001001-10.2099.8.16.9999(Apelação Cível)</p>"
        "<p>Relator(a): Des. Fulano Fictício</p><p>Órgão Julgador: 1ª Câmara</p>"
        "<p>Data do Julgamento: 06/10/2026</p>"
        f"<p>Ementa: {CORPO}</p>"
    )
    resultado = analisar(texto)
    assert resultado.origem == "rotulos_no_texto"
    assert resultado.fallback
    assert resultado.relator == "Des. Fulano Fictício"
    assert resultado.data_julgamento == date(2026, 10, 6)
    assert resultado.ementa == CORPO


def test_sem_tabela_nem_rotulos_usa_o_texto_inteiro() -> None:
    resultado = analisar(f"<p>{CORPO}</p><p>Segundo parágrafo da ementa.</p>")
    assert resultado.origem == "texto_inteiro"
    assert resultado.relator is None and resultado.data_julgamento is None
    assert resultado.ementa == f"{CORPO}\n\nSegundo parágrafo da ementa."


@pytest.mark.parametrize(
    "texto", ["", "   ", _tabela(ementa="curta"), "<p>Ementa:</p>", "<table></table>"]
)
def test_ementa_vazia_ou_curta_e_falha_de_parser(texto: str) -> None:
    with pytest.raises(FalhaParser) as erro:
        analisar(texto)
    assert "curta" not in str(erro.value)


def test_html_malformado_e_tolerado() -> None:
    texto = f"<table><tr><td>Relator(a):<td>Des. Fulano<tr><td colspan=2>Ementa:<br>{CORPO}"
    resultado = analisar(texto)
    assert resultado.relator == "Des. Fulano"
    assert resultado.ementa == CORPO


def test_entidade_escapada_duas_vezes_na_ementa() -> None:
    resultado = analisar(item_ementa(_ementa(900009))["texto"])
    assert "IRACEMA GUSMÃO TREVISANUTO" in resultado.ementa
    assert "&" not in resultado.ementa
