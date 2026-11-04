"""Serviço de mock da API (``api.mock = true``): dados sintéticos fixos, no formato do contrato.

Para o frontend (Fase 5) trabalhar antes da busca real. Nada aqui é real: magistrados com
nomes genéricos ("Fulano de Tal"), processos do ano 2099 e ementas escritas para o exemplo. A
"busca" só conta palavras em comum, sem acento; não tem relação com a busca híbrida real.
"""

import html
import math
import re
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import count

from buscajus.api.consulta import ConsultaAnalisada
from buscajus.api.esquemas import (
    LIMITE_RECENTES,
    LIMITE_RESULTADOS,
    POR_PAGINA,
    POR_PAGINA_RECENTES,
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
    RespostaRecentes,
    ResultadoBusca,
    SituacaoAcordao,
)
from buscajus.ingest.fontes import FONTES
from buscajus.ingest.processo import digito_verificador
from buscajus.ingest.texto import chave


def _numero(sequencial: int, tribunal: str, origem: str = "9999") -> str:
    seq = f"{sequencial:07d}"
    dv = digito_verificador(seq, "2099", "8", tribunal, origem)
    return f"{seq}-{dv:02d}.2099.8.{tribunal}.{origem}"


@dataclass(frozen=True)
class _Exemplo:
    detalhe: DetalheAcordao

    @property
    def digitos(self) -> str:
        return re.sub(r"\D", "", self.detalhe.numero_processo)

    @property
    def data_referencia(self) -> date | None:
        d = self.detalhe
        return d.data_julgamento or d.data_publicacao or d.data_disponibilizacao


_TJPR = _numero(11412, "16")
_TJDFT_1 = _numero(1234, "07")
_TJDFT_2 = _numero(5678, "07")

EXEMPLOS = (
    _Exemplo(
        DetalheAcordao(
            id=1,
            fonte="djen",
            tribunal="TJPR",
            numero_processo=_TJPR,
            orgao_julgador="3ª Turma Recursal dos Juizados Especiais",
            classe=Classe(codigo=460, nome="Recurso Inominado Cível"),
            relator="Fulano de Tal",
            relator_designado=None,
            turma_recursal=True,
            data_julgamento=date(2026, 10, 6),
            data_publicacao=None,
            data_disponibilizacao=date(2026, 10, 14),
            link_oficial="https://comunicaapi.pje.jus.br/api/v1/comunicacao/exemplo1/certidao",
            link_tribunal=None,
            citacao=(
                "TJPR, 3ª Turma Recursal dos Juizados Especiais, Recurso Inominado Cível "
                f"nº {_TJPR}, Rel. Fulano de Tal, j. 06/10/2026, DJEN de 14/10/2026."
            ),
            ementa=(
                "RECURSO INOMINADO. TRANSPORTE AÉREO. CANCELAMENTO DE VOO SEM ASSISTÊNCIA "
                "MATERIAL. DANO MORAL CONFIGURADO. Sentença mantida. Recurso desprovido."
            ),
            decisao=None,
            possui_inteiro_teor=None,
        )
    ),
    _Exemplo(
        DetalheAcordao(
            id=2,
            fonte="tjdft",
            tribunal="TJDFT",
            numero_processo=_TJDFT_1,
            orgao_julgador="3ª Turma Cível",
            classe=Classe(codigo=198, nome="Apelação Cível"),
            relator="Beltrano de Tal",
            relator_designado=None,
            turma_recursal=False,
            data_julgamento=date(2026, 10, 8),
            data_publicacao=date(2026, 10, 21),
            data_disponibilizacao=None,
            link_oficial="https://jurisdf.tjdft.jus.br/acordaos/00000000-2099-4000-8000-000000000002",
            link_tribunal=None,
            citacao=(
                f"TJDFT, 3ª Turma Cível, Apelação Cível nº {_TJDFT_1}, Rel. Beltrano de Tal, "
                "j. 08/10/2026, publ. PJe 21/10/2026."
            ),
            ementa=(
                # Modelo do CNJ (Recomendação 154/2024), para exibir tópicos e itens (F5-15).
                "DIREITO CIVIL. APELAÇÃO CÍVEL. INVENTÁRIO. PARTILHA DA HERANÇA ENTRE OS "
                "HERDEIROS. Imóvel da família. Sucessão. Recurso conhecido e desprovido.\n"
                "I. CASO EM EXAME\n"
                "1. Apelação contra sentença que homologou a partilha do imóvel da família.\n"
                "II. QUESTÃO EM DISCUSSÃO\n"
                "2. A questão consiste em saber se o imóvel integra o espólio.\n"
                "III. RAZÕES DE DECIDIR\n"
                "3. O imóvel foi adquirido antes do casamento, nos termos do art. 1.661 do CC.\n"
                "4. A sentença observou a ordem de vocação hereditária.\n"
                "IV. DISPOSITIVO E TESE\n"
                "5. Recurso conhecido e desprovido.\n"
                "Tese de julgamento: O bem adquirido antes do casamento não se comunica.\n"
                "Dispositivos relevantes citados: CC, art. 1.661."
            ),
            decisao="CONHECIDO. DESPROVIDO. UNÂNIME.",
            possui_inteiro_teor=True,
        )
    ),
    _Exemplo(
        DetalheAcordao(
            id=3,
            fonte="tjdft",
            tribunal="TJDFT",
            numero_processo=_TJDFT_2,
            orgao_julgador="1ª Câmara Criminal",
            classe=Classe(codigo=417, nome="Apelação Criminal"),
            relator="Sicrano de Tal",
            relator_designado="Beltrana de Tal",
            turma_recursal=False,
            data_julgamento=date(2026, 10, 2),
            data_publicacao=date(2026, 10, 14),
            data_disponibilizacao=None,
            link_oficial="https://jurisdf.tjdft.jus.br/acordaos/00000000-2099-4000-8000-000000000003",
            link_tribunal=None,
            citacao=(
                f"TJDFT, 1ª Câmara Criminal, Apelação Criminal nº {_TJDFT_2}, Rel. p/ acórdão "
                "Beltrana de Tal, j. 02/10/2026, publ. DJE 14/10/2026."
            ),
            ementa=(
                "PENAL. VIOLÊNCIA DOMÉSTICA. LEI MARIA DA PENHA. LESÃO CORPORAL. Palavra da "
                "vítima corroborada por outras provas. Condenação mantida."
            ),
            decisao="CONHECIDO. DESPROVIDO. MAIORIA.",
            possui_inteiro_teor=True,
        )
    ),
)


def _recente(n: int) -> _Exemplo:
    """Acórdão sintético a mais, só para a lista de recentes ter duas páginas (F5-13)."""
    djen = n % 2 == 0
    tribunal, codigo = ("TJPR", "16") if djen else ("TJDFT", "07")
    numero = _numero(20000 + n, codigo)
    julgamento = date(2026, 9, 1) + timedelta(days=n)
    publicacao = julgamento + timedelta(days=7)
    orgao = "2ª Turma Recursal" if djen else "5ª Turma Cível"
    classe = (
        Classe(codigo=460, nome="Recurso Inominado Cível")
        if djen
        else Classe(codigo=198, nome="Apelação Cível")
    )
    data_j, data_p = julgamento.strftime("%d/%m/%Y"), publicacao.strftime("%d/%m/%Y")
    final = f"DJEN de {data_p}" if djen else f"publ. PJe {data_p}"
    return _Exemplo(
        DetalheAcordao(
            id=100 + n,
            fonte="djen" if djen else "tjdft",
            tribunal=tribunal,
            numero_processo=numero,
            orgao_julgador=orgao,
            classe=classe,
            relator="Fulano de Tal",
            relator_designado=None,
            turma_recursal=djen,
            data_julgamento=julgamento,
            data_publicacao=None if djen else publicacao,
            data_disponibilizacao=publicacao if djen else None,
            link_oficial=(
                f"https://comunicaapi.pje.jus.br/api/v1/comunicacao/recente{n}/certidao"
                if djen
                else f"https://jurisdf.tjdft.jus.br/acordaos/00000000-2099-4000-8000-{n:012d}"
            ),
            link_tribunal=None,
            citacao=(
                f"{tribunal}, {orgao}, {classe.nome} nº {numero}, Rel. Fulano de Tal, "
                f"j. {data_j}, {final}."
            ),
            ementa=f"EMENTA SINTÉTICA Nº {n}. Exemplo da lista de acórdãos recentes.",
            decisao=None if djen else "CONHECIDO. DESPROVIDO. UNÂNIME.",
            possui_inteiro_teor=None if djen else True,
        )
    )


# Fora da busca, dos filtros e da cobertura (os testes contam com os três EXEMPLOS); aparecem
# só na lista de recentes e no detalhe.
RECENTES_EXTRAS = tuple(_recente(n) for n in range(1, 13))
INDISPONIVEIS = {
    4: Indisponivel(erro="removido", mensagem="Acórdão removido a pedido.", link_oficial=None),
    5: Indisponivel(
        erro="cancelado",
        mensagem="A publicação foi cancelada na fonte oficial.",
        link_oficial="https://comunicaapi.pje.jus.br/api/v1/comunicacao/exemplo5/certidao",
    ),
}


def _publicacao(exemplo: _Exemplo) -> date | None:
    return exemplo.detalhe.data_publicacao or exemplo.detalhe.data_disponibilizacao


def _palavras(texto: str) -> set[str]:
    # Palavras com 4+ letras: "por", "dos" etc. não contam.
    return set(re.findall(r"\w{4,}", chave(texto)))


def _trecho(ementa: str, palavras: set[str]) -> str:
    """Ementa escapada, com <mark> em volta das palavras da consulta."""

    def marcar(m: re.Match[str]) -> str:
        return f"<mark>{m.group()}</mark>" if chave(m.group()) in palavras else m.group()

    return re.sub(r"\w+", marcar, html.escape(ementa))


def _resultado(exemplo: _Exemplo, palavras: set[str]) -> ResultadoBusca:
    campos = exemplo.detalhe.model_dump(exclude={"ementa", "decisao", "possui_inteiro_teor"})
    return ResultadoBusca(**campos, trecho=_trecho(exemplo.detalhe.ementa, palavras))


def _aplica(exemplo: _Exemplo, filtros: FiltrosBusca) -> bool:
    d, ref = exemplo.detalhe, exemplo.data_referencia
    return (
        (filtros.tribunal is None or d.tribunal == filtros.tribunal.upper())
        and (filtros.orgao is None or d.orgao_julgador == filtros.orgao)
        and (filtros.classe is None or d.classe.codigo == filtros.classe)
        and (filtros.relator is None or chave(d.relator or "") == filtros.relator)
        and (filtros.data_inicio is None or (ref is not None and ref >= filtros.data_inicio))
        and (filtros.data_fim is None or (ref is not None and ref <= filtros.data_fim))
    )


def _opcoes(valores: list[tuple[str, str]]) -> list[OpcaoFiltro]:
    totais: dict[tuple[str, str], int] = {}
    for valor in valores:
        totais[valor] = totais.get(valor, 0) + 1
    return [OpcaoFiltro(valor=v, rotulo=r, total=t) for (v, r), t in sorted(totais.items())]


class ServicoMock:
    def __init__(self) -> None:
        self._protocolos = count(1)

    def buscar(
        self, consulta: ConsultaAnalisada, filtros: FiltrosBusca, pagina: int
    ) -> RespostaBusca:
        candidatos = [e for e in EXEMPLOS if _aplica(e, filtros)]
        if consulta.numero is not None:
            candidatos = [e for e in candidatos if e.digitos.startswith(consulta.numero.digitos)]
        palavras = _palavras(consulta.texto)
        if palavras:
            pontos = {e.detalhe.id: len(palavras & _palavras(e.detalhe.ementa)) for e in candidatos}
            candidatos = sorted(
                (e for e in candidatos if pontos[e.detalhe.id]),
                key=lambda e: -pontos[e.detalhe.id],
            )
        candidatos = candidatos[:LIMITE_RESULTADOS]
        inicio = (pagina - 1) * POR_PAGINA
        numero = consulta.numero
        return RespostaBusca(
            consulta=consulta.original,
            tipo=consulta.tipo,
            numero_processo=(numero.mascara or numero.digitos) if numero else None,
            filtros=filtros,
            pagina=pagina,
            total=len(candidatos),
            resultados=[_resultado(e, palavras) for e in candidatos[inicio : inicio + POR_PAGINA]],
        )

    def recentes(self, pagina: int) -> RespostaRecentes:
        exemplos = sorted(
            (*EXEMPLOS, *RECENTES_EXTRAS),
            key=lambda e: (_publicacao(e) or date.min, e.detalhe.id),
            reverse=True,
        )[:LIMITE_RECENTES]
        inicio = (pagina - 1) * POR_PAGINA_RECENTES
        return RespostaRecentes(
            pagina=pagina,
            total=len(exemplos),
            total_paginas=math.ceil(len(exemplos) / POR_PAGINA_RECENTES),
            resultados=[
                _resultado(e, set()) for e in exemplos[inicio : inicio + POR_PAGINA_RECENTES]
            ],
        )

    def detalhe(self, acordao_id: int) -> DetalheAcordao | Indisponivel | None:
        if acordao_id in INDISPONIVEIS:
            return INDISPONIVEIS[acordao_id]
        todos = (*EXEMPLOS, *RECENTES_EXTRAS)
        return next((e.detalhe for e in todos if e.detalhe.id == acordao_id), None)

    def situacao(self, acordao_id: int) -> SituacaoAcordao | None:
        resultado = self.detalhe(acordao_id)
        if resultado is None:
            return None
        if isinstance(resultado, Indisponivel):
            return SituacaoAcordao(situacao=resultado.erro)
        return SituacaoAcordao(situacao="ativo")

    def processo(self, digitos: str) -> AcordaosDoProcesso | None:
        exemplos = [e for e in EXEMPLOS if e.digitos.startswith(digitos)]
        if not exemplos:
            return None
        exemplos.sort(key=lambda e: e.data_referencia or date.min, reverse=True)
        return AcordaosDoProcesso(
            numero_processo=exemplos[0].detalhe.numero_processo,
            acordaos=[_resultado(e, set()) for e in exemplos],
        )

    def filtros(self) -> Filtros:
        detalhes = [e.detalhe for e in EXEMPLOS]
        return Filtros(
            tribunais=_opcoes([(d.tribunal, d.tribunal) for d in detalhes]),
            orgaos=_opcoes(
                [(d.orgao_julgador, d.orgao_julgador) for d in detalhes if d.orgao_julgador]
            ),
            classes=_opcoes(
                [(str(d.classe.codigo), d.classe.nome or "") for d in detalhes if d.classe.codigo]
            ),
        )

    def cobertura(self) -> list[CoberturaTribunal]:
        por_chave: dict[tuple[str, str], list[_Exemplo]] = {}
        for exemplo in EXEMPLOS:
            por_chave.setdefault((exemplo.detalhe.fonte, exemplo.detalhe.tribunal), []).append(
                exemplo
            )
        saida = []
        for (fonte, tribunal), exemplos in sorted(por_chave.items(), key=lambda x: x[0][1]):
            datas = [e.data_referencia for e in exemplos if e.data_referencia]
            saida.append(
                CoberturaTribunal(
                    fonte=exemplos[0].detalhe.fonte,
                    fonte_nome=FONTES[fonte].nome,
                    fonte_url=FONTES[fonte].url,
                    tribunal=tribunal,
                    acordaos=len(exemplos),
                    desde=min(datas, default=None),
                    ate=max(datas, default=None),
                )
            )
        return saida

    def relatores(self, prefixo: str) -> list[Relator]:
        alvo = chave(prefixo)
        nomes = sorted({d.relator for d in (e.detalhe for e in EXEMPLOS) if d.relator})
        return [Relator(nome=n, chave=chave(n)) for n in nomes if alvo in chave(n)]

    def registrar_remocao(self, pedido: PedidoRemocao) -> RemocaoRecebida:
        return RemocaoRecebida(
            protocolo=next(self._protocolos),
            status="pendente",
            mensagem="Pedido recebido (mock: nada foi gravado).",
        )
