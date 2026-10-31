"""Spike F2-02: estrutura dos registros da API do TJDFT, sem expor conteúdo.

Roda numa máquina no Brasil. Para cada data de publicação pedida, percorre todas as páginas
(``tamanho`` 40, uma requisição a cada ~1,1 s) da base ``acordaos`` e imprime **apenas**
agregados:

- nomes de campos, tipos e contagens de presença;
- valores de campos categóricos de uma lista fechada (base, subbase, booleanos, código da
  classe, versão), só os que aparecem 3 vezes ou mais;
- "formas" de valores (dígitos → 9, letras → a), nunca os valores; para
  ``localDePublicacao``, a forma com dígitos → 9 e letras preservadas, só se aparecer 3 vezes
  ou mais (é um modelo de texto do sistema, não conteúdo do acórdão);
- para nomes (relator, revisor, designado): só presença, caixa e o título inicial, se for um
  de uma lista fechada;
- para ementa e decisão: só tamanho e presença de HTML/entidades;
- conferência da paginação (uuids únicos × ``hits.value``) e do fuso das datas.

Nada de ementa, decisão, nome, número de processo, uuid ou identificador chega à saída.
Nada é gravado em disco.

Uso (de ``backend/``)::

    uv run python scripts/spike_api_tjdft.py 2026-10-20
"""

import argparse
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

API = "https://jurisdf.tjdft.jus.br/api/v1/pesquisa"
USER_AGENT = "BuscaJus/spike-F2-02 (+https://github.com/danielcperalba/buscajus)"
TAMANHO = 40
PAUSA = 1.1
FUSO = ZoneInfo("America/Sao_Paulo")
MIN_CATEGORIA = 3

CATEGORICOS = (
    "base",
    "subbase",
    "turmaRecursal",
    "segredoJustica",
    "possuiInteiroTeor",
    "codigoClasseCnj",
    "versao",
)
NOMES = ("nomeRelator", "nomeRevisor", "nomeRelatorDesignado")
TEXTOS = ("ementa", "decisao", "inteiroTeorHtml")
DATAS = ("dataJulgamento", "dataPublicacao")
FORMAS = ("uuid", "identificador", "processo")
TITULOS = {
    "DESEMBARGADOR",
    "DESEMBARGADORA",
    "DES.",
    "DESA.",
    "JUIZ",
    "JUIZA",
    "JUÍZA",
    "JUIZ(A)",
    "DESEMBARGADOR(A)",
}
_HTML = re.compile(r"<[a-zA-Z/]")
_ENTIDADE = re.compile(r"&#?\w+;")


def forma(valor: str) -> str:
    return re.sub(r"[^\W\d_]", "a", re.sub(r"\d", "9", valor))


def forma_modelo(valor: str) -> str:
    return re.sub(r"\d", "9", valor)


def tipo(valor: Any) -> str:
    return "null" if valor is None else type(valor).__name__


# Só nomes de campo (camelCase iniciado por minúscula); nomes de pessoas vêm em maiúsculas.
_IDENTIFICADOR = re.compile(r"^[a-z][A-Za-z0-9_]{0,40}$")


def chaves(objeto: dict[str, Any]) -> str:
    """Nomes de chaves com forma de identificador; as demais só são contadas."""
    nomes = sorted(k for k in objeto if isinstance(k, str) and _IDENTIFICADOR.match(k))
    outras = len(objeto) - len(nomes)
    return ",".join(nomes) + (f" +{outras} chaves não identificadoras" if outras else "")


def estrutura(valor: Any, profundidade: int = 0) -> str:
    """Forma aninhada (chaves identificadoras e tipos das folhas), nunca os valores."""
    if profundidade >= 4:
        return tipo(valor)
    if isinstance(valor, dict):
        nomes = sorted(k for k in valor if isinstance(k, str) and _IDENTIFICADOR.match(k))
        partes = [f"{k}: {estrutura(valor[k], profundidade + 1)}" for k in nomes]
        if len(nomes) < len(valor):
            partes.append(f"+{len(valor) - len(nomes)} chaves não identificadoras")
        return "{" + ", ".join(partes) + "}"
    if isinstance(valor, list):
        tipos = sorted({estrutura(e, profundidade + 1) for e in valor[:20]})
        return "list[" + " | ".join(tipos) + "]"
    return tipo(valor)


def caixa(valor: str) -> str:
    letras = [c for c in valor if c.isalpha()]
    if not letras:
        return "sem letras"
    if all(c.isupper() for c in letras):
        return "MAIÚSCULAS"
    if all(c.islower() for c in letras):
        return "minúsculas"
    return "Mista"


def categorias(contador: Counter[Any]) -> dict[str, int]:
    visiveis = {str(k): v for k, v in contador.most_common() if v >= MIN_CATEGORIA}
    raros = sum(v for v in contador.values() if v < MIN_CATEGORIA)
    if raros:
        visiveis["<valores raros>"] = raros
    return visiveis


def requisitar(cliente: httpx.Client, dia: date, pagina: int) -> httpx.Response:
    time.sleep(PAUSA)
    return cliente.post(
        API,
        json={
            "query": "",
            "pagina": pagina,
            "tamanho": TAMANHO,
            "termosAcessorios": [
                {"campo": "base", "valor": "acordaos"},
                {"campo": "dataPublicacao", "valor": dia.isoformat()},
            ],
        },
    )


class Agregados:
    def __init__(self) -> None:
        self.registros = 0
        self.chaves_resposta: Counter[str] = Counter()
        self.chaves_hits: Counter[str] = Counter()
        self.campos: Counter[str] = Counter()
        self.tipos: dict[str, Counter[str]] = defaultdict(Counter)
        self.categoricos: dict[str, Counter[Any]] = defaultdict(Counter)
        self.formas: dict[str, Counter[str]] = defaultdict(Counter)
        self.local_publicacao: Counter[str] = Counter()
        self.nomes: dict[str, Counter[str]] = defaultdict(Counter)
        self.designado_difere = 0
        self.tamanhos: dict[str, list[int]] = defaultdict(list)
        self.html: Counter[str] = Counter()
        self.entidades: Counter[str] = Counter()
        self.datas_forma: dict[str, Counter[str]] = defaultdict(Counter)
        self.hora_utc: Counter[int] = Counter()
        self.data_pedida: Counter[str] = Counter()
        self.segredo_campos: Counter[str] = Counter()
        self.listas: dict[str, Counter[str]] = defaultdict(Counter)
        self.classe_ausente = 0
        self.marcadores: Counter[str] = Counter()
        self.orgao: Counter[str] = Counter()
        self.paginacao: Counter[str] = Counter()
        self.agregacoes: Counter[str] = Counter()

    def registro(self, reg: dict[str, Any], dia: date) -> None:
        self.registros += 1
        for campo, valor in reg.items():
            self.campos[campo] += 1
            self.tipos[campo][tipo(valor)] += 1
            if isinstance(valor, list):
                for elemento in valor[:50]:
                    if isinstance(elemento, dict):
                        self.listas[campo]["dict:" + chaves(elemento)] += 1
                    else:
                        self.listas[campo][tipo(elemento)] += 1
            elif isinstance(valor, dict):
                self.listas[campo]["chaves:" + chaves(valor)] += 1
        for campo in CATEGORICOS:
            if campo in reg:
                valor = reg[campo]
                if isinstance(valor, (dict, list)):
                    valor = tipo(valor)
                self.categoricos[campo][valor] += 1
        if reg.get("codigoClasseCnj") in (None, ""):
            self.classe_ausente += 1
        for campo in FORMAS:
            valor = reg.get(campo)
            if isinstance(valor, str):
                self.formas[campo][forma(valor)] += 1
            elif valor is not None:
                self.formas[campo][f"<{tipo(valor)}>"] += 1
        if "marcadores" in reg:
            self.marcadores[estrutura(reg["marcadores"])] += 1
        orgao = reg.get("descricaoOrgaoJulgador")
        if isinstance(orgao, str):
            self.orgao[f"{caixa(orgao)} | {forma(orgao)}"] += 1
        local = reg.get("localDePublicacao")
        if isinstance(local, str):
            self.local_publicacao[forma_modelo(local)] += 1
        elif "localDePublicacao" in reg:
            self.local_publicacao[f"<{tipo(local)}>"] += 1
        for campo in NOMES:
            valor = reg.get(campo)
            if isinstance(valor, str) and valor.strip():
                primeiro = valor.split()[0].upper()
                titulo = primeiro if primeiro in TITULOS else "<sem título conhecido>"
                self.nomes[campo][f"{caixa(valor)} | {titulo}"] += 1
            else:
                self.nomes[campo][f"<{tipo(valor)}{'/vazio' if valor == '' else ''}>"] += 1
        designado, relator = reg.get("nomeRelatorDesignado"), reg.get("nomeRelator")
        if isinstance(designado, str) and designado.strip() and designado != relator:
            self.designado_difere += 1
        for campo in TEXTOS:
            valor = reg.get(campo)
            if isinstance(valor, str):
                self.tamanhos[campo].append(len(valor))
                if _HTML.search(valor):
                    self.html[campo] += 1
                if _ENTIDADE.search(valor):
                    self.entidades[campo] += 1
        for campo in DATAS:
            valor = reg.get(campo)
            if not isinstance(valor, str):
                self.datas_forma[campo][f"<{tipo(valor)}>"] += 1
                continue
            self.datas_forma[campo][forma(valor)] += 1
            if campo != "dataPublicacao":
                continue
            try:
                quando = datetime.fromisoformat(valor.replace("Z", "+00:00"))
            except ValueError:
                self.data_pedida["não interpretável"] += 1
                continue
            self.hora_utc[quando.hour] += 1
            utc_igual = quando.date() == dia
            sp_igual = quando.astimezone(FUSO).date() == dia
            self.data_pedida[f"data UTC = pedida: {utc_igual}; data SP = pedida: {sp_igual}"] += 1
        if reg.get("segredoJustica") is not False:
            for campo, valor in reg.items():
                vazio = valor in (None, "", [], {})
                self.segredo_campos[f"{campo}{' (vazio)' if vazio else ''}"] += 1

    def imprimir(self) -> None:
        def secao(titulo: str, dados: Any) -> None:
            print(f"\n## {titulo}")
            if isinstance(dados, dict):
                for chave, valor in dados.items():
                    print(f"  {chave}: {valor}")
            else:
                print(f"  {dados}")

        secao("registros", self.registros)
        secao("chaves da resposta", dict(self.chaves_resposta))
        secao("chaves de hits", dict(self.chaves_hits))
        secao("campos (presença)", dict(self.campos.most_common()))
        secao("tipos", {c: dict(t) for c, t in sorted(self.tipos.items())})
        secao("listas/objetos (estrutura)", {c: dict(t) for c, t in self.listas.items()})
        secao("categóricos", {c: categorias(v) for c, v in self.categoricos.items()})
        secao("codigoClasseCnj ausente", self.classe_ausente)
        secao("formas", {c: categorias(v) for c, v in self.formas.items()})
        secao("marcadores (estrutura)", dict(self.marcadores))
        secao("descricaoOrgaoJulgador (caixa | forma)", categorias(self.orgao))
        secao("paginacao (estrutura)", dict(self.paginacao))
        secao("agregacoes (estrutura)", dict(self.agregacoes))
        secao("localDePublicacao (modelo)", categorias(self.local_publicacao))
        secao("nomes (caixa | título)", {c: categorias(v) for c, v in self.nomes.items()})
        secao("designado diferente do relator", self.designado_difere)
        secao(
            "tamanhos de texto",
            {
                c: f"n={len(v)} min={min(v)} mediana={statistics.median(v):.0f} max={max(v)}"
                for c, v in self.tamanhos.items()
                if v
            },
        )
        secao("com tags HTML", dict(self.html))
        secao("com entidades HTML", dict(self.entidades))
        secao("formas de data", {c: categorias(v) for c, v in self.datas_forma.items()})
        secao("hora UTC de dataPublicacao", dict(sorted(self.hora_utc.items())))
        secao("dataPublicacao × dia pedido", dict(self.data_pedida))
        secao("campos dos registros com segredo != false", dict(self.segredo_campos))


def analisar(cliente: httpx.Client, dia: date, agregados: Agregados) -> None:
    print(f"\n# {dia.isoformat()}")
    uuids: list[str] = []
    totais: set[int] = set()
    pagina = 0
    while True:
        resposta = requisitar(cliente, dia, pagina)
        if resposta.status_code != 200:
            print(f"  página {pagina}: HTTP {resposta.status_code}")
            return
        corpo = resposta.json()
        for chave, valor in corpo.items():
            agregados.chaves_resposta[f"{chave}: {tipo(valor)}"] += 1
        agregados.paginacao[estrutura(corpo.get("paginacao"))] += 1
        agregados.agregacoes[estrutura(corpo.get("agregacoes"))] += 1
        hits = corpo.get("hits")
        if isinstance(hits, dict):
            for chave, valor in hits.items():
                agregados.chaves_hits[f"{chave}: {tipo(valor)}"] += 1
            if isinstance(hits.get("value"), int):
                totais.add(hits["value"])
        registros = corpo.get("registros") or []
        for reg in registros:
            if isinstance(reg, dict):
                agregados.registro(reg, dia)
                if isinstance(reg.get("uuid"), str):
                    uuids.append(reg["uuid"])
        total = max(totais) if totais else 0
        if not registros or (pagina + 1) * TAMANHO >= total:
            break
        pagina += 1
    print(f"  páginas: {pagina + 1}; hits.value distintos entre páginas: {len(totais)}")
    print(
        f"  registros: {len(uuids)}; uuids únicos: {len(set(uuids))}; hits.value: {sorted(totais)}"
    )

    # A primeira página de novo: a ordem é estável entre duas consultas?
    resposta = requisitar(cliente, dia, 0)
    if resposta.status_code == 200:
        repetida = [r.get("uuid") for r in resposta.json().get("registros") or []]
        print(f"  página 0 repetida: mesma ordem = {repetida == uuids[: len(repetida)]}")

    # Página além do fim: como vem a página vazia?
    resposta = requisitar(cliente, dia, pagina + 1)
    if resposta.status_code == 200:
        corpo = resposta.json()
        print(
            f"  página após o fim: HTTP 200, registros = {len(corpo.get('registros') or [])}, "
            f"tipo de registros = {tipo(corpo.get('registros'))}"
        )
    else:
        print(f"  página após o fim: HTTP {resposta.status_code}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("datas", nargs="+", type=date.fromisoformat)
    args = parser.parse_args()
    agregados = Agregados()
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30) as cliente:
        for dia in args.datas:
            analisar(cliente, dia, agregados)
    agregados.imprimir()
    return 0


if __name__ == "__main__":
    sys.exit(main())
