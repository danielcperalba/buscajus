"""Conector do DJEN por caderno diário (ARCHITECTURE.md, seção 3.2).

Fluxo de uma unidade (tribunal + dia):

1. metadados do caderno: 404 → sem caderno (ou não pronto, se o dia ainda não acabou);
   ``status`` diferente de "Processado" → não pronto, sem comunicações ou erro;
2. download em streaming para a área temporária, com limite de tamanho;
3. SHA-256 contra ``hash``; se divergir, apaga e repete com metadados novos (a URL vale
   5 minutos), até ``tentativas_hash``;
4. leitura do ZIP: comunicações que não são ementa de acórdão são descartadas em memória,
   sem log; as aceitas vão para o anonimizador ainda com os destinatários, que só existem
   em memória; a quantidade lida é conferida com ``total_comunicacoes``;
5. o ZIP é apagado antes de o lote seguir adiante, e de novo no ``finally``.

O conector não funciona sem um anonimizador: não há caminho que grave o texto sem ele.
"""

import logging
from collections.abc import Callable, Iterator
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from buscajus.core.config import ConfigDjen
from buscajus.ingest import temporario
from buscajus.ingest.anonimizacao import Anonimizador, Rejeicao
from buscajus.ingest.bruto import caminho_caderno
from buscajus.ingest.conector import (
    Checkpoint,
    Contadores,
    ErroColeta,
    Fonte,
    LoteBruto,
    MetadadosCaderno,
    UnidadeColeta,
    UnidadeNaoPronta,
    UnidadeSemDados,
)
from buscajus.ingest.djen import caderno
from buscajus.ingest.djen.campos import LISTA_BRANCA, tipo_aceito
from buscajus.ingest.djen.normalizacao import normalizar
from buscajus.ingest.http import ClienteHttp

log = logging.getLogger(__name__)

FUSO = ZoneInfo("America/Sao_Paulo")


def hoje_sao_paulo() -> date:
    return datetime.now(FUSO).date()


class ConectorDjen:
    fonte: Fonte = "djen"
    lista_branca = LISTA_BRANCA
    normalizar = staticmethod(normalizar)

    def __init__(
        self,
        config: ConfigDjen,
        cliente: ClienteHttp,
        anonimizar: Anonimizador,
        diretorio_tmp: Path,
        *,
        hoje: Callable[[], date] = hoje_sao_paulo,
    ) -> None:
        self._config = config
        self._cliente = cliente
        self._anonimizar = anonimizar
        self._diretorio_tmp = diretorio_tmp
        self._hoje = hoje

    # --- F1-11 ---------------------------------------------------------------------

    def planejar(self, tribunal: str, inicio: date, fim: date) -> list[UnidadeColeta]:
        """Um caderno por dia, do mais recente ao mais antigo.

        Não passa da data de início das ementas do tribunal nem de hoje. Dias sem caderno
        (fins de semana, feriados) entram no plano e viram ``sem_caderno`` na coleta.
        """
        tribunal = tribunal.strip().upper()
        if tribunal not in self._config.tribunais:
            raise ValueError(f"tribunal {tribunal} não está em djen.tribunais")
        inicio = max(inicio, self._config.inicio_ementas[tribunal])
        fim = min(fim, self._hoje())
        dias = (fim - inicio).days + 1
        return [
            UnidadeColeta("djen", tribunal, dia, dia, paginada=False)
            for dia in (fim - timedelta(days=i) for i in range(max(dias, 0)))
        ]

    # --- F1-12 a F1-15 -------------------------------------------------------------

    def coletar(self, unidade: UnidadeColeta, checkpoint: Checkpoint) -> Iterator[LoteBruto]:
        tribunal, data = unidade.tribunal, unidade.data_inicio
        for tentativa in range(1, self._config.tentativas_hash + 1):
            meta = self._metadados_prontos(tribunal, data)
            arquivo = temporario.novo_arquivo(self._diretorio_tmp, f"{tribunal}-{data}")
            try:
                tamanho = self._cliente.baixar(
                    meta.url,
                    arquivo,
                    rotulo="download do caderno",
                    limite_bytes=self._config.limite_bytes_caderno,
                )
                if tamanho > self._config.alerta_bytes_caderno:
                    log.warning(
                        "caderno acima do tamanho de alerta",
                        extra={"unidade": unidade.descricao, "bytes": tamanho},
                    )
                if caderno.sha256_arquivo(arquivo) != meta.hash:
                    log.warning(
                        "SHA-256 do caderno não confere com os metadados",
                        extra={"unidade": unidade.descricao, "tentativa": tentativa},
                    )
                    continue
                itens, contadores = self._ler(arquivo, meta)
            finally:
                arquivo.unlink(missing_ok=True)
            yield LoteBruto(
                itens=itens,
                caminho_bruto=caminho_caderno(tribunal, data, meta.versao),
                contadores=contadores,
                total_fonte=meta.total,
                caderno=MetadadosCaderno(versao=meta.versao, hash=meta.hash, bytes=tamanho),
            )
            return
        raise ErroColeta(
            f"SHA-256 do caderno não confere após {self._config.tentativas_hash} downloads"
        )

    def _metadados_prontos(self, tribunal: str, data: date) -> caderno.MetadadosDjen:
        meta = caderno.obter_metadados(self._cliente, self._config.url_api, tribunal, data)
        if meta is None:
            # O caderno do dia corrente pode ainda não ter sido publicado.
            if data >= self._hoje():
                raise UnidadeNaoPronta
            raise UnidadeSemDados
        if meta.status in caderno.STATUS_NAO_PRONTO:
            raise UnidadeNaoPronta
        if meta.status == caderno.STATUS_SEM_COMUNICACOES:
            raise UnidadeSemDados
        if meta.status != caderno.STATUS_PRONTO:
            # "Cancelado" ou valor desconhecido: precisa de olho humano.
            raise ErroColeta(f"caderno com status {meta.status!r}")
        if not meta.url:
            raise ErroColeta("metadados do caderno sem URL do arquivo")
        return meta

    def _ler(
        self, arquivo: Path, meta: caderno.MetadadosDjen
    ) -> tuple[list[dict[str, object]], Contadores]:
        contadores = Contadores()
        itens: list[dict[str, object]] = []
        for comunicacao in caderno.ler_comunicacoes(arquivo):
            contadores.recebidos += 1
            if not tipo_aceito(comunicacao, self._config.tipos_documento_aceitos):
                # Descartada em memória: nada é gravado nem logado.
                contadores.descartados += 1
                continue
            resultado = self._anonimizar(comunicacao)
            if isinstance(resultado, Rejeicao):
                contadores.rejeitados_anonimizacao.append(resultado.id_comunicacao)
                continue
            itens.append(resultado)
            contadores.aceitos += 1
        if meta.total is not None and contadores.recebidos != meta.total:
            raise ErroColeta(
                f"caderno com {contadores.recebidos} comunicações; os metadados indicam "
                f"{meta.total}"
            )
        return itens, contadores
