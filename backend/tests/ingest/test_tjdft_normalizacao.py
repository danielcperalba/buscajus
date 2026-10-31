"""Mapeamento TJDFT → AcordaoNormalizado (F2-08) e conversão de fuso (F2-05)."""

from datetime import date
from typing import Any

import pytest

from buscajus.db.classes_cnj import ler_tpu
from buscajus.ingest.modelos import ItemInvalido
from buscajus.ingest.processo import NumeroProcessoInvalido
from buscajus.ingest.tjdft.campos import aplicar_lista_branca
from buscajus.ingest.tjdft.normalizacao import NormalizadorTjdft, data_sao_paulo
from fixtures.djen import numero_cnj
from fixtures.tjdft import dados

from .tjdft_ajuda import DIA, DIA_VIRADA, fixture, uuid

CLASSES = {c["codigo"]: c["nome"] for c in ler_tpu().classes}


def item(n: int, dia: date = DIA, **alteracoes: Any) -> dict[str, Any]:
    paginas = (0, 1) if dia == DIA else (0,)
    registros = [r for p in paginas for r in fixture(dia, p)["registros"]]
    registro = next(r for r in registros if r["uuid"] == uuid(n))
    return aplicar_lista_branca(registro) | {"anonimizacao_versao": "falso"} | alteracoes


@pytest.fixture
def normalizar() -> NormalizadorTjdft:
    return NormalizadorTjdft(CLASSES)


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("2026-10-14T03:00:00.000Z", date(2026, 10, 14)),  # meia-noite em São Paulo
        ("2026-10-14T02:59:59.999Z", date(2026, 10, 13)),
        ("2026-10-14T01:30:00.000Z", date(2026, 10, 13)),
        ("2026-10-14T20:34:07.000Z", date(2026, 10, 14)),
        ("2026-10-14T02:00:00", date(2026, 10, 13)),  # sem fuso: UTC
        ("2026-10-14T02:00:00-03:00", date(2026, 10, 14)),
        ("", None),
        ("14/10/2026", None),
        (None, None),
    ],
)
def test_data_convertida_para_sao_paulo(valor: Any, esperado: date | None) -> None:
    assert data_sao_paulo(valor) == esperado


def test_registro_completo(normalizar: NormalizadorTjdft) -> None:
    digitos, mascara = numero_cnj(1, justica=8, tribunal=7)
    acordao = normalizar(item(1))
    assert acordao.fonte == "tjdft"
    assert acordao.id_fonte == uuid(1)
    assert acordao.identificador_fonte == "9900001"
    assert acordao.tipo_documento_fonte == "acordaos"
    assert acordao.tribunal == "TJDFT"
    assert (acordao.numero_processo, acordao.numero_processo_mascara) == (digitos, mascara)
    assert acordao.numero_processo_valido
    assert acordao.orgao_julgador == "3ª Turma Cível"
    assert acordao.classe_codigo_cnj == 198
    assert acordao.classe_nome == acordao.classe_citacao == "Apelação Cível"
    assert acordao.relator == "Aristóbulo Ventanilha Quaresmeiro"
    assert acordao.relator_chave == "aristobulo ventanilha quaresmeiro"
    assert acordao.relator_designado is None
    assert acordao.data_julgamento == date(2026, 10, 8)
    assert acordao.data_publicacao == date(2026, 10, 14)
    assert acordao.data_disponibilizacao is None
    assert acordao.local_publicacao == "PJe"
    assert acordao.ementa.startswith("DIREITO DO CONSUMIDOR. APELAÇÃO CÍVEL.")
    assert "\nII. QUESTÃO EM DISCUSSÃO\n" in acordao.ementa
    assert acordao.decisao == "CONHECIDO. DESPROVIDO. UNÂNIME."
    assert acordao.turma_recursal is False
    assert acordao.possui_inteiro_teor is True
    assert acordao.link_oficial == f"https://jurisdf.tjdft.jus.br/acordaos/{uuid(1)}"
    assert acordao.link_tribunal is None
    assert acordao.anonimizacao_versao == "falso"


def test_datas_perto_da_meia_noite_utc(normalizar: NormalizadorTjdft) -> None:
    acordao = normalizar(item(4))
    assert acordao.data_publicacao == date(2026, 10, 13)
    assert acordao.data_julgamento == date(2026, 10, 7)
    # Consultado em 15/10 (data UTC), publicado em 14/10 em São Paulo.
    assert normalizar(item(46, DIA_VIRADA)).data_publicacao == date(2026, 10, 14)


def test_relator_designado_e_guardado_junto_com_o_original(
    normalizar: NormalizadorTjdft,
) -> None:
    acordao = normalizar(item(5))
    assert acordao.relator == "Hermenegildo Soutelo Vilarongo"
    assert acordao.relator_designado == "Leopoldina Arrudão Cambraieta"
    assert acordao.relator_designado_chave == "leopoldina arrudao cambraieta"
    assert acordao.classe_citacao == "Apelação Criminal"
    assert acordao.local_publicacao == "DJE"


def test_turma_recursal_pela_subbase_ou_pelo_booleano(normalizar: NormalizadorTjdft) -> None:
    assert normalizar(item(2)).turma_recursal is True
    assert normalizar(item(2, turmaRecursal=False)).turma_recursal is True
    assert normalizar(item(2, subbase="acordaos")).turma_recursal is True
    assert normalizar(item(2, subbase="acordaos", turmaRecursal=False)).turma_recursal is False
    assert normalizar(item(2)).classe_nome == "Recurso Inominado Cível"


def test_classe_fora_da_tpu_fica_sem_nome(normalizar: NormalizadorTjdft) -> None:
    acordao = normalizar(item(1, codigoClasseCnj=999999))
    assert acordao.classe_codigo_cnj == 999999
    assert acordao.classe_nome is None and acordao.classe_citacao is None


@pytest.mark.parametrize(
    "alteracoes",
    [{"uuid": None}, {"uuid": "../../x"}, {"ementa": "   "}, {"ementa": None}],
    ids=["sem uuid", "uuid estranho", "ementa vazia", "ementa nula"],
)
def test_item_invalido(normalizar: NormalizadorTjdft, alteracoes: dict[str, Any]) -> None:
    with pytest.raises(ItemInvalido):
        normalizar(item(1, **alteracoes))


def test_processo_invalido(normalizar: NormalizadorTjdft) -> None:
    with pytest.raises(NumeroProcessoInvalido):
        normalizar(item(1, processo="123"))


def test_hash_muda_com_designado_e_local(normalizar: NormalizadorTjdft) -> None:
    base = normalizar(item(1))
    assert normalizar(item(1, localDePublicacao="DJE")).hash_conteudo != base.hash_conteudo
    assert (
        normalizar(item(1, nomeRelatorDesignado=dados.DESIGNADO)).hash_conteudo
        != base.hash_conteudo
    )
