"""F1-42: revisão por amostra, com acórdãos sintéticos (processos de 2099, nomes fictícios)."""

import dataclasses
import json
import random
from collections import Counter
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from busca.conftest import acordao as novo_acordao
from buscajus import revisao
from buscajus.ingest.anonimizacao.camada2 import Entidade
from buscajus.ingest.anonimizacao.nomes import trechos_protegidos
from buscajus.ingest.modelos import AcordaoNormalizado
from buscajus.ingest.upsert import upsert

VERSAO = "c1-1+cpf-1+doc-1+ner-teste"
NOME_VAZADO = "Clotilde Ravanello"


def _sintetico(i: int, fonte: str, orgao: str, versao: str = VERSAO) -> AcordaoNormalizado:
    ementa = f"EMENTA SINTÉTICA {i}. Apelação. Recurso desprovido."
    if i == 1:
        ementa = f"EMENTA SINTÉTICA 1. A vítima {NOME_VAZADO} relatou os fatos. RG nº 12.345.678-9."
    base = novo_acordao(f"rev-{i}", ementa, sequencial=1000 + i, fonte=fonte, orgao=orgao)
    return dataclasses.replace(base, anonimizacao_versao=versao)


ORGAOS = {
    "djen": ["1ª Câmara Criminal", "12ª Câmara Cível", "5ª Câmara Cível"],
    "tjdft": ["1ª Turma Criminal", "3ª Turma Cível"],
}


@pytest.fixture
def acordaos(banco: Engine) -> Iterator[Engine]:
    with banco.begin() as conexao:
        i = 1
        for fonte, orgaos in ORGAOS.items():
            for orgao in orgaos:
                for _ in range(30):
                    upsert(
                        conexao,
                        _sintetico(i, fonte, orgao),
                        coleta_bruta_id=None,
                        cancelado=False,
                    )
                    i += 1
    yield banco


class TerminalFalso:
    def __init__(self, respostas: Sequence[str]) -> None:
        self.respostas = list(respostas)
        self.saida: list[str] = []

    def ler(self, _prompt: str) -> str:
        return self.respostas.pop(0)

    def escrever(self, texto: str) -> None:
        self.saida.append(texto)

    @property
    def terminal(self) -> revisao.Terminal:
        return revisao.Terminal(ler=self.ler, escrever=self.escrever, largura=80)


def test_estratos() -> None:
    assert revisao.estrato("TJPR", "3ª Câmara Criminal") == "criminal"
    assert revisao.estrato("TJPR", "12ª Câmara Cível") == "familia"
    assert revisao.estrato("TJPR", "5ª Câmara Cível") == "civel"
    assert revisao.estrato("TJDFT", "1ª Turma Criminal") == "criminal"
    assert revisao.estrato("TJDFT", "12ª Câmara Cível") == "civel"


def test_sorteio_estratificado() -> None:
    candidatos = [
        revisao.Candidato(i, tribunal, estrato)
        for i, (tribunal, estrato) in enumerate(
            [("TJPR", "criminal")] * 200
            + [("TJPR", "familia")] * 200
            + [("TJPR", "civel")] * 200
            + [("TJDFT", "criminal")] * 200
            + [("TJDFT", "civel")] * 200
        )
    ]
    amostra = revisao.sortear(candidatos, 100, 0.2, random.Random(1))  # noqa: S311
    contagem = Counter((c.tribunal, c.estrato) for c in amostra)
    assert len(amostra) == len({c.acordao_id for c in amostra}) == 100
    assert contagem == {
        ("TJPR", "criminal"): 40,
        ("TJPR", "familia"): 20,
        ("TJPR", "civel"): 20,
        ("TJDFT", "criminal"): 10,
        ("TJDFT", "civel"): 10,
    }


def test_estrato_curto_cede_a_cota() -> None:
    candidatos = [revisao.Candidato(i, "TJPR", "criminal") for i in range(10)]
    candidatos += [revisao.Candidato(100 + i, "TJPR", "civel") for i in range(200)]
    amostra = revisao.sortear(candidatos, 100, 0.2, random.Random(1))  # noqa: S311
    contagem = Counter(c.estrato for c in amostra)
    assert len(amostra) == 100 and contagem["criminal"] == 10


def test_limite_superior() -> None:
    assert revisao.limite_superior(0, 100) == pytest.approx(1 - 0.05 ** (1 / 100), abs=1e-6)
    assert revisao.limite_superior(0, 100) == pytest.approx(0.0295, abs=1e-4)
    assert revisao.limite_superior(1, 100) == pytest.approx(0.0466, abs=1e-3)
    assert revisao.limite_superior(0, 30) == pytest.approx(0.0950, abs=1e-3)
    assert revisao.limite_superior(0, 0) == 1.0


def _situacao(engine: Engine, id_fonte: str) -> tuple[str, str | None]:
    with engine.connect() as conexao:
        linha = conexao.execute(
            text("SELECT situacao::text, motivo_situacao FROM acordao WHERE id_fonte = :i"),
            {"i": id_fonte},
        ).one()
    return linha[0], linha[1]


def test_fluxo_completo(acordaos: Engine, tmp_path: Path) -> None:
    pasta = tmp_path / revisao.NOME_PASTA
    resumo = revisao.amostrar(acordaos, pasta, n=100, semente=7)
    assert resumo["amostra"] == 100
    estratos = resumo["por_estrato"]
    # Só há 30 criminais no TJPR: a sobra da cota vai para os outros estratos do TJPR.
    assert estratos["TJPR/criminal"] == 30
    assert estratos["TJPR/familia"] + estratos["TJPR/civel"] == 50
    assert min(estratos["TJPR/familia"], estratos["TJPR/civel"]) >= 20
    assert estratos["TJDFT/criminal"] == estratos["TJDFT/civel"] == 10
    amostra = revisao.ler_amostra(pasta)
    with pytest.raises(revisao.ErroRevisao, match="nova-rodada"):
        revisao.amostrar(acordaos, pasta, n=100)

    # Todos os criminais do TJPR entram, inclusive o do nome vazado; ele vai para o começo.
    alvo = next(r for r in amostra if "Clotilde" in r["ementa"])
    amostra.remove(alvo)
    amostra.insert(0, alvo)
    (pasta / revisao.AMOSTRA).write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in amostra), encoding="utf-8"
    )

    # Primeira sessão: "vazou" (com um trecho que não existe e depois o certo), ok, sair.
    term = TerminalFalso(["v", "Fulano Inexistente", NOME_VAZADO.upper(), "o", "x", "s"])
    sessao = revisao.revisar(acordaos, pasta, term.terminal)
    assert sessao == {"ok": 1, "vazou": 1, "restantes": 98}
    assert any("não foi encontrado" in linha for linha in term.saida)
    situacao, motivo = _situacao(acordaos, "rev-1")
    assert situacao == "quarentena" and motivo and VERSAO in motivo

    # Recoleta com as mesmas regras não libera; com regras corrigidas (outra versão), libera.
    with acordaos.begin() as conexao:
        upsert(
            conexao, _sintetico(1, "djen", ORGAOS["djen"][0]), coleta_bruta_id=None, cancelado=False
        )
    assert _situacao(acordaos, "rev-1")[0] == "quarentena"

    # Segunda sessão continua de onde parou.
    term = TerminalFalso(["ok"] * 98)
    assert revisao.revisar(acordaos, pasta, term.terminal) == {
        "ok": 98,
        "vazou": 0,
        "restantes": 0,
    }

    relatorio = tmp_path / "revisao-anonimizacao.md"
    resultado = revisao.resultado(pasta, relatorio)
    assert resultado["revisadas"] == 100 and resultado["vazamentos"] == 1
    assert resultado["situacao"].startswith("reprovada")
    conteudo = relatorio.read_text(encoding="utf-8")
    assert "| 1 |" in conteudo
    # Só agregados: nada das ementas, do trecho nem dos ids.
    for proibido in ("Clotilde", "CLOTILDE", "Ravanello", "SINTÉTICA", "rev-", "r001", "12.345"):
        assert proibido not in conteudo

    # Regras corrigidas: um detector que pega o nome; o verificar só devolve contagens.
    class Detector:
        versao = "corrigido"

        def detectar(self, texto: str) -> list[Entidade]:
            return [Entidade(a, b) for a, b in trechos_protegidos(texto, [NOME_VAZADO])]

    class SemNer:
        versao = "nada"

        def detectar(self, texto: str) -> list[Entidade]:
            return []

    assert revisao.verificar(pasta, Detector()) == {"trechos": 1, "pegos": 1, "escapam": 0}
    assert revisao.verificar(pasta, SemNer()) == {"trechos": 1, "pegos": 0, "escapam": 1}

    with acordaos.begin() as conexao:
        corrigido = _sintetico(1, "djen", ORGAOS["djen"][0], versao=VERSAO + "-2")
        upsert(conexao, corrigido, coleta_bruta_id=None, cancelado=False)
    assert _situacao(acordaos, "rev-1")[0] == "ativo"

    # Nova rodada: arquiva a anterior e não repete acórdãos já revisados.
    nova = revisao.amostrar(acordaos, pasta, n=30, nova_rodada=True, semente=3)
    assert nova["amostra"] == 30
    ids_antigos = {r["acordao_id"] for r in amostra}
    assert not ids_antigos & {r["acordao_id"] for r in revisao.ler_amostra(pasta)}
    assert (pasta / revisao.RODADAS / "01" / revisao.RESPOSTAS).exists()
    # Os trechos da rodada arquivada continuam valendo para o verificar.
    assert revisao.verificar(pasta, SemNer())["trechos"] == 1


def test_aprovacao_com_zero_vazamentos(tmp_path: Path) -> None:
    pasta = revisao.preparar_pasta(tmp_path / "p")
    amostra = [
        {
            "id_amostra": f"r{i:03d}",
            "acordao_id": i,
            "tribunal": "TJPR",
            "estrato": "civel",
            "anonimizacao_versao": VERSAO,
            "ementa": "x",
        }
        for i in range(1, 101)
    ]
    (pasta / revisao.AMOSTRA).write_text(
        "".join(json.dumps(r) + "\n" for r in amostra), encoding="utf-8"
    )
    (pasta / revisao.RESPOSTAS).write_text(
        "".join(
            json.dumps({"id_amostra": r["id_amostra"], "resultado": "ok"}) + "\n" for r in amostra
        ),
        encoding="utf-8",
    )
    resultado = revisao.resultado(pasta, None)
    assert resultado["situacao"] == "aprovada: 0 vazamentos"
    assert resultado["limite_superior_95"] == pytest.approx(0.0295, abs=1e-4)
    parcial = revisao.resultado(pasta, None, meta=200)
    assert parcial["situacao"].startswith("incompleta")


def test_sem_amostra(tmp_path: Path) -> None:
    with pytest.raises(revisao.ErroRevisao, match="amostrar"):
        revisao.ler_amostra(tmp_path)
