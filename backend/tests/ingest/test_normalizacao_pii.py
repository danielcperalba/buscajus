"""Mapeamento DJEN → AcordaoNormalizado (F1-23) e PII residual (F1-24)."""

import dataclasses
from datetime import date, datetime
from typing import Any

import pytest

from buscajus.ingest.anonimizacao import Rejeicao
from buscajus.ingest.anonimizacao.pipeline import criar_anonimizador
from buscajus.ingest.djen.normalizacao import ItemInvalido, normalizar
from buscajus.ingest.djen.parser import FalhaParser
from buscajus.ingest.pii import verificar_pii
from fixtures.djen import dados, hash_comunicacao, item_ementa, numero_cnj

from .anonimizacao_ajuda import DetectorFalso


def _anonimizado(id_comunicacao: int, **alteracoes: Any) -> dict[str, Any]:
    ementa = next(e for e in dados.EMENTAS if e.id == id_comunicacao)
    item = criar_anonimizador(DetectorFalso())(item_ementa(ementa) | alteracoes)
    assert not isinstance(item, Rejeicao)
    return item


# --- F1-23 -----------------------------------------------------------------------------


def test_item_de_ponta_a_ponta() -> None:
    acordao = normalizar(_anonimizado(900001))
    digitos, mascara = numero_cnj(1001)
    assert acordao.fonte == "djen"
    assert acordao.id_fonte == "900001"
    assert acordao.hash_fonte == hash_comunicacao(900001)
    assert acordao.tipo_documento_fonte == "Ementa de Acórdão"
    assert acordao.tribunal == "TJPR"
    assert (acordao.numero_processo, acordao.numero_processo_mascara) == (digitos, mascara)
    assert acordao.numero_processo_valido
    assert acordao.orgao_julgador == "3ª Câmara Criminal"
    # idOrgao não existe nos cadernos (F1-01).
    assert acordao.id_orgao_fonte is None
    # Filtros: nomeClasse/codigoClasse; citação: a classe do cabeçalho (difere em 44%).
    assert (acordao.classe_nome, acordao.classe_codigo_cnj) == (
        "Ação Penal - Procedimento Ordinário",
        417,
    )
    assert acordao.classe_citacao == "Apelação Criminal"
    assert acordao.relator == "Des. Aristeu Prudente Valença"
    assert acordao.relator_chave == "aristeu prudente valenca"
    assert acordao.turma_recursal is False
    assert acordao.data_julgamento == date(2026, 10, 9)
    assert acordao.data_publicacao is None
    assert acordao.data_disponibilizacao == date(2026, 10, 15)
    assert acordao.link_oficial == (
        f"https://comunicaapi.pje.jus.br/api/v1/comunicacao/{hash_comunicacao(900001)}/certidao"
    )
    assert acordao.link_tribunal == "https://tribunal.exemplo.invalid/consulta/documento/900001"
    assert acordao.ementa.startswith("EMENTA: DIREITO PENAL.")
    assert acordao.anonimizacao_versao == "c1-1+cpf-1+ner-falso-1"
    assert acordao.anonimizacao_substituicoes > 0
    assert (acordao.ativo_fonte, acordao.status_fonte, acordao.data_cancelamento) == (
        True,
        "P",
        None,
    )


def test_turma_recursal_sem_data_e_cancelado() -> None:
    assert normalizar(_anonimizado(900005)).turma_recursal is True
    assert normalizar(_anonimizado(900014)).data_julgamento is None
    cancelado = normalizar(_anonimizado(900015))
    assert cancelado.ativo_fonte is False
    assert cancelado.data_cancelamento == datetime.fromisoformat("2026-10-16T09:30:00-03:00")


def test_hash_de_conteudo() -> None:
    a = normalizar(_anonimizado(900001))
    assert a.hash_conteudo == normalizar(_anonimizado(900001)).hash_conteudo
    # Estado da fonte não muda o hash; conteúdo exibido muda.
    assert dataclasses.replace(a, ativo_fonte=False).hash_conteudo == a.hash_conteudo
    assert dataclasses.replace(a, ementa=a.ementa + " X").hash_conteudo != a.hash_conteudo
    assert dataclasses.replace(a, relator="Outro").hash_conteudo != a.hash_conteudo


def test_item_do_formato_recente() -> None:
    """Sem numeroprocessocommascara, meiocompleto e idOrgao; link nulo (F1-01)."""
    item = _anonimizado(900012)
    assert not {"numeroprocessocommascara", "meiocompleto", "idOrgao"} & set(item)
    assert item["link"] is None
    acordao = normalizar(item)
    digitos, mascara = numero_cnj(1012)
    assert (acordao.numero_processo, acordao.numero_processo_mascara) == (digitos, mascara)
    assert acordao.link_tribunal is None
    assert acordao.classe_citacao == acordao.classe_nome == "Apelação Cível"


def test_numero_do_cabecalho_conferido_contra_numero_processo(
    caplog: pytest.LogCaptureFixture,
) -> None:
    item = _anonimizado(900001)
    assert normalizar(item).numero_processo == item["numero_processo"]
    divergente = item | {"numero_processo": numero_cnj(4242)[0]}
    with caplog.at_level("WARNING"):
        acordao = normalizar(divergente)
    # Prevalece o campo estruturado, e o aviso traz só o id.
    assert acordao.numero_processo == numero_cnj(4242)[0]
    assert [r.getMessage() for r in caplog.records] == [
        "número do cabeçalho difere do campo estruturado"
    ]


def test_texto_nulo_e_falha_de_parser() -> None:
    with pytest.raises(FalhaParser):
        normalizar(_anonimizado(900001) | {"texto": None})


def test_link_do_tribunal_invalido_e_descartado() -> None:
    assert normalizar(_anonimizado(900001) | {"link": "javascript:alert(1)"}).link_tribunal is None


@pytest.mark.parametrize("campo", ["id", "hash"])
def test_item_sem_identificacao(campo: str) -> None:
    with pytest.raises(ItemInvalido):
        normalizar(_anonimizado(900001) | {campo: None})


def test_texto_ruim_e_falha_de_parser() -> None:
    with pytest.raises(FalhaParser):
        normalizar(_anonimizado(900001) | {"texto": "<p>curto</p>"})


# --- F1-24 -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "motivos"),
    [
        ("contato: fulano.tal@exemplo.invalid", ["email"]),
        ("telefone (41) 99999-0000", ["telefone"]),
        ("ligar para +55 41 99999-0000", ["telefone"]),
        ("Tel.: 3333-4444", ["telefone"]),
        ("advogado inscrito na OAB/PR 12.345", ["oab"]),
        ("OAB nº 12345/PR", ["oab"]),
        ("OAB-PR 98765", ["oab"]),
        ("Apelante: J.S.S.", ["rotulo_parte"]),
        ("RECORRIDO: Banco Fictício", ["rotulo_parte"]),
        ("Advogado(a): Fulano", ["rotulo_parte"]),
        ("Réu: F.T.", ["rotulo_parte"]),
        ("inscrito no CPF 529.982.247-25", ["cpf"]),
    ],
)
def test_pii_positivos(texto: str, motivos: list[str]) -> None:
    assert verificar_pii(texto) == motivos


@pytest.mark.parametrize(
    "texto",
    [
        "O apelante sustenta a nulidade; o recorrido não contrarrazoou.",
        "A OAB tem legitimidade para propor a ação (art. 103, VII, da CF).",
        "Processo nº 0001234-56.2099.8.16.9999; fls. 123-456.",
        "Valor de R$ 1.234.567,89, corrigido desde 21/09/2026.",
        "Lei 11.101/2005, art. 83, I; Súmula 299 do STJ; Tema 793 do STF.",
        "serviço de telefonia móvel; autos digitais; parte autora vencida",
        "CPF mascarado ***.***.***-**",
        "Autoria e materialidade comprovadas. Réu reincidente.",
        "CNPJ 11.444.777/0001-61 e nº 52998224725209981699",
    ],
)
def test_pii_negativos(texto: str) -> None:
    assert verificar_pii(texto) == []


def test_ementa_da_fixture_com_pii_vai_para_quarentena() -> None:
    acordao = normalizar(_anonimizado(900019))
    assert set(verificar_pii(acordao.ementa)) == {"email", "telefone", "rotulo_parte"}
    limpas = [e for e in dados.EMENTAS if e.id not in (900019,)]
    assert all(verificar_pii(normalizar(_anonimizado(e.id)).ementa) == [] for e in limpas)
