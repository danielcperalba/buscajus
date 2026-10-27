"""Decisão dos pedidos de remoção (F4-12; ARCHITECTURE.md, seção 6.5).

``buscajus remocao listar | aceitar | rejeitar | limpar-contatos``:

- aceitar: remove pela regra geral do F2-13 (``ingest.remocao.remover``) o acórdão do pedido
  ou todos os do número do processo; pedido por número também cria um ``bloqueio`` por
  ``numero_processo``, para que acórdãos do processo coletados depois não entrem;
- rejeitar: só registra a decisão;
- limpar-contatos: apaga o e-mail dos pedidos resolvidos há mais de ``retencao_contato_dias``.

Uma remoção só é desfeita por ação manual no banco (apagar o bloqueio e recoletar).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, Engine, text

from buscajus.core.erros import ErroSeguro
from buscajus.ingest.bruto import ArmazenamentoBruto
from buscajus.ingest.remocao import remover

MOTIVO_ACEITO = "pedido de remoção aceito"


class PedidoInvalido(ErroSeguro):
    pass


@dataclass(frozen=True)
class Pedido:
    id: int
    acordao_id: int | None
    numero_processo: str | None
    motivo: str
    contato: str | None
    status: str
    criado_em: datetime


def listar(engine: Engine, status: str = "pendente") -> list[Pedido]:
    with engine.connect() as conexao:
        linhas = conexao.execute(
            text("""
                SELECT id, acordao_id, numero_processo, motivo, contato, status, criado_em
                FROM pedido_remocao WHERE status = :status ORDER BY criado_em, id
            """),
            {"status": status},
        ).all()
    return [Pedido(**linha._mapping) for linha in linhas]


def _pendente(conexao: Connection, pedido_id: int) -> Any:
    pedido = conexao.execute(
        text("SELECT * FROM pedido_remocao WHERE id = :id FOR UPDATE"), {"id": pedido_id}
    ).one_or_none()
    if pedido is None:
        raise PedidoInvalido(f"pedido {pedido_id} não existe")
    if pedido.status != "pendente":
        raise PedidoInvalido(f"pedido {pedido_id} já está {pedido.status}")
    return pedido


def _resolver(conexao: Connection, pedido_id: int, status: str, decisao: str) -> None:
    conexao.execute(
        text("""
            UPDATE pedido_remocao SET status = :status, decisao = :decisao, resolvido_em = now()
            WHERE id = :id
        """),
        {"id": pedido_id, "status": status, "decisao": decisao},
    )


def aceitar(engine: Engine, bruto: ArmazenamentoBruto, pedido_id: int, decisao: str) -> list[int]:
    """Remove os acórdãos do pedido. Devolve os ids removidos."""
    with engine.begin() as conexao:
        pedido = _pendente(conexao, pedido_id)
        if pedido.acordao_id is not None:
            ids = [pedido.acordao_id]
        else:
            ids = list(
                conexao.scalars(
                    text("SELECT id FROM acordao WHERE numero_processo = :numero"),
                    {"numero": pedido.numero_processo},
                )
            )
            conexao.execute(
                text("""
                    INSERT INTO bloqueio (numero_processo, motivo, pedido_remocao_id)
                    VALUES (:numero, :motivo, :pedido)
                """),
                {"numero": pedido.numero_processo, "motivo": MOTIVO_ACEITO, "pedido": pedido_id},
            )
        removidos = remover(conexao, bruto, ids, MOTIVO_ACEITO, pedido_remocao_id=pedido_id)
        _resolver(conexao, pedido_id, "aceito", decisao)
    return removidos


def rejeitar(engine: Engine, pedido_id: int, decisao: str) -> None:
    with engine.begin() as conexao:
        _pendente(conexao, pedido_id)
        _resolver(conexao, pedido_id, "rejeitado", decisao)


def limpar_contatos(engine: Engine, dias: int) -> int:
    """Apaga o e-mail dos pedidos resolvidos há mais de ``dias`` dias."""
    with engine.begin() as conexao:
        return len(
            conexao.execute(
                text("""
                    UPDATE pedido_remocao SET contato = NULL
                    WHERE status <> 'pendente' AND contato IS NOT NULL
                      AND resolvido_em < now() - make_interval(days => :dias)
                    RETURNING id
                """),
                {"dias": dias},
            ).all()
        )
