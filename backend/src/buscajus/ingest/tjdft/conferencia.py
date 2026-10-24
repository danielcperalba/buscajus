"""Conferência mensal dos dias antigos do TJDFT (F2-14; ARCHITECTURE.md, seção 3.3).

A coleta diária recoleta os últimos 30 dias. Para os dias de 31 a 90 dias atrás, uma vez por
mês, faz uma requisição de tamanho 1 por dia e compara ``hits.value`` com o total registrado
na última coleta do dia (``coleta_janela.total_fonte``). Só os dias que mudaram, que nunca
foram coletados ou que não terminaram são recoletados (com ``forcar``).
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import Engine, text

from buscajus.core.erros import descrever_erro
from buscajus.ingest.runner import Orquestrador, Resultado
from buscajus.ingest.tjdft.conector import TRIBUNAL, ConectorTjdft


@dataclass
class DiaConferido:
    dia: date
    total_fonte: int | None
    total_coletado: int | None
    recoletado: bool
    resultado: str | None = None
    erro: str | None = None


def _coletados(engine: Engine, de: date, ate: date) -> dict[date, tuple[int | None, str]]:
    with engine.connect() as conexao:
        linhas = conexao.execute(
            text("""
                SELECT data_inicio, total_fonte, status FROM coleta_janela
                WHERE fonte = 'tjdft' AND tribunal = :tribunal AND data_inicio = data_fim
                  AND data_inicio BETWEEN :de AND :ate
            """),
            {"tribunal": TRIBUNAL, "de": de, "ate": ate},
        ).all()
    return {linha.data_inicio: (linha.total_fonte, linha.status) for linha in linhas}


def conferir_dias_antigos(
    engine: Engine,
    conector: ConectorTjdft,
    orquestrador: Orquestrador,
    *,
    hoje: date,
    de_dias: int = 31,
    ate_dias: int = 90,
) -> list[DiaConferido]:
    """Confere os dias de ``hoje - ate_dias`` a ``hoje - de_dias`` e recoleta os que mudaram."""
    inicio, fim = hoje - timedelta(days=ate_dias), hoje - timedelta(days=de_dias)
    coletados = _coletados(engine, inicio, fim)
    resultados = []
    for unidade in conector.planejar(TRIBUNAL, inicio, fim):
        dia = unidade.data_inicio
        total_coletado, status = coletados.get(dia, (None, None))
        conferido = DiaConferido(dia, None, total_coletado, recoletado=False)
        resultados.append(conferido)
        try:
            conferido.total_fonte = conector.contar(dia)
        except Exception as exc:
            conferido.erro = descrever_erro(exc)
            continue
        # Um dia vazio concluído não registra total (equivale a zero).
        if status == "concluida" and (total_coletado or 0) == conferido.total_fonte:
            continue
        resumo = orquestrador.executar_unidade(unidade, forcar=True)
        conferido.recoletado = True
        conferido.resultado = str(resumo.resultado)
        if resumo.resultado is Resultado.ERRO:
            conferido.erro = resumo.erro
    return resultados
