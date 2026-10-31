"""F1-43 e F1-44: piloto local, só com dados sintéticos.

Os acórdãos "do piloto" aqui são sintéticos com processos de outro ano (2098), para provar que a
limpeza apaga tudo que não é dado sintético de desenvolvimento (processos de 2099).
"""

import argparse
import dataclasses
import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from busca.conftest import acordao as novo_acordao
from buscajus import cli, piloto
from buscajus.core.config import Config
from buscajus.ingest.conector import Contadores, UnidadeColeta
from buscajus.ingest.processo import digito_verificador
from buscajus.ingest.runner import Resultado, ResumoUnidade
from buscajus.ingest.upsert import upsert

# --- Pastas sincronizadas com nuvem --------------------------------------------------------


@pytest.mark.parametrize(
    "caminho",
    [
        "C:/Users/Fulano/OneDrive/git/buscajus",
        "C:/Users/Fulano/OneDrive - Empresa Exemplo/buscajus",
        "/home/fulano/Dropbox/buscajus",
        "G:/Meu Drive/buscajus",
        "/Users/fulano/Library/Mobile Documents/com~apple~CloudDocs/buscajus",
        "/home/fulano/Nextcloud/buscajus/ner-avaliacao-privado",
    ],
)
def test_pastas_na_nuvem_sao_recusadas(caminho: str) -> None:
    assert piloto.em_pasta_nuvem(Path(caminho), {}) is not None
    with pytest.raises(piloto.ErroPiloto, match="sincronizada"):
        piloto.conferir_pastas([Path(caminho)], {})


def test_pasta_do_onedrive_pela_variavel_de_ambiente(tmp_path: Path) -> None:
    raiz = tmp_path / "Documentos sincronizados"
    ambiente = {"OneDrive": str(raiz)}
    assert piloto.em_pasta_nuvem(raiz / "git" / "buscajus", ambiente)
    assert piloto.em_pasta_nuvem(tmp_path / "git" / "buscajus", ambiente) is None


def test_pasta_local_passa() -> None:
    piloto.conferir_pastas([Path("C:/git/buscajus"), Path("/home/fulano/git/buscajus")], {})


# --- Recusa fora do worker ------------------------------------------------------------------


def test_so_roda_no_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    config = Config()
    monkeypatch.setattr(piloto.sys, "platform", "linux")
    with pytest.raises(piloto.ErroPiloto, match="worker"):
        piloto.conferir_conteiner(config, {})
    piloto.conferir_conteiner(config, {piloto.VARIAVEL_CONTEINER: "1"})
    monkeypatch.setattr(piloto.sys, "platform", "win32")
    with pytest.raises(piloto.ErroPiloto, match="worker"):
        piloto.conferir_conteiner(config, {piloto.VARIAVEL_CONTEINER: "1"})


def test_recusa_banco_remoto_e_producao(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(piloto.sys, "platform", "linux")
    env = {piloto.VARIAVEL_CONTEINER: "1"}
    remoto = Config(database_url="postgresql+psycopg://u:segredo@banco.exemplo.invalid/b")
    with pytest.raises(piloto.ErroPiloto, match="banco local"):
        piloto.conferir_conteiner(remoto, env)
    producao = Config(ambiente="producao", database_url="postgresql+psycopg://u:s@db/b")
    with pytest.raises(piloto.ErroPiloto, match="produção"):
        piloto.conferir_conteiner(producao, env)


def test_carga_e_limpeza_recusam_fora_do_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(piloto.VARIAVEL_CONTEINER, raising=False)
    with pytest.raises(piloto.ErroPiloto):
        piloto.executar_carga(Config(), None, hoje=date(2026, 10, 30))  # type: ignore[arg-type]
    with pytest.raises(piloto.ErroPiloto):
        piloto.executar_limpeza(Config(), None)  # type: ignore[arg-type]


# --- Seleção dos dias -----------------------------------------------------------------------


def test_dias_uteis_anteriores() -> None:
    dias = piloto.dias_uteis_anteriores(date(2026, 10, 30), janela=10)  # sexta-feira
    assert dias[0] == date(2026, 10, 29)
    assert all(d.weekday() < 5 for d in dias)
    assert date(2026, 10, 25) not in dias  # domingo


def test_carrega_ate_achar_os_dias_com_dados() -> None:
    feriado = date(2026, 10, 28)

    def planejar(d: date) -> UnidadeColeta:
        return UnidadeColeta("djen", "TJPR", d, d, paginada=False)

    def executar(u: UnidadeColeta) -> ResumoUnidade:
        if u.data_inicio == feriado:
            return ResumoUnidade(u, Resultado.SEM_DADOS)
        return ResumoUnidade(u, Resultado.CONCLUIDA, Contadores(recebidos=10, aceitos=2))

    candidatos = piloto.dias_uteis_anteriores(date(2026, 10, 30))
    dias, resumos = piloto.carregar_dias(
        planejar, executar, candidatos, 5, lambda r: r.resultado == Resultado.CONCLUIDA
    )
    assert len(dias) == 5 and feriado.isoformat() not in dias
    assert len(resumos) == 6
    volumes = piloto.Volumes()
    for resumo in resumos:
        volumes.somar("djen", resumo)
    assert volumes.comunicacoes == 50 and volumes.ementas_aceitas == {"djen": 10}
    dados = piloto.volumes_dict(volumes)
    assert set(dados) >= {
        "comunicacoes_djen",
        "ementas_aceitas",
        "substituicoes_por_camada",
        "quarentena",
        "descartados_segredo_tjdft",
    }


# --- Limpeza (F1-44) ------------------------------------------------------------------------


def _do_piloto(i: int, fonte: str) -> object:
    """Acórdão sintético que faz as vezes de dado real do piloto: processo de 2098."""
    base = novo_acordao(f"piloto-{fonte}-{i}", f"Ementa do piloto {i}.", sequencial=i, fonte=fonte)
    tribunal = "07" if fonte == "tjdft" else "16"
    seq = f"{i:07d}"
    dv = digito_verificador(seq, "2098", "8", tribunal, "9999")
    return dataclasses.replace(
        base,
        numero_processo=f"{seq}{dv:02d}20988{tribunal}9999",
        numero_processo_mascara=f"{seq}-{dv:02d}.2098.8.{tribunal}.9999",
    )


def _contar(engine: Engine, tabela: str) -> int:
    with engine.connect() as conexao:
        return int(conexao.scalar(text(f"SELECT count(*) FROM {tabela}")) or 0)  # noqa: S608


def test_limpeza_apaga_tudo_do_piloto_e_mantem_o_sintetico(banco: Engine, tmp_path: Path) -> None:
    with banco.begin() as conexao:
        janela = conexao.scalar(
            text("""
                INSERT INTO coleta_janela (fonte, tribunal, data_inicio, data_fim, status)
                VALUES ('tjdft', 'TJDFT', '2026-10-29', '2026-10-29', 'concluida') RETURNING id
            """)
        )
        caderno = conexao.scalar(
            text("""
                INSERT INTO caderno_djen (tribunal, data, status)
                VALUES ('TJPR', '2026-10-29', 'processado') RETURNING id
            """)
        )
        bruta = conexao.scalar(
            text("""
                INSERT INTO coleta_bruta (fonte, coleta_janela_id, pagina, caminho_arquivo,
                    sha256, bytes, itens)
                VALUES ('tjdft', :j, 0, 'tjdft/TJDFT/2026-10-29/p0000.jsonl.gz', 'x', 1, 1)
                RETURNING id
            """),
            {"j": janela},
        )
        conexao.execute(text("INSERT INTO tarefa (tipo) VALUES ('tjdft_diario')"))
        for i in range(1, 4):
            for fonte in ("djen", "tjdft"):
                upsert(conexao, _do_piloto(i, fonte), coleta_bruta_id=bruta, cancelado=False)
        # Nova versão de um acórdão do piloto: gera histórico.
        alterado = dataclasses.replace(_do_piloto(1, "djen"), ementa="Ementa alterada.")
        upsert(conexao, alterado, coleta_bruta_id=bruta, cancelado=False)
        for i in range(1, 3):
            upsert(
                conexao,
                novo_acordao(f"sintetico-{i}", f"Ementa sintética {i}.", sequencial=500 + i),
                coleta_bruta_id=bruta,
                cancelado=False,
            )
        pedido = conexao.scalar(
            text("""
                INSERT INTO pedido_remocao (acordao_id, motivo, contato)
                SELECT id, 'teste', 'contato@exemplo.invalid' FROM acordao
                WHERE id_fonte = 'piloto-djen-2' RETURNING id
            """)
        )
        conexao.execute(
            text("""
                INSERT INTO bloqueio (fonte, id_fonte, motivo, pedido_remocao_id)
                VALUES ('djen', 'piloto-djen-3', 'teste', :p)
            """),
            {"p": pedido},
        )
        assert caderno is not None
    assert _contar(banco, "acordao_historico") == 1

    raw = tmp_path / "raw"
    (raw / "tjdft" / "TJDFT" / "2026-10-29").mkdir(parents=True)
    (raw / "tjdft" / "TJDFT" / "2026-10-29" / "p0000.jsonl.gz").write_bytes(b"x")
    (raw / "djen.jsonl.gz").write_bytes(b"x")

    contagens = piloto.limpar_banco(banco)
    assert piloto.limpar_diretorio(raw) == 2
    assert contagens["acordao"] == 6 and contagens["acordao_historico"] == 1
    assert contagens["pedido_remocao"] == 1 and contagens["bloqueio"] == 1

    with banco.connect() as conexao:
        restantes = conexao.scalars(text("SELECT id_fonte FROM acordao ORDER BY id_fonte")).all()
        processos = conexao.scalars(text("SELECT numero_processo FROM acordao")).all()
        tpu = conexao.scalar(text("SELECT count(*) FROM classe_cnj"))
    assert restantes == ["sintetico-1", "sintetico-2"]
    assert all(p[9:13] == "2099" for p in processos)
    for tabela in ("acordao_historico", "pedido_remocao", "bloqueio", *piloto.TABELAS_COLETA):
        assert _contar(banco, tabela) == 0, tabela
    assert tpu and tpu > 800
    assert raw.exists() and not any(raw.iterdir())


def _args(**kwargs: object) -> argparse.Namespace:
    return argparse.Namespace(**({"pasta_revisao": None, "sim": False} | kwargs))


def _repositorio(tmp_path: Path) -> Path:
    raiz = tmp_path / "repo"
    (raiz / "backend").mkdir(parents=True)
    (raiz / "compose.yaml").write_text("name: teste\n", encoding="utf-8")
    return raiz


def test_cli_limpar_pede_confirmacao_e_apaga_a_pasta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    raiz = _repositorio(tmp_path)
    pasta = raiz / "ner-avaliacao-privado"
    (pasta / "rodadas" / "01").mkdir(parents=True)
    (pasta / "amostra.jsonl").write_text("{}\n", encoding="utf-8")
    (pasta / "rodadas" / "01" / "respostas.jsonl").write_text("{}\n", encoding="utf-8")
    monkeypatch.chdir(raiz / "backend")
    chamadas: list[list[str]] = []

    def worker(r: Path, argumentos: list[str]) -> tuple[int, str]:
        assert r == raiz
        chamadas.append(argumentos)
        return 0, json.dumps({"acordao": 6})

    monkeypatch.setattr(piloto, "chamar_worker", worker)
    assert cli._piloto_limpar(_args(), ler=lambda _: "não") == 1
    assert pasta.exists() and not chamadas

    assert cli._piloto_limpar(_args(), ler=lambda _: "APAGAR") == 0
    assert chamadas == [["executar-limpeza"]]
    assert not pasta.exists()
    saida = json.loads(capsys.readouterr().out)
    assert saida == {"acordao": 6, "arquivos_pasta_revisao": 2}


def test_cli_carregar_recusa_repositorio_na_nuvem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raiz = _repositorio(tmp_path / "OneDrive")
    monkeypatch.chdir(raiz)
    monkeypatch.setattr(piloto, "chamar_worker", lambda *_: pytest.fail("não deveria chamar"))
    with pytest.raises(piloto.ErroPiloto, match="sincronizada"):
        cli._piloto_carregar(_args(dias_uteis=5))


def test_cli_carregar_chama_o_worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raiz = _repositorio(tmp_path)
    monkeypatch.chdir(raiz)
    chamadas: list[list[str]] = []
    monkeypatch.setattr(piloto, "chamar_worker", lambda r, a: (chamadas.append(a), (0, "{}\n"))[1])
    assert cli._piloto_carregar(_args(dias_uteis=5)) == 0
    assert chamadas == [["executar-carga", "--dias-uteis", "5"]]
    assert piloto.comando_worker("executar-carga")[:6] == [
        "docker",
        "compose",
        "run",
        "--rm",
        "-T",
        "worker",
    ]
