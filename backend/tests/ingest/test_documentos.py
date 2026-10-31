"""F1-41: mascaramento de documentos de identificação, ancorado por palavra-chave.

Todos os números são de exemplo; processos usam o ano 2099.
"""

import pytest

from buscajus.ingest.anonimizacao.documentos import MASCARA, mascarar_documentos, tem_documento
from buscajus.ingest.anonimizacao.pipeline import AnonimizadorDjen
from buscajus.ingest.pii import verificar_pii
from buscajus.ingest.tjdft.anonimizacao import criar_anonimizador as criar_anonimizador_tjdft
from fixtures.djen import dados, item_ementa

from .anonimizacao_ajuda import DetectorFalso

POSITIVOS = [
    # RG / identidade
    ("portador do RG nº 12.345.678-9", "portador do RG nº ***"),
    ("RG 1234567", "RG ***"),
    ("R.G. 9.876.543-X, expedido pela SSP", "R.G. ***, expedido pela SSP"),
    ("RG/SSP-PR 1.234.567", "RG/SSP-PR ***"),
    ("RG: 12.345.678-9 SSP/PR", "RG: *** SSP/PR"),
    ("inscrito no RG sob o nº 7.654.321", "inscrito no RG sob o nº ***"),
    ("carteira de identidade nº MG-12.345.678", "carteira de identidade nº ***"),
    ("cédula de identidade n. 4.321.987", "cédula de identidade n. ***"),
    ("IDENTIDADE N. 4.321.987", "IDENTIDADE N. ***"),
    ("C.I. 3.456.789", "C.I. ***"),
    # CNH
    ("CNH nº 01234567890, categoria B", "CNH nº ***, categoria B"),
    ("Carteira Nacional de Habilitação 01234567890", "Carteira Nacional de Habilitação ***"),
    ("carteira de habilitação número 98765432100", "carteira de habilitação número ***"),
    # Título de eleitor
    ("título de eleitor nº 1234 5678 9012", "título de eleitor nº ***"),
    ("Título Eleitoral: 123456789012", "Título Eleitoral: ***"),
    ("inscrição eleitoral 0123 4567 8901", "inscrição eleitoral ***"),
    ("TÍTULO DE ELEITOR 123456789012", "TÍTULO DE ELEITOR ***"),
    # PIS/PASEP/NIS/NIT
    ("PIS/PASEP 123.45678.90-1", "PIS/PASEP ***"),
    ("PIS nº 12345678901", "PIS nº ***"),
    ("NIS 12345678901", "NIS ***"),
    ("NIT: 123.45678.90-1", "NIT: ***"),
    ("PASEP 1.234.567.890-1", "PASEP ***"),
    # CTPS (número e série)
    ("CTPS nº 1234567, série 0012-PR", "CTPS nº ***, série ***"),
    ("carteira de trabalho nº 7654321 série 00123", "carteira de trabalho nº *** série ***"),
    ("CARTEIRA DE TRABALHO Nº 7654321 SÉRIE 00123", "CARTEIRA DE TRABALHO Nº *** SÉRIE ***"),
    # Passaporte
    ("passaporte nº FT123456", "passaporte nº ***"),
    ("Passaporte AB1234567 emitido em 2099", "Passaporte *** emitido em 2099"),
]

NEGATIVOS = [
    # Números de processo, leis, artigos, súmulas, valores, datas, CNPJ
    "Apelação nº 0001234-56.2099.8.16.0001",
    "processo 00012345620998160001",
    "Lei nº 10.637/2002 (PIS e COFINS)",
    "contribuição ao PIS, Lei 10.637/2002, art. 3º",
    "PIS e COFINS sobre receitas de 2099",
    "alíquota do PIS de 1,65%",
    "Lei nº 9.099/95, art. 55",
    "art. 5º, inciso X, da Constituição",
    "Súmula 301 do STJ; Tema 905",
    "R$ 12.345,67",
    "em 12/03/2099",
    "CNPJ 12.345.678/0001-90",
    # Palavras-chave sem número de documento logo depois
    "identidade de gênero",
    "identidade física do juiz",
    "título executivo nº 12345",
    "título executivo extrajudicial 0001234-56.2099.8.16.0001",
    "habilitação de crédito nº 0001234-56.2099.8.16.0001",
    "CNH categoria B suspensa por 12 meses",
    "a CTPS do autor não foi anotada",
    "passaporte vencido",
    # Siglas dentro de palavras
    "AgRg no HC 999.001/PR",
    "AGRG NO RESP 1.234.567/SP",
    "NISSAN 12345",
    # Defesas: processo CNJ, CNPJ e números curtos depois da palavra-chave
    "CNH 0001234-56.2099.8.16.0001",
    "identidade 12.345.678/0001-90",
    "RG 123",
]


@pytest.mark.parametrize(("texto", "esperado"), POSITIVOS)
def test_documentos_mascarados(texto: str, esperado: str) -> None:
    mascarado, contagem = mascarar_documentos(texto)
    assert mascarado == esperado
    assert contagem == esperado.count(MASCARA)
    assert tem_documento(texto)
    assert not tem_documento(mascarado)


@pytest.mark.parametrize("texto", NEGATIVOS)
def test_outros_numeros_nao_sao_mascarados(texto: str) -> None:
    assert mascarar_documentos(texto) == (texto, 0)
    assert not tem_documento(texto)


def test_varios_documentos_no_mesmo_texto() -> None:
    texto = (
        "A vítima, portadora do RG nº 12.345.678-9 e da CTPS nº 1234567, série 0012-PR, "
        "foi ouvida no processo 0001234-56.2099.8.16.0001, nos termos do art. 201 do CPP."
    )
    mascarado, contagem = mascarar_documentos(texto)
    assert contagem == 3
    assert "0001234-56.2099.8.16.0001" in mascarado and "art. 201" in mascarado
    assert "12.345.678-9" not in mascarado and "1234567," not in mascarado


def test_documento_residual_vai_para_a_quarentena() -> None:
    assert "documento" in verificar_pii("Identificado pelo RG 12.345.678-9.")
    assert "documento" not in verificar_pii("Lei nº 10.637/2002 (PIS e COFINS).")


# --- Aplicação no DJEN e no TJDFT, antes de qualquer gravação -----------------------------


def test_djen_mascara_documentos_e_conta_por_camada() -> None:
    anonimizar = AnonimizadorDjen(DetectorFalso())
    item = item_ementa(dados.EMENTAS[0])
    item["texto"] += "<p>A vítima apresentou o RG nº 12.345.678-9 e a CNH 55544433321.</p>"
    resultado = anonimizar(item)
    assert isinstance(resultado, dict)
    assert "12.345.678-9" not in resultado["texto"] and "55544433321" not in resultado["texto"]
    assert "RG nº ***" in resultado["texto"] and "CNH ***" in resultado["texto"]
    assert anonimizar.substituicoes["documentos"] == 2
    assert anonimizar.substituicoes["camada1"] + anonimizar.substituicoes["camada2"] > 0
    assert resultado["anonimizacao_versao"].startswith("c1-1+cpf-1+doc-1+")


def test_tjdft_mascara_documentos_na_ementa_e_na_decisao() -> None:
    anonimizar = criar_anonimizador_tjdft(DetectorFalso(()))
    registro = {
        "uuid": "u-doc",
        "ementa": "Testemunha identificada pelo título de eleitor nº 1234 5678 9012.",
        "decisao": "Oficie-se, com a CTPS nº 1234567, série 0012-PR.",
        "nomeRelator": "FULANO DE TAL",
    }
    resultado = anonimizar(registro)
    assert isinstance(resultado, dict)
    assert resultado["ementa"].endswith("título de eleitor nº ***.")
    assert resultado["decisao"] == "Oficie-se, com a CTPS nº ***, série ***."
    assert anonimizar.substituicoes["documentos"] == 3
    assert resultado["anonimizacao_substituicoes"] == 3
