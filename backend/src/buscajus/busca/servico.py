"""Serviço da busca sobre o Postgres (F4-03, F4-08, F4-09, F4-11, F4-12).

- ``buscar``: consulta que é só um número de processo → busca exata (ou por prefixo), do mais
  recente ao mais antigo (F4-03); senão, busca híbrida: ramo full-text e ramo vetorial (este
  desligado até o F3-06) fundidos por RRF, até 200 resultados, páginas de 20 (F4-08). Um número
  junto com outros termos vira filtro. Cada resultado traz o trecho destacado, a citação e o
  aviso de reprodução.
- ``detalhe``: só ``ativo``; ``cancelado`` e ``removido`` → 410; o resto (inexistente,
  quarentena, duplicado) → 404 (F4-09).
- ``processo``: acórdãos ativos de um número completo ou de um prefixo (limitado).
- ``filtros`` (com cache) e ``relatores`` (trigrama sobre ``relator_chave``) (F4-11).
- ``registrar_remocao``: grava ``pedido_remocao``; a decisão é do comando administrativo
  (``busca.pedidos``) (F4-12).
"""

import re
import time
from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import Connection, Engine, text

from buscajus.api.consulta import ConsultaAnalisada, NumeroNaConsulta, analisar_consulta
from buscajus.api.esquemas import (
    LIMITE_RESULTADOS,
    POR_PAGINA,
    AcordaosDoProcesso,
    Classe,
    CoberturaTribunal,
    DetalheAcordao,
    Filtros,
    FiltrosBusca,
    Indisponivel,
    OpcaoFiltro,
    PedidoRemocao,
    Relator,
    RemocaoRecebida,
    RespostaBusca,
    ResultadoBusca,
    SituacaoAcordao,
)
from buscajus.api.servico import ErroApi
from buscajus.busca.citacao import citar
from buscajus.busca.filtros import condicoes
from buscajus.busca.fusao import pagina, rrf
from buscajus.busca.texto import destaques, inicio_da_ementa, ramo_texto
from buscajus.busca.vetorial import RamoVetorial, RamoVetorialDesligado
from buscajus.core.config import ConfigBusca
from buscajus.ingest.fontes import FONTES
from buscajus.ingest.texto import chave

COLUNAS = """
    a.id, a.fonte::text AS fonte, a.tribunal, a.numero_processo, a.numero_processo_mascara,
    a.orgao_julgador, a.classe_codigo_cnj, a.classe_nome, a.classe_citacao, a.relator,
    a.relator_designado, a.turma_recursal, a.data_julgamento, a.data_publicacao,
    a.data_disponibilizacao, a.local_publicacao, a.link_oficial, a.link_tribunal, a.ementa,
    a.decisao, a.possui_inteiro_teor, a.situacao::text AS situacao
"""
ORDEM_DATA = "a.data_referencia DESC NULLS LAST, a.id DESC"
# Link de um resultado: página de detalhe do site ou rota da API.
_LINK_ACORDAO = re.compile(r"/acordaos?/(\d+)(?:\D|$)")


def _campos(linha: Mapping[str, Any]) -> dict[str, Any]:
    """Campos comuns de ``Acordao`` a partir de uma linha de ``acordao``."""
    return {
        "id": linha["id"],
        "fonte": linha["fonte"],
        "tribunal": linha["tribunal"],
        "numero_processo": linha["numero_processo_mascara"],
        "orgao_julgador": linha["orgao_julgador"],
        "classe": Classe(codigo=linha["classe_codigo_cnj"], nome=linha["classe_nome"]),
        "relator": linha["relator"],
        "relator_designado": linha["relator_designado"],
        "turma_recursal": linha["turma_recursal"],
        "data_julgamento": linha["data_julgamento"],
        "data_publicacao": linha["data_publicacao"],
        "data_disponibilizacao": linha["data_disponibilizacao"],
        "link_oficial": linha["link_oficial"],
        "link_tribunal": linha["link_tribunal"],
        "citacao": citar(linha),
    }


class ServicoPostgres:
    def __init__(
        self,
        engine: Engine,
        config: ConfigBusca | None = None,
        *,
        ramo_vetorial: RamoVetorial | None = None,
    ) -> None:
        self._engine = engine
        self._config = config or ConfigBusca()
        self._vetorial = ramo_vetorial or RamoVetorialDesligado()
        self._cache_filtros: tuple[float, Filtros] | None = None

    # --- /busca (F4-08) ------------------------------------------------------------

    def buscar(
        self, consulta: ConsultaAnalisada, filtros: FiltrosBusca, numero_pagina: int
    ) -> RespostaBusca:
        with self._engine.connect() as conexao:
            if consulta.tipo == "processo" and consulta.numero is not None:
                ids = self._ids_do_processo(conexao, consulta.numero, filtros, LIMITE_RESULTADOS)
            else:
                ids = self._ids_hibridos(conexao, consulta, filtros)
            ids_pagina = pagina(ids, numero_pagina, POR_PAGINA)
            linhas = self._linhas(conexao, ids_pagina)
            trechos = destaques(conexao, consulta.texto, ids_pagina) if consulta.texto else {}
        numero = consulta.numero
        return RespostaBusca(
            consulta=consulta.original,
            tipo=consulta.tipo,
            numero_processo=(numero.mascara or numero.digitos) if numero else None,
            filtros=filtros,
            pagina=numero_pagina,
            total=len(ids),
            resultados=[
                self._resultado(linhas[i], trechos.get(i)) for i in ids_pagina if i in linhas
            ],
        )

    def _ids_hibridos(
        self, conexao: Connection, consulta: ConsultaAnalisada, filtros: FiltrosBusca
    ) -> list[int]:
        top = self._config.top_ramo
        rankings = {
            "texto": [
                i
                for i, _ in ramo_texto(
                    conexao, consulta.texto, filtros, consulta.numero, limite=top
                )
            ]
        }
        if self._vetorial.disponivel:
            vetor = self._vetorial.buscar(
                conexao, consulta.texto, filtros, consulta.numero, limite=top
            )
            rankings["vetor"] = [i for i, _ in vetor]
        pesos = {"texto": self._config.peso_texto, "vetor": self._config.peso_vetor}
        fundidos = rrf(rankings, pesos, k=self._config.rrf_k, limite=LIMITE_RESULTADOS)
        return [i for i, _ in fundidos]

    def _ids_do_processo(
        self,
        conexao: Connection,
        numero: NumeroNaConsulta,
        filtros: FiltrosBusca,
        limite: int,
    ) -> list[int]:
        """Busca exata (ou por prefixo, limitada), do acórdão mais recente ao mais antigo."""
        onde, parametros = condicoes(filtros, numero)
        if not numero.completo:
            limite = min(limite, self._config.limite_prefixo)
        return list(
            conexao.scalars(
                text(
                    f"SELECT a.id FROM acordao a WHERE {onde} ORDER BY {ORDEM_DATA} LIMIT :limite"  # noqa: S608
                ),
                parametros | {"limite": limite},
            )
        )

    def _linhas(self, conexao: Connection, ids: Iterable[int]) -> dict[int, Mapping[str, Any]]:
        lista = list(ids)
        if not lista:
            return {}
        resultado = conexao.execute(
            text(
                f"SELECT {COLUNAS} FROM acordao a WHERE a.id = ANY(:ids) AND a.situacao = 'ativo'"  # noqa: S608
            ),
            {"ids": lista},
        )
        return {linha.id: dict(linha._mapping) for linha in resultado}

    @staticmethod
    def _resultado(linha: Mapping[str, Any], trecho: str | None) -> ResultadoBusca:
        return ResultadoBusca(**_campos(linha), trecho=trecho or inicio_da_ementa(linha["ementa"]))

    # --- /acordaos/{id} (F4-09) ----------------------------------------------------

    def detalhe(self, acordao_id: int) -> DetalheAcordao | Indisponivel | None:
        with self._engine.connect() as conexao:
            linha = conexao.execute(
                text(f"SELECT {COLUNAS} FROM acordao a WHERE a.id = :id"),  # noqa: S608
                {"id": acordao_id},
            ).one_or_none()
        if linha is None:
            return None
        dados = dict(linha._mapping)
        if dados["situacao"] == "cancelado":
            return Indisponivel(
                erro="cancelado",
                mensagem="A publicação deste acórdão foi cancelada na fonte oficial.",
                link_oficial=dados["link_oficial"],
            )
        if dados["situacao"] == "removido":
            return Indisponivel(erro="removido", mensagem="Este acórdão foi removido.")
        if dados["situacao"] != "ativo":
            return None  # quarentena e duplicado não são exibidos
        return DetalheAcordao(
            **_campos(dados),
            ementa=dados["ementa"],
            decisao=dados["decisao"],
            possui_inteiro_teor=dados["possui_inteiro_teor"],
        )

    def situacao(self, acordao_id: int) -> SituacaoAcordao | None:
        with self._engine.connect() as conexao:
            situacao = conexao.scalar(
                text("SELECT situacao::text FROM acordao WHERE id = :id"), {"id": acordao_id}
            )
        if situacao in ("ativo", "cancelado", "removido"):
            return SituacaoAcordao(situacao=situacao)
        return None  # inexistente, quarentena ou duplicado

    # --- /processos/{numero} (F4-03) -----------------------------------------------

    def processo(self, digitos: str) -> AcordaosDoProcesso | None:
        numero = NumeroNaConsulta(digitos, completo=len(digitos) == 20)
        with self._engine.connect() as conexao:
            ids = self._ids_do_processo(conexao, numero, FiltrosBusca(), LIMITE_RESULTADOS)
            linhas = self._linhas(conexao, ids)
        if not ids:
            return None
        acordaos = [self._resultado(linhas[i], None) for i in ids if i in linhas]
        rotulo = acordaos[0].numero_processo if numero.completo else digitos
        return AcordaosDoProcesso(numero_processo=rotulo, acordaos=acordaos)

    # --- /filtros e /relatores (F4-11) ---------------------------------------------

    def filtros(self) -> Filtros:
        agora = time.monotonic()
        if self._cache_filtros is not None:
            momento, guardado = self._cache_filtros
            if agora - momento < self._config.cache_filtros_segundos:
                return guardado
        with self._engine.connect() as conexao:
            filtros = Filtros(
                tribunais=_opcoes(conexao, "tribunal", "tribunal"),
                orgaos=_opcoes(conexao, "orgao_julgador", "orgao_julgador"),
                classes=_opcoes(conexao, "classe_codigo_cnj", "max(classe_nome)"),
            )
        self._cache_filtros = (agora, filtros)
        return filtros

    def cobertura(self) -> list[CoberturaTribunal]:
        """Cobertura por fonte e tribunal, só dos acórdãos exibíveis (F7-04)."""
        with self._engine.connect() as conexao:
            linhas = conexao.execute(
                text("""
                    SELECT fonte::text AS fonte, tribunal, count(*) AS acordaos,
                        min(data_referencia) AS desde, max(data_referencia) AS ate
                    FROM acordao WHERE situacao = 'ativo'
                    GROUP BY fonte, tribunal ORDER BY tribunal, fonte
                """)
            ).all()
        return [
            CoberturaTribunal(
                fonte=linha.fonte,
                fonte_nome=FONTES[linha.fonte].nome,
                fonte_url=FONTES[linha.fonte].url,
                tribunal=linha.tribunal,
                acordaos=linha.acordaos,
                desde=linha.desde,
                ate=linha.ate,
            )
            for linha in linhas
        ]

    def relatores(self, prefixo: str, limite: int = 10) -> list[Relator]:
        alvo = chave(prefixo)
        with self._engine.connect() as conexao:
            linhas = conexao.execute(
                text("""
                    SELECT relator_chave AS chave, max(relator) AS nome
                    FROM acordao
                    WHERE situacao = 'ativo' AND relator_chave LIKE :padrao
                    GROUP BY relator_chave
                    ORDER BY (relator_chave LIKE :inicio) DESC,
                        similarity(relator_chave, :alvo) DESC, relator_chave
                    LIMIT :limite
                """),
                {
                    "padrao": f"%{_escapar_like(alvo)}%",
                    "inicio": f"{_escapar_like(alvo)}%",
                    "alvo": alvo,
                    "limite": limite,
                },
            ).all()
        return [Relator(nome=linha.nome, chave=linha.chave) for linha in linhas]

    # --- /remocao (F4-12) ----------------------------------------------------------

    def registrar_remocao(self, pedido: PedidoRemocao) -> RemocaoRecebida:
        acordao_id, numero = self._referencia(pedido.referencia)
        with self._engine.begin() as conexao:
            if acordao_id is not None and not conexao.scalar(
                text("SELECT EXISTS (SELECT 1 FROM acordao WHERE id = :id)"), {"id": acordao_id}
            ):
                raise ErroApi(422, "referencia_invalida", "acórdão não encontrado")
            protocolo = conexao.execute(
                text("""
                    INSERT INTO pedido_remocao (acordao_id, numero_processo, motivo, contato)
                    VALUES (:acordao_id, :numero, :motivo, :contato)
                    RETURNING id
                """),
                {
                    "acordao_id": acordao_id,
                    "numero": numero,
                    "motivo": pedido.motivo,
                    "contato": pedido.email,
                },
            ).scalar_one()
        return RemocaoRecebida(
            protocolo=protocolo,
            status="pendente",
            mensagem="Pedido recebido. A resposta será enviada ao e-mail informado.",
        )

    @staticmethod
    def _referencia(referencia: str) -> tuple[int | None, str | None]:
        link = _LINK_ACORDAO.search(referencia)
        if link:
            return int(link.group(1)), None
        numero = analisar_consulta(referencia).numero
        if numero is not None and numero.completo:
            return None, numero.digitos
        raise ErroApi(
            422,
            "referencia_invalida",
            "informe o número completo do processo ou o link do resultado",
        )


def _opcoes(conexao: Connection, valor: str, rotulo: str) -> list[OpcaoFiltro]:
    """Valores de um filtro entre os acórdãos ativos, com o total de cada um."""
    linhas = conexao.execute(
        text(f"""
            SELECT {valor} AS valor, {rotulo} AS rotulo, count(*) AS total
            FROM acordao WHERE situacao = 'ativo' AND {valor} IS NOT NULL
            GROUP BY {valor} ORDER BY 2, 1
        """)  # noqa: S608 (interpola só expressões fixas deste módulo)
    ).all()
    return [
        OpcaoFiltro(
            valor=str(linha.valor), rotulo=str(linha.rotulo or linha.valor), total=linha.total
        )
        for linha in linhas
    ]


def _escapar_like(valor: str) -> str:
    return valor.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
