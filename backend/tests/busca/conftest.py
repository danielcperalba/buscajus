"""Acórdãos sintéticos inseridos direto no banco de teste, e a API sobre eles.

Nenhum dado real: relatores com nomes genéricos, processos do ano 2099 (origem 9999), ementas
escritas para os testes.
"""

from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from buscajus.api import app as modulo_app
from buscajus.api.limite import LimitadorJanela
from buscajus.busca.servico import ServicoPostgres
from buscajus.ingest.modelos import AcordaoNormalizado
from buscajus.ingest.processo import digito_verificador
from buscajus.ingest.relator import normalizar_relator
from buscajus.ingest.upsert import upsert


def numero(sequencial: int, tribunal: str = "07") -> tuple[str, str]:
    seq = f"{sequencial:07d}"
    dv = digito_verificador(seq, "2099", "8", tribunal, "9999")
    return f"{seq}{dv:02d}20998{tribunal}9999", f"{seq}-{dv:02d}.2099.8.{tribunal}.9999"


def acordao(
    id_fonte: str,
    ementa: str,
    *,
    sequencial: int = 1,
    fonte: str = "tjdft",
    relator: str = "Fulano de Tal",
    designado: str | None = None,
    orgao: str = "3ª Turma Cível",
    classe: tuple[int, str] = (198, "Apelação Cível"),
    julgamento: date | None = date(2026, 10, 8),
    publicacao: date | None = date(2026, 10, 21),
) -> AcordaoNormalizado:
    tribunal = "TJDFT" if fonte == "tjdft" else "TJPR"
    digitos, mascara = numero(sequencial, "07" if fonte == "tjdft" else "16")
    rel = normalizar_relator(relator)
    des = normalizar_relator(designado)
    return AcordaoNormalizado(
        fonte=fonte,  # type: ignore[arg-type]
        id_fonte=id_fonte,
        tribunal=tribunal,
        numero_processo=digitos,
        numero_processo_mascara=mascara,
        numero_processo_valido=True,
        ementa=ementa,
        link_oficial=f"https://exemplo.invalid/{id_fonte}",
        orgao_julgador=orgao,
        classe_codigo_cnj=classe[0],
        classe_nome=classe[1],
        classe_citacao=classe[1],
        relator=rel.exibicao if rel else None,
        relator_chave=rel.chave if rel else None,
        relator_designado=des.exibicao if des else None,
        relator_designado_chave=des.chave if des else None,
        data_julgamento=julgamento,
        data_publicacao=publicacao if fonte == "tjdft" else None,
        data_disponibilizacao=publicacao if fonte == "djen" else None,
        local_publicacao="PJe" if fonte == "tjdft" else None,
        decisao="CONHECIDO. DESPROVIDO. UNÂNIME." if fonte == "tjdft" else None,
        possui_inteiro_teor=True if fonte == "tjdft" else None,
    )


ACORDAOS = {
    "heranca": acordao(
        "u-heranca",
        "DIREITO CIVIL. INVENTÁRIO. PARTILHA DA HERANÇA ENTRE OS HERDEIROS. Sucessão.",
        sequencial=10,
        julgamento=date(2026, 10, 8),
    ),
    "heranca_embargos": acordao(
        "u-heranca-ed",
        "EMBARGOS DE DECLARAÇÃO. Herança. Omissão inexistente.",
        sequencial=10,  # mesmo processo, julgado depois
        classe=(1689, "Embargos de Declaração Cível"),
        julgamento=date(2026, 10, 15),
    ),
    "companheira": acordao(
        "u-companheira",
        "DIREITO CIVIL. UNIÃO ESTÁVEL. Direito da companheira à herança. Testamento.",
        sequencial=11,
        relator="Sicrano de Tal",
        designado="Beltrana de Tal",
        orgao="6ª Turma Cível",
        julgamento=date(2026, 9, 1),
    ),
    "tjpr_partilha": acordao(
        "900001",
        "RECURSO INOMINADO. Partilha de bens. <script>x</script> Sentença mantida.",
        fonte="djen",
        sequencial=12,
        orgao="3ª Turma Recursal",
        classe=(460, "Recurso Inominado Cível"),
        julgamento=None,
        publicacao=date(2026, 10, 14),
    ),
    "plano": acordao(
        "u-plano",
        "DIREITO DO CONSUMIDOR. PLANO DE SAÚDE. NEGATIVA DE COBERTURA. Dano moral.",
        sequencial=13,
    ),
    "cancelado": acordao("u-cancelado", "HERANÇA cancelada na fonte.", sequencial=14),
    "removido": acordao("u-removido", "HERANÇA removida a pedido.", sequencial=15),
    "quarentena": acordao("u-quarentena", "HERANÇA em quarentena.", sequencial=16),
    "duplicado": acordao("u-duplicado", "HERANÇA duplicada.", sequencial=17),
}


@pytest.fixture
def ids(banco: Engine) -> dict[str, int]:
    with banco.begin() as conexao:
        for nome, item in ACORDAOS.items():
            upsert(
                conexao,
                item,
                coleta_bruta_id=None,
                cancelado=nome == "cancelado",
                motivos_pii=["email"] if nome == "quarentena" else (),
            )
        for nome in ("removido", "duplicado"):
            conexao.execute(
                text(
                    "UPDATE acordao SET situacao = CAST(:s AS situacao_acordao) WHERE id_fonte = :i"
                ),
                {"s": nome, "i": ACORDAOS[nome].id_fonte},
            )
        linhas = conexao.execute(text("SELECT id_fonte, id FROM acordao")).all()
    por_fonte = dict(linhas)  # type: ignore[arg-type]
    return {nome: por_fonte[item.id_fonte] for nome, item in ACORDAOS.items()}


def inserir(banco: Engine, *itens: AcordaoNormalizado) -> None:
    with banco.begin() as conexao:
        for item in itens:
            upsert(conexao, item, coleta_bruta_id=None, cancelado=False)


@pytest.fixture
def cliente(banco: Engine) -> Iterator[TestClient]:
    app = modulo_app.criar_app()
    app.state.servico = ServicoPostgres(banco, app.state.config.busca)
    app.state.limitadores = {
        "consulta": LimitadorJanela(10_000, 60),
        "remocao": LimitadorJanela(10_000, 3600),
    }
    with TestClient(app) as cliente:
        yield cliente
