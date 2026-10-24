"""Upsert com versionamento (F1-25), cancelamentos (F1-26) e bloqueios (F1-27)."""

import dataclasses
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, text

from buscajus.ingest.modelos import AcordaoNormalizado
from buscajus.ingest.upsert import Resultado, marcar_cancelado, upsert

pytestmark = pytest.mark.banco

ACORDAO = AcordaoNormalizado(
    fonte="djen",
    id_fonte="900001",
    tribunal="TJPR",
    numero_processo="00010011020998169999",
    numero_processo_mascara="0001001-10.2099.8.16.9999",
    numero_processo_valido=True,
    ementa="EMENTA: DIREITO CIVIL. PARTILHA DE BENS NA HERANÇA. Recurso desprovido.",
    link_oficial="https://comunicaapi.pje.jus.br/api/v1/comunicacao/abc/certidao",
    relator="Des. Fulano Fictício",
    ativo_fonte=True,
    status_fonte="P",
)


def _linha(conexao: Connection, id_fonte: str = "900001") -> Any:
    return conexao.execute(
        text("SELECT *, situacao::text AS sit FROM acordao WHERE id_fonte = :id"), {"id": id_fonte}
    ).one_or_none()


def _upsert(conexao: Connection, acordao: AcordaoNormalizado = ACORDAO, **kwargs: Any) -> Resultado:
    return upsert(
        conexao, acordao, coleta_bruta_id=None, cancelado=kwargs.pop("cancelado", False), **kwargs
    )


def test_insercao_reinsercao_identica_e_alteracao(banco: Engine) -> None:
    with banco.begin() as conexao:
        assert _upsert(conexao) is Resultado.INSERIDO
        primeira = _linha(conexao)
        assert (primeira.versao, primeira.sit) == (1, "ativo")
        assert primeira.hash_conteudo == ACORDAO.hash_conteudo

        assert _upsert(conexao) is Resultado.ESTADO_ATUALIZADO
        assert _linha(conexao).versao == 1
        assert conexao.scalar(text("SELECT count(*) FROM acordao_historico")) == 0

        alterado = dataclasses.replace(ACORDAO, ementa=ACORDAO.ementa + " Texto corrigido.")
        assert _upsert(conexao, alterado) is Resultado.NOVA_VERSAO
        segunda = _linha(conexao)
        assert segunda.versao == 2
        assert segunda.ementa.endswith("Texto corrigido.")
        historico = conexao.execute(text("SELECT versao, snapshot FROM acordao_historico")).one()
        assert historico.versao == 1
        assert historico.snapshot["ementa"] == ACORDAO.ementa
        assert "busca_tsv" not in historico.snapshot
        assert conexao.scalar(text("SELECT count(*) FROM acordao")) == 1


def test_mesmo_hash_atualiza_so_o_estado(banco: Engine) -> None:
    with banco.begin() as conexao:
        _upsert(conexao)
        antes = _linha(conexao)
        cancelado = dataclasses.replace(ACORDAO, ativo_fonte=False, status_fonte="C")
        assert _upsert(conexao, cancelado, cancelado=True) is Resultado.ESTADO_ATUALIZADO
        depois = _linha(conexao)
        assert (depois.sit, depois.ativo_fonte, depois.status_fonte) == ("cancelado", False, "C")
        assert depois.versao == antes.versao
        assert depois.ultima_coleta_em >= antes.ultima_coleta_em


def test_cancelado_no_caderno_e_gravado_sem_apagar(banco: Engine) -> None:
    with banco.begin() as conexao:
        assert _upsert(conexao, cancelado=True) is Resultado.INSERIDO
        linha = _linha(conexao)
        assert (linha.sit, linha.motivo_situacao) == ("cancelado", "cancelado na fonte")


def test_quarentena_por_pii(banco: Engine) -> None:
    with banco.begin() as conexao:
        _upsert(conexao, motivos_pii=["email", "telefone"])
        linha = _linha(conexao)
        assert (linha.sit, linha.motivo_situacao) == ("quarentena", "PII residual: email, telefone")
        _upsert(conexao)
        assert _linha(conexao).sit == "ativo"


@pytest.mark.parametrize(
    "bloqueio",
    [
        "INSERT INTO bloqueio (fonte, id_fonte, motivo) VALUES ('djen', '900001', 'pedido')",
        "INSERT INTO bloqueio (numero_processo, motivo) VALUES ('00010011020998169999', 'pedido')",
    ],
)
def test_bloqueio_impede_insercao(banco: Engine, bloqueio: str) -> None:
    with banco.begin() as conexao:
        conexao.execute(text(bloqueio))
        assert _upsert(conexao) is Resultado.BLOQUEADO
        assert _linha(conexao) is None


def test_bloqueio_depois_da_coleta_remove_e_nao_reinsere(banco: Engine) -> None:
    with banco.begin() as conexao:
        _upsert(conexao)
        conexao.execute(
            text(
                "INSERT INTO bloqueio (fonte, id_fonte, motivo) VALUES ('djen', '900001', 'pedido')"
            )
        )
        assert _upsert(conexao) is Resultado.BLOQUEADO
        linha = _linha(conexao)
        assert (linha.sit, linha.motivo_situacao) == ("removido", "bloqueio")
        alterado = dataclasses.replace(ACORDAO, ementa=ACORDAO.ementa + " Nova versão.")
        assert _upsert(conexao, alterado) is Resultado.BLOQUEADO
        assert _linha(conexao).ementa == ACORDAO.ementa


@pytest.mark.parametrize("situacao", ["removido", "duplicado"])
def test_situacao_persistente_nao_e_desfeita(banco: Engine, situacao: str) -> None:
    with banco.begin() as conexao:
        _upsert(conexao)
        conexao.execute(
            text(
                "UPDATE acordao SET situacao = CAST(:s AS situacao_acordao), motivo_situacao = 'x'"
            ),
            {"s": situacao},
        )
        _upsert(conexao, dataclasses.replace(ACORDAO, ementa=ACORDAO.ementa + " Mudou."))
        linha = _linha(conexao)
        assert (linha.sit, linha.motivo_situacao, linha.versao) == (situacao, "x", 2)


def test_marcar_cancelado(banco: Engine) -> None:
    with banco.begin() as conexao:
        _upsert(conexao)
        marcar_cancelado(conexao, _linha(conexao).id, "ausente na versão 2 do caderno")
        linha = _linha(conexao)
        assert (linha.sit, linha.motivo_situacao) == ("cancelado", "ausente na versão 2 do caderno")
