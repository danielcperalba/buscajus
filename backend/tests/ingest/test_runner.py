"""Orquestrador genérico (F1-09) e retomada (F1-10) com um conector falso."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, text

from buscajus.ingest.bruto import ArmazenamentoBruto, caminho_caderno, caminho_pagina
from buscajus.ingest.conector import (
    Checkpoint,
    Contadores,
    Fonte,
    LoteBruto,
    MetadadosCaderno,
    UnidadeColeta,
    UnidadeNaoPronta,
    UnidadeSemDados,
)
from buscajus.ingest.http import Estatisticas
from buscajus.ingest.runner import Orquestrador, Resultado

pytestmark = pytest.mark.banco

DIA = date(2026, 10, 15)


class Interrupcao(BaseException):
    """Simula o processo sendo morto no meio da unidade."""


@dataclass
class ConectorFalso:
    paginada: bool
    paginas: int = 3
    itens_por_pagina: int = 2
    falhar_em: tuple[date, int] | None = None
    interromper_em: tuple[date, int] | None = None
    interromper_depois_do_lote: bool = False
    sem_dados: set[date] = field(default_factory=set)
    nao_pronta: set[date] = field(default_factory=set)
    campo_proibido: bool = False
    estatisticas: Estatisticas | None = None
    chamadas: list[tuple[UnidadeColeta, Checkpoint]] = field(default_factory=list)
    fechamentos: int = 0
    lista_branca: frozenset[str] = frozenset({"id", "texto"})

    @property
    def fonte(self) -> Fonte:
        return "tjdft" if self.paginada else "djen"

    def planejar(self, tribunal: str, inicio: date, fim: date) -> list[UnidadeColeta]:
        dias = (fim - inicio).days + 1
        return [
            UnidadeColeta(self.fonte, tribunal, dia, dia, self.paginada)
            for dia in (fim - timedelta(days=i) for i in range(dias))
        ]

    def coletar(self, unidade: UnidadeColeta, checkpoint: Checkpoint) -> Iterator[LoteBruto]:
        self.chamadas.append((unidade, checkpoint))
        try:
            dia = unidade.data_inicio
            if dia in self.sem_dados:
                raise UnidadeSemDados
            if dia in self.nao_pronta:
                raise UnidadeNaoPronta
            if self.estatisticas:
                self.estatisticas.respostas_429 += 2
            paginas = range(checkpoint.proxima_pagina, self.paginas) if self.paginada else [0]
            for pagina in paginas:
                if self.falhar_em == (dia, pagina):
                    raise ValueError("NOME DE PARTE no texto da comunicação")
                if self.interromper_em == (dia, pagina) and not self.interromper_depois_do_lote:
                    raise Interrupcao
                yield self._lote(unidade, pagina)
                if self.interromper_em == (dia, pagina):
                    raise Interrupcao
        finally:
            self.fechamentos += 1

    def _lote(self, unidade: UnidadeColeta, pagina: int) -> LoteBruto:
        itens: list[dict[str, Any]] = [
            {"id": f"{unidade.data_inicio}-{pagina}-{i}", "texto": "ementa"}
            for i in range(self.itens_por_pagina)
        ]
        if self.campo_proibido:
            itens[0]["destinatarios"] = [{"nome": "MARCADOR"}]
        contadores = Contadores(
            recebidos=10,
            aceitos=len(itens),
            descartados=10 - len(itens),
            rejeitados_anonimizacao=["99"],
        )
        if self.paginada:
            return LoteBruto(
                itens,
                caminho_pagina(self.fonte, unidade.tribunal, unidade.data_inicio, pagina),
                contadores,
                pagina=pagina,
                total_fonte=self.paginas * self.itens_por_pagina,
            )
        return LoteBruto(
            itens,
            caminho_caderno(unidade.tribunal, unidade.data_inicio, 1),
            contadores,
            total_fonte=10,
            caderno=MetadadosCaderno(versao=1, hash="abc", bytes=123),
        )


def _orquestrador(
    banco: Engine, conector: ConectorFalso, tmp_path: Path, **kwargs: Any
) -> Orquestrador:
    return Orquestrador(banco, conector, ArmazenamentoBruto(tmp_path), **kwargs)


def _linha(banco: Engine, sql: str, **parametros: Any) -> Any:
    with banco.connect() as conexao:
        return conexao.execute(text(sql), parametros).one()


def _contar(banco: Engine, tabela: str) -> int:
    resultado: int = _linha(banco, f"SELECT count(*) FROM {tabela}")[0]  # noqa: S608
    return resultado


# --- F1-09: percorre unidades com e sem paginação ------------------------------------


def test_cadernos_sem_paginacao(banco: Engine, tmp_path: Path) -> None:
    conector = ConectorFalso(paginada=False)
    unidades = conector.planejar("TJPR", DIA - timedelta(days=2), DIA)
    resumos = _orquestrador(banco, conector, tmp_path, versao_parser="p1").executar(unidades)

    assert [r.resultado for r in resumos] == [Resultado.CONCLUIDA] * 3
    assert [u.data_inicio for u, _ in conector.chamadas] == [
        DIA,
        DIA - timedelta(days=1),
        DIA - timedelta(days=2),
    ]
    caderno = _linha(banco, "SELECT * FROM caderno_djen WHERE data = :d", d=DIA)
    assert caderno.status == "processado"
    assert (caderno.versao, caderno.hash, caderno.bytes, caderno.total_fonte) == (1, "abc", 123, 10)
    assert (caderno.comunicacoes_lidas, caderno.acordaos_aceitos) == (10, 2)
    assert caderno.rejeitados_anonimizacao == ["99"]
    assert caderno.versao_parser == "p1"
    assert caderno.processado_em is not None
    assert _contar(banco, "coleta_bruta") == 3
    assert (tmp_path / "djen/TJPR/2026-10-15/v1.jsonl.gz").exists()


def test_janelas_paginadas(banco: Engine, tmp_path: Path) -> None:
    conector = ConectorFalso(paginada=True, paginas=3)
    unidades = conector.planejar("TJDFT", DIA - timedelta(days=1), DIA)
    resumos = _orquestrador(banco, conector, tmp_path).executar(unidades)

    assert [r.lotes for r in resumos] == [3, 3]
    janela = _linha(banco, "SELECT * FROM coleta_janela WHERE data_inicio = :d", d=DIA)
    assert janela.status == "concluida"
    assert (janela.ultima_pagina, janela.total_fonte) == (2, 6)
    assert (janela.itens_recebidos, janela.itens_aceitos, janela.itens_descartados) == (30, 6, 24)
    paginas = _linha(
        banco,
        "SELECT array_agg(pagina ORDER BY pagina) FROM coleta_bruta WHERE coleta_janela_id = :id",
        id=janela.id,
    )[0]
    assert paginas == [0, 1, 2]


def test_processador_roda_na_transacao_do_lote(banco: Engine, tmp_path: Path) -> None:
    vistos: list[int] = []

    def processar(conexao: Connection, lote: LoteBruto, coleta_bruta_id: int) -> Contadores:
        # O registro do bruto já está visível na mesma transação.
        assert conexao.scalar(
            text("SELECT itens FROM coleta_bruta WHERE id = :id"), {"id": coleta_bruta_id}
        ) == len(lote.itens)
        vistos.append(coleta_bruta_id)
        return Contadores(quarentena=1, falhas_parser=2, cancelados=3)

    conector = ConectorFalso(paginada=False)
    _orquestrador(banco, conector, tmp_path, processar=processar).executar(
        conector.planejar("TJPR", DIA, DIA)
    )
    caderno = _linha(banco, "SELECT * FROM caderno_djen")
    assert (caderno.quarentena, caderno.falhas_parser, caderno.cancelados) == (1, 2, 3)
    assert len(vistos) == 1


def test_erro_no_processador_desfaz_o_lote(banco: Engine, tmp_path: Path) -> None:
    def processar(conexao: Connection, lote: LoteBruto, coleta_bruta_id: int) -> Contadores:
        raise RuntimeError("falha com CONTEÚDO da ementa")

    conector = ConectorFalso(paginada=False)
    (resumo,) = _orquestrador(banco, conector, tmp_path, processar=processar).executar(
        conector.planejar("TJPR", DIA, DIA)
    )
    assert resumo.resultado is Resultado.ERRO
    assert _contar(banco, "coleta_bruta") == 0
    caderno = _linha(banco, "SELECT status, acordaos_aceitos, ultimo_erro FROM caderno_djen")
    assert (caderno.status, caderno.acordaos_aceitos) == ("erro", 0)
    assert "CONTEÚDO" not in caderno.ultimo_erro


def test_sem_dados_e_nao_pronta(banco: Engine, tmp_path: Path) -> None:
    conector = ConectorFalso(paginada=False, sem_dados={DIA}, nao_pronta={DIA - timedelta(days=1)})
    resumos = _orquestrador(banco, conector, tmp_path).executar(
        conector.planejar("TJPR", DIA - timedelta(days=1), DIA)
    )
    assert [r.resultado for r in resumos] == [Resultado.SEM_DADOS, Resultado.NAO_PRONTA]
    with banco.connect() as conexao:
        status = dict(conexao.execute(text("SELECT data, status FROM caderno_djen")).all())
    assert status == {DIA: "sem_caderno", DIA - timedelta(days=1): "pendente"}


def test_erro_marca_a_unidade_sem_conteudo_e_segue(banco: Engine, tmp_path: Path) -> None:
    conector = ConectorFalso(paginada=False, falhar_em=(DIA, 0))
    resumos = _orquestrador(banco, conector, tmp_path).executar(
        conector.planejar("TJPR", DIA - timedelta(days=1), DIA)
    )
    assert [r.resultado for r in resumos] == [Resultado.ERRO, Resultado.CONCLUIDA]
    caderno = _linha(
        banco, "SELECT status, ultimo_erro, tentativas FROM caderno_djen WHERE data = :d", d=DIA
    )
    assert caderno.status == "erro"
    assert caderno.tentativas == 1
    assert caderno.ultimo_erro.startswith("ValueError em test_runner.py:")
    assert "NOME DE PARTE" not in caderno.ultimo_erro


def test_campo_fora_da_lista_branca_vira_erro_e_fecha_o_conector(
    banco: Engine, tmp_path: Path
) -> None:
    conector = ConectorFalso(paginada=False, campo_proibido=True)
    (resumo,) = _orquestrador(banco, conector, tmp_path).executar(
        conector.planejar("TJPR", DIA, DIA)
    )
    assert resumo.resultado is Resultado.ERRO
    assert resumo.erro is not None
    assert "destinatarios" in resumo.erro
    assert "MARCADOR" not in resumo.erro
    assert conector.fechamentos == 1
    assert not any(tmp_path.rglob("*.gz"))


def test_registra_respostas_429(banco: Engine, tmp_path: Path) -> None:
    estatisticas = Estatisticas()
    conector = ConectorFalso(paginada=False, estatisticas=estatisticas)
    _orquestrador(banco, conector, tmp_path, estatisticas_http=estatisticas).executar(
        conector.planejar("TJPR", DIA - timedelta(days=1), DIA)
    )
    with banco.connect() as conexao:
        assert conexao.scalars(text("SELECT respostas_429 FROM caderno_djen")).all() == [2, 2]


# --- F1-10: retomada ----------------------------------------------------------------


@pytest.mark.parametrize("paginada", [False, True])
def test_unidade_concluida_e_pulada(banco: Engine, tmp_path: Path, paginada: bool) -> None:
    conector = ConectorFalso(paginada=paginada)
    unidades = conector.planejar("TJPR", DIA, DIA)
    orquestrador = _orquestrador(banco, conector, tmp_path)
    orquestrador.executar(unidades)
    chamadas = len(conector.chamadas)

    (resumo,) = orquestrador.executar(unidades)
    assert resumo.resultado is Resultado.PULADA
    assert len(conector.chamadas) == chamadas


@pytest.mark.parametrize("paginada", [False, True])
def test_forcar_reprocessa_do_zero_sem_duplicar_contagens(
    banco: Engine, tmp_path: Path, paginada: bool
) -> None:
    conector = ConectorFalso(paginada=paginada)
    unidades = conector.planejar("TJPR", DIA, DIA)
    orquestrador = _orquestrador(banco, conector, tmp_path)
    orquestrador.executar(unidades)
    (resumo,) = orquestrador.executar(unidades, forcar=True)

    assert resumo.resultado is Resultado.CONCLUIDA
    assert conector.chamadas[-1][1] == Checkpoint(None)
    tabela, coluna = (
        ("coleta_janela", "itens_aceitos") if paginada else ("caderno_djen", "acordaos_aceitos")
    )
    linha = _linha(banco, f"SELECT {coluna}, tentativas FROM {tabela}")  # noqa: S608
    assert linha[0] == (6 if paginada else 2)
    assert linha.tentativas == 2


def test_caderno_interrompido_e_reprocessado_inteiro(banco: Engine, tmp_path: Path) -> None:
    conector = ConectorFalso(
        paginada=False, interromper_em=(DIA, 0), interromper_depois_do_lote=True
    )
    unidades = conector.planejar("TJPR", DIA, DIA)
    with pytest.raises(Interrupcao):
        _orquestrador(banco, conector, tmp_path).executar(unidades)
    assert conector.fechamentos == 1
    caderno = _linha(banco, "SELECT status, acordaos_aceitos FROM caderno_djen")
    assert (caderno.status, caderno.acordaos_aceitos) == ("em_andamento", 2)

    conector.interromper_em = None
    (resumo,) = _orquestrador(banco, conector, tmp_path).executar(unidades)
    assert resumo.resultado is Resultado.CONCLUIDA
    assert conector.chamadas[-1][1] == Checkpoint(None)
    caderno = _linha(banco, "SELECT status, acordaos_aceitos, comunicacoes_lidas FROM caderno_djen")
    assert (caderno.status, caderno.acordaos_aceitos, caderno.comunicacoes_lidas) == (
        "processado",
        2,
        10,
    )


def test_janela_interrompida_continua_da_pagina_seguinte(banco: Engine, tmp_path: Path) -> None:
    conector = ConectorFalso(paginada=True, paginas=4, interromper_em=(DIA, 2))
    unidades = conector.planejar("TJDFT", DIA, DIA)
    with pytest.raises(Interrupcao):
        _orquestrador(banco, conector, tmp_path).executar(unidades)
    janela = _linha(banco, "SELECT status, ultima_pagina, itens_aceitos FROM coleta_janela")
    assert (janela.status, janela.ultima_pagina, janela.itens_aceitos) == ("em_andamento", 1, 4)

    conector.interromper_em = None
    (resumo,) = _orquestrador(banco, conector, tmp_path).executar(unidades)
    assert conector.chamadas[-1][1] == Checkpoint(ultima_pagina=1)
    assert resumo.lotes == 2
    janela = _linha(banco, "SELECT status, ultima_pagina, itens_aceitos FROM coleta_janela")
    assert (janela.status, janela.ultima_pagina, janela.itens_aceitos) == ("concluida", 3, 8)


def test_janela_com_erro_continua_da_pagina_seguinte(banco: Engine, tmp_path: Path) -> None:
    conector = ConectorFalso(paginada=True, paginas=3, falhar_em=(DIA, 1))
    unidades = conector.planejar("TJDFT", DIA, DIA)
    orquestrador = _orquestrador(banco, conector, tmp_path)
    (resumo,) = orquestrador.executar(unidades)
    assert resumo.resultado is Resultado.ERRO

    conector.falhar_em = None
    (resumo,) = orquestrador.executar(unidades)
    assert resumo.resultado is Resultado.CONCLUIDA
    assert conector.chamadas[-1][1] == Checkpoint(ultima_pagina=0)
    janela = _linha(banco, "SELECT ultima_pagina, itens_aceitos, ultimo_erro FROM coleta_janela")
    assert (janela.ultima_pagina, janela.itens_aceitos, janela.ultimo_erro) == (2, 6, None)
