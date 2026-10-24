"""Checagem pontual de uma comunicação via ``GET /api/v1/comunicacao`` (F1-17).

Só para conferir o estado de uma comunicação específica: a que sumiu numa nova versão do
caderno ou a de um pedido de remoção. **Nunca** para coleta em massa. Da resposta só se
leem ``ativo``, ``status`` e ``data_cancelamento``; ela não é gravada nem logada.

Filtros (confirmados no F1-01): ``numeroProcesso`` (20 dígitos) + ``siglaTribunal`` +
``dataDisponibilizacaoInicio`` = ``dataDisponibilizacaoFim`` = data do caderno devolvem um
resultado, conferido pelo ``id``. ``numeroComunicacao`` não serve: não é único. O endpoint
tem janela de ~20 requisições (``x-ratelimit-remaining``); o cliente pausa ao chegar a zero.
"""

from dataclasses import dataclass
from datetime import date

import httpx

from buscajus.ingest.conector import ErroColeta
from buscajus.ingest.djen.campos import EstadoFonte, RegraEstado
from buscajus.ingest.http import ClienteHttp


@dataclass(frozen=True)
class EstadoComunicacao:
    encontrada: bool
    ativo: bool | None = None
    status: str | None = None
    data_cancelamento: str | None = None

    def estado(self, regra: RegraEstado) -> EstadoFonte:
        """Não encontrada conta como cancelada (ARCHITECTURE.md, seção 3.2)."""
        if not self.encontrada:
            return EstadoFonte.CANCELADA
        return regra.classificar(
            {
                "ativo": self.ativo,
                "status": self.status,
                "data_cancelamento": self.data_cancelamento,
            }
        )


def checar_comunicacao(
    cliente: ClienteHttp,
    url_api: str,
    *,
    tribunal: str,
    numero_processo: str,
    data_disponibilizacao: date,
    id_comunicacao: str,
) -> EstadoComunicacao:
    """Procura a comunicação pelo processo e pela data e a identifica pelo ``id``."""
    resposta = cliente.requisitar(
        "GET",
        f"{url_api}/api/v1/comunicacao",
        rotulo="checagem pontual de comunicação",
        params={
            "siglaTribunal": tribunal,
            "numeroProcesso": "".join(c for c in numero_processo if c.isdigit()),
            "dataDisponibilizacaoInicio": data_disponibilizacao.isoformat(),
            "dataDisponibilizacaoFim": data_disponibilizacao.isoformat(),
        },
    )
    if resposta.status_code == httpx.codes.NOT_FOUND:
        return EstadoComunicacao(encontrada=False)
    if resposta.status_code != httpx.codes.OK:
        raise ErroColeta(f"checagem pontual de comunicação: HTTP {resposta.status_code}")
    try:
        corpo = resposta.json()
    except ValueError as exc:
        raise ErroColeta("checagem pontual: resposta não é JSON") from exc
    itens = corpo.get("items") if isinstance(corpo, dict) else None
    for item in itens if isinstance(itens, list) else []:
        if isinstance(item, dict) and str(item.get("id")) == str(id_comunicacao):
            ativo = item.get("ativo")
            status = item.get("status")
            cancelamento = item.get("data_cancelamento")
            return EstadoComunicacao(
                encontrada=True,
                ativo=ativo if isinstance(ativo, bool) else None,
                status=status if isinstance(status, str) else None,
                data_cancelamento=str(cancelamento) if cancelamento not in (None, "") else None,
            )
    return EstadoComunicacao(encontrada=False)
