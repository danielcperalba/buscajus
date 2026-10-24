"""Estado persistido das unidades de coleta (``caderno_djen`` e ``coleta_janela``).

Unidades não paginadas (cadernos do DJEN) ficam em ``caderno_djen``; as paginadas, em
``coleta_janela``, com a última página processada como checkpoint.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import Connection, text

from buscajus.ingest.bruto import ArquivoBruto
from buscajus.ingest.conector import LoteBruto, UnidadeColeta


@dataclass(frozen=True)
class EstadoUnidade:
    id: int
    status: str
    concluida: bool
    ultima_pagina: int | None = None


class Repositorio(Protocol):
    def obter(self, conexao: Connection, unidade: UnidadeColeta) -> EstadoUnidade | None: ...

    def iniciar(
        self, conexao: Connection, unidade: UnidadeColeta, *, recomecar: bool
    ) -> EstadoUnidade: ...

    def registrar_lote(self, conexao: Connection, id_unidade: int, lote: LoteBruto) -> None: ...

    def concluir(
        self, conexao: Connection, id_unidade: int, respostas_429: int, versao_parser: str | None
    ) -> None: ...

    def marcar_sem_dados(
        self, conexao: Connection, id_unidade: int, respostas_429: int
    ) -> None: ...

    def marcar_pendente(self, conexao: Connection, id_unidade: int, respostas_429: int) -> None: ...

    def marcar_erro(
        self, conexao: Connection, id_unidade: int, respostas_429: int, erro: str
    ) -> None: ...


def _contadores(lote: LoteBruto) -> dict[str, Any]:
    c = lote.contadores
    return {
        "recebidos": c.recebidos,
        "aceitos": c.aceitos,
        "descartados": c.descartados,
        "rejeitados": list(c.rejeitados_anonimizacao),
        "falhas_parser": c.falhas_parser,
        "quarentena": c.quarentena,
        "cancelados": c.cancelados,
        "bloqueados": c.bloqueados,
        "anomalias": c.anomalias,
        "total_fonte": lote.total_fonte,
    }


class RepositorioCadernos:
    """Cadernos do DJEN: interrompido ou forçado, o caderno recomeça do zero."""

    _ZERAR = """
        comunicacoes_lidas = 0, acordaos_aceitos = 0, rejeitados_anonimizacao = '{}',
        falhas_parser = 0, quarentena = 0, cancelados = 0, bloqueados = 0, anomalias = 0,
        respostas_429 = 0
    """

    def obter(self, conexao: Connection, unidade: UnidadeColeta) -> EstadoUnidade | None:
        linha = conexao.execute(
            text("SELECT id, status FROM caderno_djen WHERE tribunal = :tribunal AND data = :data"),
            {"tribunal": unidade.tribunal, "data": unidade.data_inicio},
        ).one_or_none()
        if linha is None:
            return None
        return EstadoUnidade(linha.id, linha.status, linha.status in ("processado", "sem_caderno"))

    def iniciar(
        self, conexao: Connection, unidade: UnidadeColeta, *, recomecar: bool
    ) -> EstadoUnidade:
        # Um caderno nunca é retomado pela metade: o upsert é idempotente.
        linha = conexao.execute(
            text(f"""
                INSERT INTO caderno_djen (tribunal, data, status, tentativas, iniciado_em)
                VALUES (:tribunal, :data, 'em_andamento', 1, now())
                ON CONFLICT (tribunal, data) DO UPDATE SET
                    status = 'em_andamento',
                    tentativas = caderno_djen.tentativas + 1,
                    iniciado_em = now(),
                    ultimo_erro = NULL,
                    {self._ZERAR}
                RETURNING id, status
            """),  # noqa: S608 (interpola só constantes do módulo)
            {"tribunal": unidade.tribunal, "data": unidade.data_inicio},
        ).one()
        return EstadoUnidade(linha.id, linha.status, concluida=False)

    def registrar_lote(self, conexao: Connection, id_unidade: int, lote: LoteBruto) -> None:
        caderno = lote.caderno
        conexao.execute(
            text("""
                UPDATE caderno_djen SET
                    comunicacoes_lidas = comunicacoes_lidas + :recebidos,
                    acordaos_aceitos = acordaos_aceitos + :aceitos,
                    rejeitados_anonimizacao =
                        rejeitados_anonimizacao || CAST(:rejeitados AS text[]),
                    falhas_parser = falhas_parser + :falhas_parser,
                    quarentena = quarentena + :quarentena,
                    cancelados = cancelados + :cancelados,
                    bloqueados = bloqueados + :bloqueados,
                    anomalias = anomalias + :anomalias,
                    total_fonte = coalesce(:total_fonte, total_fonte),
                    versao = coalesce(:versao, versao),
                    hash = coalesce(:hash, hash),
                    bytes = coalesce(:bytes, bytes)
                WHERE id = :id
            """),
            _contadores(lote)
            | {
                "id": id_unidade,
                "versao": caderno.versao if caderno else None,
                "hash": caderno.hash if caderno else None,
                "bytes": caderno.bytes if caderno else None,
            },
        )

    def concluir(
        self, conexao: Connection, id_unidade: int, respostas_429: int, versao_parser: str | None
    ) -> None:
        conexao.execute(
            text("""
                UPDATE caderno_djen SET status = 'processado', processado_em = now(),
                    verificado_em = now(), versao_parser = :versao_parser,
                    respostas_429 = respostas_429 + :r429
                WHERE id = :id
            """),
            {"id": id_unidade, "versao_parser": versao_parser, "r429": respostas_429},
        )

    def marcar_sem_dados(self, conexao: Connection, id_unidade: int, respostas_429: int) -> None:
        self._status(conexao, id_unidade, "sem_caderno", respostas_429, processado=True)

    def marcar_pendente(self, conexao: Connection, id_unidade: int, respostas_429: int) -> None:
        self._status(conexao, id_unidade, "pendente", respostas_429)

    def marcar_erro(
        self, conexao: Connection, id_unidade: int, respostas_429: int, erro: str
    ) -> None:
        self._status(conexao, id_unidade, "erro", respostas_429, erro=erro)

    def _status(
        self,
        conexao: Connection,
        id_unidade: int,
        status: str,
        respostas_429: int,
        *,
        erro: str | None = None,
        processado: bool = False,
    ) -> None:
        conexao.execute(
            text("""
                UPDATE caderno_djen SET status = :status, ultimo_erro = :erro,
                    respostas_429 = respostas_429 + :r429,
                    verificado_em = now(),
                    processado_em = CASE WHEN :processado THEN now() ELSE processado_em END
                WHERE id = :id
            """),
            {
                "id": id_unidade,
                "status": status,
                "erro": erro,
                "r429": respostas_429,
                "processado": processado,
            },
        )


class RepositorioJanelas:
    """Janelas paginadas: o checkpoint é a última página processada."""

    _CHAVE = (
        "fonte = :fonte AND tribunal = :tribunal "
        "AND data_inicio = :data_inicio AND data_fim = :data_fim"
    )

    def obter(self, conexao: Connection, unidade: UnidadeColeta) -> EstadoUnidade | None:
        linha = conexao.execute(
            text(f"SELECT id, status, ultima_pagina FROM coleta_janela WHERE {self._CHAVE}"),  # noqa: S608
            _chave(unidade),
        ).one_or_none()
        if linha is None:
            return None
        return EstadoUnidade(
            linha.id, linha.status, linha.status == "concluida", linha.ultima_pagina
        )

    def iniciar(
        self, conexao: Connection, unidade: UnidadeColeta, *, recomecar: bool
    ) -> EstadoUnidade:
        zerar = """,
            ultima_pagina = NULL, total_fonte = NULL, itens_recebidos = 0, itens_aceitos = 0,
            itens_descartados = 0, rejeitados_anonimizacao = '{}', falhas_parser = 0,
            quarentena = 0, cancelados = 0, bloqueados = 0, anomalias = 0, respostas_429 = 0
        """
        linha = conexao.execute(
            text(f"""
                INSERT INTO coleta_janela
                    (fonte, tribunal, data_inicio, data_fim, status, tentativas, iniciada_em)
                VALUES (:fonte, :tribunal, :data_inicio, :data_fim, 'em_andamento', 1, now())
                ON CONFLICT (fonte, tribunal, data_inicio, data_fim) DO UPDATE SET
                    status = 'em_andamento',
                    tentativas = coleta_janela.tentativas + 1,
                    iniciada_em = now(),
                    ultimo_erro = NULL
                    {zerar if recomecar else ""}
                RETURNING id, status, ultima_pagina
            """),  # noqa: S608 (interpola só constantes do módulo)
            _chave(unidade),
        ).one()
        return EstadoUnidade(linha.id, linha.status, False, linha.ultima_pagina)

    def registrar_lote(self, conexao: Connection, id_unidade: int, lote: LoteBruto) -> None:
        conexao.execute(
            text("""
                UPDATE coleta_janela SET
                    ultima_pagina = coalesce(:pagina, ultima_pagina),
                    itens_recebidos = itens_recebidos + :recebidos,
                    itens_aceitos = itens_aceitos + :aceitos,
                    itens_descartados = itens_descartados + :descartados,
                    rejeitados_anonimizacao =
                        rejeitados_anonimizacao || CAST(:rejeitados AS text[]),
                    falhas_parser = falhas_parser + :falhas_parser,
                    quarentena = quarentena + :quarentena,
                    cancelados = cancelados + :cancelados,
                    bloqueados = bloqueados + :bloqueados,
                    anomalias = anomalias + :anomalias,
                    total_fonte = coalesce(:total_fonte, total_fonte)
                WHERE id = :id
            """),
            _contadores(lote) | {"id": id_unidade, "pagina": lote.pagina},
        )

    def concluir(
        self, conexao: Connection, id_unidade: int, respostas_429: int, versao_parser: str | None
    ) -> None:
        conexao.execute(
            text("""
                UPDATE coleta_janela SET status = 'concluida', concluida_em = now(),
                    versao_parser = :versao_parser, respostas_429 = respostas_429 + :r429
                WHERE id = :id
            """),
            {"id": id_unidade, "versao_parser": versao_parser, "r429": respostas_429},
        )

    def marcar_sem_dados(self, conexao: Connection, id_unidade: int, respostas_429: int) -> None:
        # Janela vazia é uma janela concluída com zero itens.
        self.concluir(conexao, id_unidade, respostas_429, None)

    def marcar_pendente(self, conexao: Connection, id_unidade: int, respostas_429: int) -> None:
        self._status(conexao, id_unidade, "pendente", respostas_429, None)

    def marcar_erro(
        self, conexao: Connection, id_unidade: int, respostas_429: int, erro: str
    ) -> None:
        self._status(conexao, id_unidade, "erro", respostas_429, erro)

    def _status(
        self,
        conexao: Connection,
        id_unidade: int,
        status: str,
        respostas_429: int,
        erro: str | None,
    ) -> None:
        conexao.execute(
            text("""
                UPDATE coleta_janela SET status = :status, ultimo_erro = :erro,
                    respostas_429 = respostas_429 + :r429
                WHERE id = :id
            """),
            {"id": id_unidade, "status": status, "erro": erro, "r429": respostas_429},
        )


def _chave(unidade: UnidadeColeta) -> dict[str, Any]:
    return {
        "fonte": unidade.fonte,
        "tribunal": unidade.tribunal,
        "data_inicio": unidade.data_inicio,
        "data_fim": unidade.data_fim,
    }


def repositorio_para(unidade: UnidadeColeta) -> Repositorio:
    return RepositorioJanelas() if unidade.paginada else RepositorioCadernos()


def registrar_coleta_bruta(
    conexao: Connection,
    unidade: UnidadeColeta,
    id_unidade: int,
    arquivo: ArquivoBruto,
    pagina: int | None,
    versao_parser: str | None,
) -> int:
    """Registra (ou atualiza, se o arquivo foi regravado) e devolve o id em ``coleta_bruta``."""
    id_bruta: int = conexao.execute(
        text("""
            INSERT INTO coleta_bruta (fonte, caderno_djen_id, coleta_janela_id, pagina,
                caminho_arquivo, sha256, bytes, itens, versao_parser)
            VALUES (:fonte, :caderno, :janela, :pagina, :caminho, :sha256, :bytes, :itens,
                :versao_parser)
            ON CONFLICT (caminho_arquivo) DO UPDATE SET
                sha256 = excluded.sha256, bytes = excluded.bytes, itens = excluded.itens,
                versao_parser = excluded.versao_parser, recebida_em = now()
            RETURNING id
        """),
        {
            "fonte": unidade.fonte,
            "caderno": None if unidade.paginada else id_unidade,
            "janela": id_unidade if unidade.paginada else None,
            "pagina": pagina,
            "caminho": arquivo.caminho_relativo,
            "sha256": arquivo.sha256,
            "bytes": arquivo.bytes,
            "itens": arquivo.itens,
            "versao_parser": versao_parser,
        },
    ).scalar_one()
    return id_bruta
