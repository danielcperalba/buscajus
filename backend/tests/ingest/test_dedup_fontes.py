"""Salvaguarda de dedup entre fontes (F2-09): API do tribunal > DJEN."""

import dataclasses
from datetime import date
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, text

from buscajus.ingest.modelos import AcordaoNormalizado
from buscajus.ingest.upsert import MOTIVO_DUPLICADO, upsert

pytestmark = pytest.mark.banco

NUMERO = "00010011020998079999"
MASCARA = "0001001-10.2099.8.07.9999"

# O mesmo acórdão sintético nas duas fontes.
DJEN = AcordaoNormalizado(
    fonte="djen",
    id_fonte="900001",
    tribunal="TJDFT",
    numero_processo=NUMERO,
    numero_processo_mascara=MASCARA,
    numero_processo_valido=True,
    ementa="DIREITO CIVIL. PARTILHA DE BENS. Recurso desprovido.",
    link_oficial="https://comunicaapi.pje.jus.br/api/v1/comunicacao/abc/certidao",
    data_julgamento=date(2026, 10, 8),
    data_disponibilizacao=date(2026, 10, 14),
    ativo_fonte=True,
    status_fonte="P",
)
TJDFT = AcordaoNormalizado(
    fonte="tjdft",
    id_fonte="0f1c7e00-2099-4000-8000-000000000001",
    tribunal="TJDFT",
    numero_processo=NUMERO,
    numero_processo_mascara=MASCARA,
    numero_processo_valido=True,
    ementa="DIREITO CIVIL. PARTILHA DE BENS. Recurso desprovido.",
    link_oficial="https://jurisdf.tjdft.jus.br/acordaos/0f1c7e00-2099-4000-8000-000000000001",
    data_julgamento=date(2026, 10, 8),
    data_publicacao=date(2026, 10, 14),
)


def _upsert(conexao: Connection, acordao: AcordaoNormalizado, **kwargs: Any) -> None:
    upsert(conexao, acordao, coleta_bruta_id=None, cancelado=False, **kwargs)


def _linhas(conexao: Connection) -> dict[str, Any]:
    linhas = conexao.execute(
        text(
            "SELECT id, fonte::text AS fonte, situacao::text AS sit, motivo_situacao, "
            "duplicata_de FROM acordao"
        )
    ).all()
    return {linha.fonte: linha for linha in linhas}


def test_djen_depois_do_tjdft_entra_como_duplicado(banco: Engine) -> None:
    with banco.begin() as conexao:
        _upsert(conexao, TJDFT)
        _upsert(conexao, DJEN)
        linhas = _linhas(conexao)
    assert linhas["tjdft"].sit == "ativo"
    assert linhas["djen"].sit == "duplicado"
    assert linhas["djen"].duplicata_de == linhas["tjdft"].id
    assert linhas["djen"].motivo_situacao == MOTIVO_DUPLICADO


def test_tjdft_depois_do_djen_marca_o_djen_como_duplicado(banco: Engine) -> None:
    with banco.begin() as conexao:
        _upsert(conexao, DJEN)
        assert _linhas(conexao)["djen"].sit == "ativo"
        _upsert(conexao, TJDFT)
        linhas = _linhas(conexao)
    assert linhas["tjdft"].sit == "ativo" and linhas["tjdft"].duplicata_de is None
    assert linhas["djen"].sit == "duplicado"
    assert linhas["djen"].duplicata_de == linhas["tjdft"].id


def test_recoleta_nao_desfaz_o_duplicado(banco: Engine) -> None:
    with banco.begin() as conexao:
        _upsert(conexao, DJEN)
        _upsert(conexao, TJDFT)
        _upsert(conexao, DJEN)
        _upsert(conexao, dataclasses.replace(DJEN, ementa=DJEN.ementa + " Corrigido."))
        assert _linhas(conexao)["djen"].sit == "duplicado"


def test_sem_julgamento_compara_publicacao_e_disponibilizacao(banco: Engine) -> None:
    djen = dataclasses.replace(DJEN, data_julgamento=None)
    tjdft = dataclasses.replace(TJDFT, data_julgamento=None)
    with banco.begin() as conexao:
        _upsert(conexao, djen)
        _upsert(conexao, tjdft)
        assert _linhas(conexao)["djen"].sit == "duplicado"


@pytest.mark.parametrize(
    "alteracao",
    [
        {"data_julgamento": date(2026, 10, 9)},
        {"numero_processo": "00010029020998079999"},
    ],
    ids=["outra data", "outro processo"],
)
def test_outro_acordao_nao_e_duplicado(banco: Engine, alteracao: dict[str, Any]) -> None:
    with banco.begin() as conexao:
        _upsert(conexao, DJEN)
        _upsert(conexao, dataclasses.replace(TJDFT, **alteracao))
        linhas = _linhas(conexao)
    assert {linhas["djen"].sit, linhas["tjdft"].sit} == {"ativo"}


def test_so_um_acordao_ativo_torna_o_outro_duplicado(banco: Engine) -> None:
    with banco.begin() as conexao:
        _upsert(conexao, DJEN)
        # TJDFT em quarentena (PII residual) não esconde o DJEN.
        _upsert(conexao, TJDFT, motivos_pii=["email"])
        linhas = _linhas(conexao)
        assert (linhas["tjdft"].sit, linhas["djen"].sit) == ("quarentena", "ativo")
        # Um DJEN cancelado continua cancelado, mesmo com o TJDFT ativo.
        conexao.execute(text("DELETE FROM acordao"))
        _upsert(conexao, TJDFT)
        upsert(conexao, DJEN, coleta_bruta_id=None, cancelado=True)
        assert _linhas(conexao)["djen"].sit == "cancelado"


def test_mesma_fonte_nao_e_dedup_entre_fontes(banco: Engine) -> None:
    with banco.begin() as conexao:
        _upsert(conexao, DJEN)
        _upsert(conexao, dataclasses.replace(DJEN, id_fonte="900002"))
        situacoes = conexao.scalars(text("SELECT situacao::text FROM acordao")).all()
    assert situacoes == ["ativo", "ativo"]
