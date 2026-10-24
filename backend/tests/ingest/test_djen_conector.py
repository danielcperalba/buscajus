"""Conector DJEN por caderno (F1-11 a F1-15) com as fixtures sintéticas."""

import gzip
import hashlib
import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import Engine, text

from buscajus.core.config import Config, ConfigHttp
from buscajus.ingest import temporario
from buscajus.ingest.bruto import ArmazenamentoBruto
from buscajus.ingest.conector import (
    Checkpoint,
    ErroColeta,
    UnidadeColeta,
    UnidadeNaoPronta,
    UnidadeSemDados,
)
from buscajus.ingest.djen.campos import LISTA_BRANCA, comunicacao_cancelada, tipo_aceito
from buscajus.ingest.djen.conector import ConectorDjen
from buscajus.ingest.http import ClienteHttp, RespostaGrandeDemais
from buscajus.ingest.runner import Orquestrador, Resultado
from buscajus.worker import preparar
from fixtures.djen import PASTA, dados

from .conftest import RelogioFalso
from .djen_ajuda import (
    DIA,
    DIA_SEM_EMENTAS,
    HOJE,
    AnonimizadorFalso,
    area_vazia,
    config_djen,
    ler_json,
    resposta_429,
    servir_caderno,
    url_metadados,
)


@pytest.fixture
def tmp_cadernos(tmp_path: Path) -> Path:
    return tmp_path / "tmp-cadernos"


@pytest.fixture
def cliente(relogio: RelogioFalso) -> ClienteHttp:
    return ClienteHttp(ConfigHttp(), 1.0, relogio=relogio)


@pytest.fixture
def anonimizador() -> AnonimizadorFalso:
    return AnonimizadorFalso()


def _conector(
    cliente: ClienteHttp, anonimizador: AnonimizadorFalso, tmp: Path, **config: Any
) -> ConectorDjen:
    return ConectorDjen(config_djen(**config), cliente, anonimizador, tmp, hoje=lambda: HOJE)


def _unidade(dia: date = DIA) -> UnidadeColeta:
    return UnidadeColeta("djen", "TJPR", dia, dia, paginada=False)


@pytest.fixture
def conector(
    cliente: ClienteHttp, anonimizador: AnonimizadorFalso, tmp_cadernos: Path
) -> ConectorDjen:
    return _conector(cliente, anonimizador, tmp_cadernos)


# --- Campos ---------------------------------------------------------------------------


def test_tipo_documento_comparado_depois_do_parse() -> None:
    item = json.loads('{"tipoDocumento": "Ementa de Ac\\u00f3rd\\u00e3o"}')
    assert tipo_aceito(item, ["Ementa de Acórdão"])
    assert tipo_aceito({"tipoDocumento": " ementa de  acórdão "}, ["Ementa de Acórdão"])
    assert not tipo_aceito({"tipoDocumento": "Acórdão"}, ["Ementa de Acórdão"])
    assert not tipo_aceito({"tipoDocumento": None}, ["Ementa de Acórdão"])


@pytest.mark.parametrize(
    ("item", "esperado"),
    [
        ({"ativo": True, "status": "P", "data_cancelamento": None}, False),
        ({"ativo": False, "status": "P", "data_cancelamento": None}, True),
        ({"ativo": True, "status": "P", "data_cancelamento": "2026-10-16T09:30:00"}, True),
        ({"ativo": True, "status": "C", "data_cancelamento": None}, True),
        ({"ativo": True, "status": "P", "data_cancelamento": ""}, False),
    ],
)
def test_cancelamento(item: dict[str, Any], esperado: bool) -> None:
    assert comunicacao_cancelada(item, ["C"]) is esperado


def test_lista_branca_nao_tem_dados_de_partes() -> None:
    assert not {"destinatarios", "destinatarioadvogados", "motivo_cancelamento"} & LISTA_BRANCA


# --- F1-11: planejamento ---------------------------------------------------------------


def test_planeja_90_dias_do_mais_recente_ao_mais_antigo(conector: ConectorDjen) -> None:
    unidades = conector.planejar("tjpr", HOJE - timedelta(days=89), HOJE)
    assert len(unidades) == 90
    assert unidades[0].data_inicio == HOJE
    assert unidades[-1].data_inicio == HOJE - timedelta(days=89)
    assert all(u.data_inicio == u.data_fim and not u.paginada for u in unidades)
    assert {u.tribunal for u in unidades} == {"TJPR"}


def test_planejamento_nao_passa_do_inicio_das_ementas_nem_de_hoje(
    conector: ConectorDjen,
) -> None:
    unidades = conector.planejar("TJPR", date(2025, 7, 1), date(2025, 7, 25))
    assert [u.data_inicio for u in unidades][-1] == date(2025, 7, 23)
    assert len(unidades) == 3
    assert conector.planejar("TJPR", HOJE, HOJE + timedelta(days=5))[0].data_inicio == HOJE
    assert conector.planejar("TJPR", date(2025, 1, 1), date(2025, 7, 22)) == []


def test_planejamento_exige_tribunal_configurado(conector: ConectorDjen) -> None:
    with pytest.raises(ValueError, match="TJSC"):
        conector.planejar("TJSC", DIA, DIA)


# --- F1-12: metadados e download --------------------------------------------------------


@respx.mock
def test_coleta_um_caderno(
    conector: ConectorDjen, anonimizador: AnonimizadorFalso, tmp_cadernos: Path
) -> None:
    servir_caderno(respx.mock, DIA)
    (lote,) = list(conector.coletar(_unidade(), Checkpoint()))

    assert lote.caminho_bruto == "djen/TJPR/2026-10-15/v1.jsonl.gz"
    assert lote.caderno is not None
    assert lote.caderno.versao == 1
    assert lote.total_fonte == 26
    c = lote.contadores
    assert (c.recebidos, c.aceitos, c.descartados) == (26, 20, 6)
    assert len(lote.itens) == 20
    assert all(set(item) <= LISTA_BRANCA for item in lote.itens)
    assert sorted(anonimizador.vistos) == sorted(e.id for e in dados.EMENTAS)
    assert area_vazia(tmp_cadernos)


@respx.mock
def test_dia_sem_caderno(conector: ConectorDjen) -> None:
    respx.get(url_metadados(DIA)).respond(404)
    with pytest.raises(UnidadeSemDados):
        list(conector.coletar(_unidade(), Checkpoint()))


@respx.mock
def test_404_no_dia_corrente_e_nao_pronto(conector: ConectorDjen) -> None:
    respx.get(url_metadados(HOJE)).respond(404)
    with pytest.raises(UnidadeNaoPronta):
        list(conector.coletar(_unidade(HOJE), Checkpoint()))


@respx.mock
@pytest.mark.parametrize(
    ("status", "excecao"),
    [
        ("Em processamento", UnidadeNaoPronta),
        ("Não Processado", UnidadeNaoPronta),
        ("Sem comunicações", UnidadeSemDados),
        ("Cancelado", ErroColeta),
        ("Desconhecido", ErroColeta),
    ],
)
def test_status_do_caderno(
    conector: ConectorDjen, tmp_cadernos: Path, status: str, excecao: type[Exception]
) -> None:
    meta = ler_json(f"metadados-{dados.DATA}-v1.json") | {"status": status}
    respx.get(url_metadados(DIA)).respond(200, json=meta)
    zip_ = respx.get(meta["url"]).respond(200, content=b"x")
    with pytest.raises(excecao):
        list(conector.coletar(_unidade(), Checkpoint()))
    assert not zip_.called
    assert area_vazia(tmp_cadernos)


@respx.mock
def test_metadados_invalidos(conector: ConectorDjen) -> None:
    respx.get(url_metadados(DIA)).respond(200, json={"status": "Processado"})
    with pytest.raises(ErroColeta, match="versao"):
        list(conector.coletar(_unidade(), Checkpoint()))


@respx.mock
def test_download_acima_do_limite(
    cliente: ClienteHttp, anonimizador: AnonimizadorFalso, tmp_cadernos: Path
) -> None:
    servir_caderno(respx.mock, DIA)
    conector = _conector(cliente, anonimizador, tmp_cadernos, limite_bytes_caderno=1000)
    with pytest.raises(RespostaGrandeDemais, match="limite"):
        list(conector.coletar(_unidade(), Checkpoint()))
    assert area_vazia(tmp_cadernos)


@respx.mock
def test_429_nos_metadados(conector: ConectorDjen, relogio: RelogioFalso) -> None:
    meta = ler_json(f"metadados-{dados.DATA}-v1.json")
    respx.get(url_metadados(DIA)).mock(side_effect=[resposta_429(), httpx.Response(200, json=meta)])
    respx.get(meta["url"]).respond(
        200,
        content=(
            Path(__file__).parents[1] / "fixtures/djen/caderno-2026-10-15-v1.zip"
        ).read_bytes(),
    )
    (lote,) = list(conector.coletar(_unidade(), Checkpoint()))
    assert lote.contadores.aceitos == 20
    assert 60.0 in relogio.esperas


# --- F1-13: SHA-256 -------------------------------------------------------------------


@respx.mock
def test_hash_divergente_tenta_de_novo_com_metadados_novos(
    conector: ConectorDjen, tmp_cadernos: Path
) -> None:
    errado = ler_json(f"metadados-{dados.DATA}-v1-hash-incorreto.json")
    certo = ler_json(f"metadados-{dados.DATA}-v1.json")
    metadados = respx.get(url_metadados(DIA)).mock(
        side_effect=[httpx.Response(200, json=errado), httpx.Response(200, json=certo)]
    )
    conteudo = (PASTA / "caderno-2026-10-15-v1.zip").read_bytes()
    zip_ = respx.get(certo["url"]).respond(200, content=conteudo)

    (lote,) = list(conector.coletar(_unidade(), Checkpoint()))
    assert lote.contadores.aceitos == 20
    assert (metadados.call_count, zip_.call_count) == (2, 2)
    assert area_vazia(tmp_cadernos)


@respx.mock
def test_hash_sempre_divergente_vira_erro(
    conector: ConectorDjen, anonimizador: AnonimizadorFalso, tmp_cadernos: Path
) -> None:
    zip_ = servir_caderno(
        respx.mock, DIA, metadados=f"metadados-{dados.DATA}-v1-hash-incorreto.json"
    )
    with pytest.raises(ErroColeta, match="SHA-256 do caderno não confere após 3 downloads"):
        list(conector.coletar(_unidade(), Checkpoint()))
    assert zip_.call_count == 3
    assert anonimizador.vistos == []
    assert area_vazia(tmp_cadernos)


# --- F1-14: leitura e filtro ----------------------------------------------------------


@respx.mock
def test_total_divergente_vira_erro(conector: ConectorDjen, tmp_cadernos: Path) -> None:
    meta = ler_json(f"metadados-{dados.DATA}-v1.json") | {"total_comunicacoes": 27}
    respx.get(url_metadados(DIA)).respond(200, json=meta)
    respx.get(meta["url"]).respond(
        200,
        content=(
            Path(__file__).parents[1] / "fixtures/djen/caderno-2026-10-15-v1.zip"
        ).read_bytes(),
    )
    with pytest.raises(ErroColeta, match="26 comunicações; os metadados indicam 27"):
        list(conector.coletar(_unidade(), Checkpoint()))
    assert area_vazia(tmp_cadernos)


@respx.mock
def test_rejeicao_da_anonimizacao_guarda_so_o_id(cliente: ClienteHttp, tmp_cadernos: Path) -> None:
    servir_caderno(respx.mock, DIA)
    anonimizador = AnonimizadorFalso(rejeitar={900002})
    (lote,) = list(_conector(cliente, anonimizador, tmp_cadernos).coletar(_unidade(), Checkpoint()))
    assert lote.contadores.rejeitados_anonimizacao == ["900002"]
    assert lote.contadores.aceitos == 19
    assert 900002 not in {item["id"] for item in lote.itens}


@respx.mock
def test_zip_que_nao_e_zip(conector: ConectorDjen, tmp_cadernos: Path) -> None:
    lixo = b"isto nao e um zip"
    meta = ler_json(f"metadados-{dados.DATA}-v1.json") | {"hash": hashlib.sha256(lixo).hexdigest()}
    respx.get(url_metadados(DIA)).respond(200, json=meta)
    respx.get(meta["url"]).respond(200, content=lixo)
    with pytest.raises(ErroColeta, match="não é um ZIP"):
        list(conector.coletar(_unidade(), Checkpoint()))
    assert area_vazia(tmp_cadernos)


# --- Ponta a ponta com o orquestrador (banco) -----------------------------------------


@pytest.fixture
def orquestrador_djen(
    banco: Engine, conector: ConectorDjen, cliente: ClienteHttp, tmp_path: Path
) -> Orquestrador:
    return Orquestrador(
        banco,
        conector,
        ArmazenamentoBruto(tmp_path / "raw"),
        estatisticas_http=cliente.estatisticas,
        versao_parser="teste",
    )


@pytest.mark.banco
@respx.mock
def test_ponta_a_ponta_sem_rastro_das_descartadas(
    orquestrador_djen: Orquestrador,
    conector: ConectorDjen,
    banco: Engine,
    tmp_path: Path,
    tmp_cadernos: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    servir_caderno(respx.mock, DIA)
    servir_caderno(respx.mock, DIA_SEM_EMENTAS)
    respx.get(url_metadados(DIA + timedelta(days=1))).respond(404)

    unidades = conector.planejar("TJPR", DIA, DIA_SEM_EMENTAS)
    resumos = orquestrador_djen.executar(unidades)
    assert [r.resultado for r in resumos] == [
        Resultado.CONCLUIDA,
        Resultado.SEM_DADOS,
        Resultado.CONCLUIDA,
    ]
    with banco.connect() as conexao:
        cadernos = {
            linha.data: linha for linha in conexao.execute(text("SELECT * FROM caderno_djen")).all()
        }
        brutos = conexao.scalar(text("SELECT count(*) FROM coleta_bruta"))
        colunas = " ".join(
            str(valor)
            for linha in conexao.execute(text("SELECT * FROM caderno_djen"))
            for valor in linha
        )
    assert cadernos[DIA].status == "processado"
    assert (cadernos[DIA].comunicacoes_lidas, cadernos[DIA].acordaos_aceitos) == (26, 20)
    assert (cadernos[DIA].versao, cadernos[DIA].total_fonte) == (1, 26)
    assert cadernos[DIA + timedelta(days=1)].status == "sem_caderno"
    assert cadernos[DIA_SEM_EMENTAS].status == "processado"
    assert cadernos[DIA_SEM_EMENTAS].acordaos_aceitos == 0
    assert brutos == 2

    # Nenhum marcador das comunicações descartadas no bruto, no banco ou nos logs; a URL
    # temporária também não aparece em lugar nenhum.
    arquivos = b"".join(p.read_bytes() for p in (tmp_path / "raw").rglob("*.gz"))
    conteudo_bruto = b"".join(
        gzip.decompress(p.read_bytes()) for p in (tmp_path / "raw").rglob("*.gz")
    ).decode()
    assert arquivos
    logs = "\n".join(f"{r.getMessage()} {vars(r)}" for r in caplog.records)
    for texto_ in (conteudo_bruto, colunas, logs):
        assert dados.MARCADOR_DESCARTADO not in texto_.upper().replace("Á", "A")
        assert "X-Amz" not in texto_
        assert "s3.cnj.jus.br" not in texto_
    assert area_vazia(tmp_cadernos)


@pytest.mark.banco
@respx.mock
def test_hash_divergente_marca_erro_no_banco(
    orquestrador_djen: Orquestrador, banco: Engine
) -> None:
    servir_caderno(respx.mock, DIA, metadados=f"metadados-{dados.DATA}-v1-hash-incorreto.json")
    (resumo,) = orquestrador_djen.executar([_unidade()])
    assert resumo.resultado is Resultado.ERRO
    with banco.connect() as conexao:
        linha = conexao.execute(text("SELECT status, ultimo_erro FROM caderno_djen")).one()
    assert linha.status == "erro"
    assert "SHA-256" in linha.ultimo_erro


# --- F1-15: descarte garantido do ZIP -----------------------------------------------


@respx.mock
def test_area_vazia_apos_excecao_no_processamento(cliente: ClienteHttp, tmp_cadernos: Path) -> None:
    servir_caderno(respx.mock, DIA)
    anonimizador = AnonimizadorFalso(falhar_em=900005)
    with pytest.raises(RuntimeError):
        list(_conector(cliente, anonimizador, tmp_cadernos).coletar(_unidade(), Checkpoint()))
    assert area_vazia(tmp_cadernos)


@pytest.mark.banco
@respx.mock
def test_area_vazia_apos_erro_no_orquestrador(
    banco: Engine, cliente: ClienteHttp, tmp_cadernos: Path, tmp_path: Path
) -> None:
    servir_caderno(respx.mock, DIA)

    def vaza_destinatarios(item: Any) -> dict[str, Any]:
        return dict(item)  # sem lista branca: o bruto recusa a gravação

    conector = ConectorDjen(
        config_djen(), cliente, vaza_destinatarios, tmp_cadernos, hoje=lambda: HOJE
    )
    (resumo,) = Orquestrador(banco, conector, ArmazenamentoBruto(tmp_path / "raw")).executar(
        [_unidade()]
    )
    assert resumo.resultado is Resultado.ERRO
    assert resumo.erro is not None and "destinatarios" in resumo.erro
    assert area_vazia(tmp_cadernos)
    assert not list((tmp_path / "raw").rglob("*.gz"))


def test_worker_apaga_orfaos_ao_iniciar(tmp_path: Path) -> None:
    area = tmp_path / "tmp-cadernos"
    area.mkdir()
    (area / "TJPR-2026-10-15-orfao.zip").write_bytes(b"caderno interrompido")
    (area / "subdir").mkdir()
    preparar(Config(diretorio_tmp_cadernos=area))
    assert area.exists()
    assert area_vazia(area)


def test_area_temporaria_criada_com_permissao_restrita(tmp_path: Path) -> None:
    caminho = temporario.novo_arquivo(tmp_path / "nova", "TJPR")
    assert caminho.parent.stat().st_mode & 0o777 == 0o700
    assert not caminho.exists()
