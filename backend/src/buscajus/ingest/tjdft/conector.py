"""Conector da API de jurisprudência do TJDFT (ARCHITECTURE.md, seção 3.3).

Unidade de coleta: um dia do filtro ``dataPublicacao`` (a API compara a data UTC), paginado
de 40 em 40 até ``hits.value``. Para cada dia:

1. lê **todas** as páginas, só em memória: em cada registro, descarta segredo de justiça e
   base diferente de ``acordaos`` (guardando só o uuid dos sigilosos, para o segredo
   superveniente), anonimiza os demais e aplica a lista branca;
2. confere a integridade da paginação: os uuids únicos de todos os registros recebidos
   (inclusive os descartados) têm de bater com ``hits.value``, e ``hits.value`` não pode
   mudar entre as páginas. Se divergir, refaz o dia inteiro, até ``tentativas_integridade``
   leituras, e então marca erro (F2-04);
3. só então devolve os lotes, um por página, a partir da página do checkpoint. Nada é gravado
   antes da conferência, e uma unidade retomada relê o dia inteiro para conferi-lo.

O conector não funciona sem um anonimizador: não há caminho que grave o texto sem ele.
"""

import logging
import math
from collections.abc import Callable, Iterator, Mapping
from datetime import date, timedelta
from typing import Any

from buscajus.core.config import ConfigTjdft
from buscajus.ingest.anonimizacao import Anonimizador, Rejeicao
from buscajus.ingest.bruto import caminho_pagina
from buscajus.ingest.conector import (
    Checkpoint,
    Contadores,
    ErroColeta,
    Fonte,
    LoteBruto,
    UnidadeColeta,
    UnidadeSemDados,
)
from buscajus.ingest.djen.conector import hoje_sao_paulo
from buscajus.ingest.http import ClienteHttp
from buscajus.ingest.tjdft.campos import (
    BASE,
    LISTA_BRANCA,
    Descarte,
    aplicar_lista_branca,
    descarte,
)

log = logging.getLogger(__name__)

TRIBUNAL = "TJDFT"


class _Divergencia(Exception):
    """A leitura do dia não bate com ``hits.value``; a mensagem só traz contagens."""


class ConectorTjdft:
    fonte: Fonte = "tjdft"
    lista_branca = LISTA_BRANCA

    def __init__(
        self,
        config: ConfigTjdft,
        cliente: ClienteHttp,
        anonimizar: Anonimizador,
        *,
        hoje: Callable[[], date] = hoje_sao_paulo,
    ) -> None:
        self._config = config
        self._cliente = cliente
        self._anonimizar = anonimizar
        self._hoje = hoje

    # --- F2-05 ---------------------------------------------------------------------

    def planejar(self, tribunal: str, inicio: date, fim: date) -> list[UnidadeColeta]:
        """Um dia de publicação por unidade, do mais recente ao mais antigo, até hoje."""
        if tribunal.strip().upper() != TRIBUNAL:
            raise ValueError(f"o conector do TJDFT só coleta {TRIBUNAL}")
        fim = min(fim, self._hoje())
        dias = (fim - inicio).days + 1
        return [
            UnidadeColeta("tjdft", TRIBUNAL, dia, dia, paginada=True)
            for dia in (fim - timedelta(days=i) for i in range(max(dias, 0)))
        ]

    # --- F2-04, F2-06 --------------------------------------------------------------

    def coletar(self, unidade: UnidadeColeta, checkpoint: Checkpoint) -> Iterator[LoteBruto]:
        dia = unidade.data_inicio
        tentativas = self._config.tentativas_integridade
        ultima: _Divergencia | None = None
        for tentativa in range(1, tentativas + 1):
            try:
                lotes = self._ler_dia(dia)
            except _Divergencia as divergencia:
                log.warning(
                    "paginação do TJDFT inconsistente, relendo o dia",
                    extra={
                        "unidade": unidade.descricao,
                        "tentativa": tentativa,
                        "motivo": str(divergencia),
                    },
                )
                ultima = divergencia
                continue
            if not lotes:
                raise UnidadeSemDados
            yield from (lote for lote in lotes if (lote.pagina or 0) >= checkpoint.proxima_pagina)
            return
        raise ErroColeta(f"paginação inconsistente após {tentativas} leituras do dia: {ultima}")

    def _ler_dia(self, dia: date) -> list[LoteBruto]:
        """Lê e filtra todas as páginas do dia; levanta ``_Divergencia`` se não fechar."""
        tamanho = self._config.tamanho_pagina
        primeira = self._pagina(dia, 0)
        total = primeira["hits"]["value"]
        paginas = max(math.ceil(total / tamanho), 1)
        uuids: set[str] = set()
        recebidos = 0
        lotes: list[LoteBruto] = []
        for numero in range(paginas):
            resposta = primeira if numero == 0 else self._pagina(dia, numero)
            if resposta["hits"]["value"] != total:
                raise _Divergencia(
                    f"hits.value mudou entre as páginas ({total} → {resposta['hits']['value']})"
                )
            registros = resposta["registros"]
            if total and not registros:
                raise _Divergencia(f"página {numero} vazia antes do fim ({total} registros)")
            recebidos += len(registros)
            uuids.update(r["uuid"] for r in registros if isinstance(r.get("uuid"), str))
            if total:
                lotes.append(self._lote(dia, numero, registros, total))
        if len(uuids) != total or recebidos != total:
            raise _Divergencia(
                f"{len(uuids)} uuids únicos em {recebidos} registros; hits.value = {total}"
            )
        return lotes

    def _lote(
        self, dia: date, numero: int, registros: list[Mapping[str, Any]], total: int
    ) -> LoteBruto:
        contadores = Contadores()
        itens: list[dict[str, Any]] = []
        ids_segredo: list[str] = []
        for registro in registros:
            contadores.recebidos += 1
            motivo = descarte(registro)
            if motivo is not None:
                # Descartado em memória, antes de qualquer gravação: nada é logado.
                contadores.descartados += 1
                if motivo is Descarte.SEGREDO:
                    contadores.segredo += 1
                    if isinstance(registro.get("uuid"), str):
                        ids_segredo.append(registro["uuid"])
                continue
            resultado = self._anonimizar(registro)
            if isinstance(resultado, Rejeicao):
                contadores.rejeitados_anonimizacao.append(resultado.id_comunicacao)
                continue
            itens.append(aplicar_lista_branca(resultado))
            contadores.aceitos += 1
        return LoteBruto(
            itens=itens,
            caminho_bruto=caminho_pagina("tjdft", TRIBUNAL, dia, numero),
            contadores=contadores,
            pagina=numero,
            total_fonte=total,
            ids_segredo=ids_segredo,
        )

    def _pagina(self, dia: date, numero: int) -> dict[str, Any]:
        resposta = self._cliente.requisitar(
            "POST",
            self._config.url_api,
            rotulo="pesquisa do TJDFT",
            json={
                "query": "",
                "pagina": numero,
                "tamanho": self._config.tamanho_pagina,
                "termosAcessorios": [
                    {"campo": "base", "valor": BASE},
                    {"campo": "dataPublicacao", "valor": dia.isoformat()},
                ],
            },
        )
        if resposta.status_code != 200:
            raise ErroColeta(f"pesquisa do TJDFT: HTTP {resposta.status_code}")
        try:
            corpo = resposta.json()
        except ValueError:
            raise ErroColeta("pesquisa do TJDFT: resposta não é JSON") from None
        if not _formato_valido(corpo):
            raise ErroColeta("pesquisa do TJDFT: resposta fora do formato esperado")
        conteudo: dict[str, Any] = corpo
        return conteudo


def _formato_valido(corpo: Any) -> bool:
    if not isinstance(corpo, dict):
        return False
    hits, registros = corpo.get("hits"), corpo.get("registros")
    return (
        isinstance(hits, dict)
        and isinstance(hits.get("value"), int)
        and not isinstance(hits.get("value"), bool)
        and hits["value"] >= 0
        and isinstance(registros, list)
        and all(isinstance(r, dict) for r in registros)
    )
