"""Agendador do worker sobre a fila ``tarefa`` (F1-30)."""

from collections.abc import Mapping
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine, text

from buscajus.core.config import Config
from buscajus.ingest.agendador import TAREFA_DJEN_DIARIO, Agendador, coleta_djen_diaria
from buscajus.ingest.anonimizacao.pipeline import ErroAnonimizacao

pytestmark = pytest.mark.banco

FUSO = ZoneInfo("America/Sao_Paulo")


class Relogio:
    def __init__(self, quando: datetime) -> None:
        self.quando = quando

    def __call__(self) -> datetime:
        return self.quando


def _tarefas(banco: Engine) -> list[Any]:
    with banco.connect() as conexao:
        return conexao.execute(
            text("SELECT tipo, payload, status, tentativas, ultimo_erro FROM tarefa ORDER BY id")
        ).all()


def _agendador(banco: Engine, relogio: Relogio, executar: Any) -> Agendador:
    config = Config(agendador={"ativo": True, "horario_djen": time(9, 0)})
    return Agendador(banco, config, {TAREFA_DJEN_DIARIO: executar}, agora=relogio)


def test_desligado_por_padrao() -> None:
    assert Config().agendador.ativo is False


def test_dispara_uma_vez_por_dia_e_registra(banco: Engine) -> None:
    execucoes: list[Mapping[str, Any]] = []
    relogio = Relogio(datetime(2026, 10, 20, 8, 59, tzinfo=FUSO))
    agendador = _agendador(banco, relogio, execucoes.append)

    assert agendador.ciclo() == 0  # antes do horário
    assert _tarefas(banco) == []

    relogio.quando = datetime(2026, 10, 20, 9, 0, tzinfo=FUSO)
    assert agendador.ciclo() == 1
    relogio.quando = datetime(2026, 10, 20, 15, 0, tzinfo=FUSO)
    assert agendador.ciclo() == 0  # mesmo dia: não repete

    relogio.quando = datetime(2026, 10, 21, 9, 30, tzinfo=FUSO)
    assert agendador.ciclo() == 1
    assert execucoes == [
        {"tribunal": "TJPR", "data": "2026-10-20"},
        {"tribunal": "TJPR", "data": "2026-10-21"},
    ]
    tarefas = _tarefas(banco)
    assert [(t.tipo, t.status, t.tentativas) for t in tarefas] == [
        (TAREFA_DJEN_DIARIO, "concluida", 1),
        (TAREFA_DJEN_DIARIO, "concluida", 1),
    ]


def test_erro_fica_registrado_sem_conteudo(banco: Engine) -> None:
    def falhar(_payload: Mapping[str, Any]) -> None:
        raise ValueError("CONTEÚDO de comunicação")

    relogio = Relogio(datetime(2026, 10, 20, 10, 0, tzinfo=FUSO))
    _agendador(banco, relogio, falhar).ciclo()
    (tarefa,) = _tarefas(banco)
    assert tarefa.status == "erro"
    assert tarefa.ultimo_erro.startswith("ValueError em test_agendador.py:")
    assert "CONTEÚDO" not in tarefa.ultimo_erro


def test_tipo_desconhecido_vira_erro(banco: Engine) -> None:
    with banco.begin() as conexao:
        conexao.execute(text("INSERT INTO tarefa (tipo, agendada_para) VALUES ('outro', now())"))
    relogio = Relogio(datetime.now(FUSO))
    agendador = Agendador(banco, Config(), {}, agora=relogio)
    assert agendador.executar_proxima()
    assert _tarefas(banco)[0].status == "erro"


def test_tarefa_diaria_sem_ner_falha_fechada(banco: Engine) -> None:
    executar = coleta_djen_diaria(Config(), banco)
    with pytest.raises(ErroAnonimizacao):
        executar({"tribunal": "TJPR", "data": "2026-10-20"})
    with banco.connect() as conexao:
        assert conexao.scalar(text("SELECT count(*) FROM caderno_djen")) == 0
