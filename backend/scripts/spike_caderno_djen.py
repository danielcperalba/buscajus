"""Spike F1-01: estrutura do caderno diário do DJEN, sem expor conteúdo.

Roda numa máquina com acesso ao DJEN (a API bloqueia IPs fora do Brasil). Para cada data:
consulta os metadados do caderno, baixa o ZIP para um diretório temporário, confere o
SHA-256, percorre as comunicações e imprime **apenas** agregados:

- contagens, tamanhos, nomes de campos e tipos;
- valores de campos categóricos de uma lista fechada (tipoDocumento, status, ativo, meio…),
  só os que aparecem 3 vezes ou mais;
- rótulos do cabeçalho das ementas, só os que têm forma de rótulo e aparecem 20 vezes ou mais;
- "formas" de valores (dígitos → 9, letras → a), nunca os valores.

Nada de texto de comunicação, nome de destinatário, número de processo, hash de comunicação
ou URL temporária chega à saída. O ZIP é apagado no ``finally``, inclusive em erro.

Uso (de ``backend/``)::

    uv run python scripts/spike_caderno_djen.py --tribunal TJPR 2026-10-15 2026-03-02 2023-09-01

Copie a saída (só agregados) para a seção 3.2 do ARCHITECTURE.md ou para a issue do F1-01.
"""

import argparse
import hashlib
import json
import re
import statistics
import sys
import tempfile
import time
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
from lxml import html as lxml_html

API = "https://comunicaapi.pje.jus.br/api/v1/caderno/{sigla}/{data}/D"
USER_AGENT = "BuscaJus/spike-F1-01 (+https://github.com/danielcperalba/buscajus)"
TIPO_EMENTA = "Ementa de Acórdão"

# Campos cujos valores são códigos ou categorias (nunca nomes ou texto livre).
CATEGORICOS = (
    "tipoDocumento",
    "tipoComunicacao",
    "meio",
    "meiocompleto",
    "status",
    "ativo",
    "siglaTribunal",
)
# Metadados do caderno cujo valor pode ser impresso.
METADADOS_IMPRIMIVEIS = {"versao", "status", "total", "total_comunicacoes", "tipo", "meio"}
MIN_CATEGORIA = 3
MIN_ROTULO = 20
FORMA_ROTULO = re.compile(r"^[a-z()/ ]{2,40}:?$")
TITULOS = {
    "des",
    "des.",
    "desa",
    "desa.",
    "desembargador",
    "desembargadora",
    "juiz",
    "juiza",
    "juíza",
    "dr",
    "dr.",
    "dra",
    "dra.",
    "substituto",
    "substituta",
    "rel",
    "rel.",
    "relator",
    "relatora",
    "juiz(a)",
    "desembargador(a)",
}
PROCESSO_COM_CLASSE = re.compile(r"^(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})(\s*)\((.+)\)\s*$")
DATA_BR = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.lower().split())


def forma(valor: str) -> str:
    """Só a forma: dígitos viram 9, letras viram a/A. Não revela o conteúdo."""
    saida = re.sub(r"\d", "9", valor)
    saida = re.sub(r"[^\W\d_]", lambda m: "A" if m.group().isupper() else "a", saida)
    return re.sub(r"([aA])\1+", r"\1…", saida)[:60]


def resumo_identificador(valor: str) -> str:
    """Só tamanho e classes de caractere (para hashes: nem a forma é impressa)."""
    classes = [
        nome
        for nome, teste in (
            ("dígitos", str.isdigit),
            ("minúsculas", str.islower),
            ("maiúsculas", str.isupper),
        )
        if any(teste(c) for c in valor)
    ]
    if any(not c.isalnum() for c in valor):
        classes.append("outros")
    return f"{len(valor)} caracteres: {', '.join(classes)}"


def resumo_link(valor: str) -> str:
    partes = urlsplit(valor)
    return f"{partes.hostname} {forma(partes.path)[:20]}{' ?' if partes.query else ''}"


def tipo(valor: Any) -> str:
    if valor is None:
        return "null"
    if isinstance(valor, list):
        return "list"
    return type(valor).__name__


def contagem_categorias(contador: Counter[Any], minimo: int = MIN_CATEGORIA) -> dict[str, int]:
    saida: dict[str, int] = {}
    outros = 0
    for valor, n in contador.most_common():
        if n >= minimo and len(str(valor)) <= 60:
            saida[repr(valor)] = n
        else:
            outros += n
    if outros:
        saida["<outros valores, agregados>"] = outros
    return saida


class Agregados:
    def __init__(self) -> None:
        self.c: Counter[str] = Counter()
        self.campos: Counter[str] = Counter()
        self.tipos: Counter[str] = Counter()
        self.categorias: dict[str, Counter[Any]] = {campo: Counter() for campo in CATEGORICOS}
        self.campos_destinatario: Counter[str] = Counter()
        self.campos_advogado_vinculo: Counter[str] = Counter()
        self.campos_advogado: Counter[str] = Counter()
        self.polos: Counter[Any] = Counter()
        self.formas: dict[str, Counter[str]] = {
            "data_disponibilizacao": Counter(),
            "id": Counter(),
            "numero_processo": Counter(),
            "numeroprocessocommascara": Counter(),
            "hash": Counter(),
            "data_cancelamento": Counter(),
            "codigoClasse": Counter(),
            "idOrgao": Counter(),
            "link": Counter(),
        }
        self.destinatarios_por_ementa: Counter[int] = Counter()
        self.advogados_por_ementa: Counter[int] = Counter()
        # ementas
        self.rotulos: Counter[str] = Counter()
        self.tags_ementa: Counter[str] = Counter()
        self.titulos_relator: Counter[str] = Counter()
        self.formas_processo: Counter[str] = Counter()
        self.formas_data: Counter[str] = Counter()
        self.linhas_tabela: Counter[int] = Counter()
        self.celulas_por_linha: Counter[int] = Counter()
        self.tamanhos_texto: list[int] = []
        self.orgaos_ementa: set[str] = set()

    def item(self, item: dict[str, Any]) -> None:
        self.c["comunicacoes"] += 1
        for campo, valor in item.items():
            self.campos[campo] += 1
            self.tipos[f"{campo}: {tipo(valor)}"] += 1
        for campo in CATEGORICOS:
            if campo in item:
                self.categorias[campo][item[campo]] += 1
        for campo, contador in self.formas.items():
            if item.get(campo) is None:
                continue
            valor = str(item[campo])
            if campo == "hash":
                contador[resumo_identificador(valor)] += 1
            elif campo == "link":
                contador[resumo_link(valor)] += 1
            else:
                contador[forma(valor)] += 1
        if item.get("data_cancelamento") is not None:
            self.c["com_data_cancelamento"] += 1
        if item.get("motivo_cancelamento") not in (None, ""):
            self.c["com_motivo_cancelamento"] += 1
        if item.get("ativo") is False:
            self.c["ativo_false"] += 1
        for d in item.get("destinatarios") or []:
            self.campos_destinatario.update(f"{k}: {tipo(v)}" for k, v in d.items())
            self.polos[d.get("polo")] += 1
        for v in item.get("destinatarioadvogados") or []:
            self.campos_advogado_vinculo.update(f"{k}: {tipo(x)}" for k, x in v.items())
            advogado = v.get("advogado")
            if isinstance(advogado, dict):
                self.campos_advogado.update(f"{k}: {tipo(x)}" for k, x in advogado.items())
        if item.get("tipoDocumento") == TIPO_EMENTA:
            self.ementa(item)

    def ementa(self, item: dict[str, Any]) -> None:
        self.c["ementas"] += 1
        if item.get("nomeOrgao"):
            self.orgaos_ementa.add(str(item["nomeOrgao"]))
        texto = str(item.get("texto") or "")
        self.tamanhos_texto.append(len(texto))
        self.destinatarios_por_ementa[len(item.get("destinatarios") or [])] += 1
        self.advogados_por_ementa[len(item.get("destinatarioadvogados") or [])] += 1
        if "&amp;" in texto:
            self.c["ementas_com_&amp;"] += 1
        if re.search(r"&#\d+;", texto):
            self.c["ementas_com_entidade_numerica"] += 1
        if re.search(r"&[A-Za-z]+;", texto):
            self.c["ementas_com_entidade_nomeada"] += 1
        if not texto.strip():
            self.c["ementas_texto_vazio"] += 1
            return
        try:
            raiz = lxml_html.fragment_fromstring(texto, create_parent="div")
        except Exception:
            self.c["ementas_html_invalido"] += 1
            return
        tabelas = raiz.findall(".//table")
        self.c[f"ementas_com_{min(len(tabelas), 3)}_tabelas"] += 1
        if not tabelas:
            return
        tabela = tabelas[0]
        fora = "".join(raiz.itertext()).strip()
        dentro = "".join(tabela.itertext()).strip()
        if len(fora) > len(dentro) + 20:
            self.c["ementas_com_texto_fora_da_tabela"] += 1
        linhas = tabela.findall(".//tr")
        self.linhas_tabela[len(linhas)] += 1
        texto_normalizado = normalizar(" ".join(raiz.itertext()))
        for d in item.get("destinatarios") or []:
            nome = normalizar(str(d.get("nome") or ""))
            if len(nome.split()) >= 2 and nome in texto_normalizado:
                self.c["ementas_com_nome_de_destinatario_no_texto"] += 1
                break
        for linha in linhas:
            celulas = linha.findall("./td") + linha.findall("./th")
            self.celulas_por_linha[len(celulas)] += 1
            if not celulas:
                continue
            if any(c.get("colspan") for c in celulas):
                self.c["linhas_com_colspan"] += 1
            primeira = " ".join(celulas[0].itertext())
            rotulo = normalizar(primeira.split(":", 1)[0] + ":") if ":" in primeira else ""
            if not rotulo:
                self.rotulos["<célula sem ':'>"] += 1
                continue
            self.rotulos[rotulo if FORMA_ROTULO.match(rotulo) else "<rótulo fora do padrão>"] += 1
            valor = (
                " ".join(" ".join(c.itertext()) for c in celulas[1:])
                if len(celulas) > 1
                else primeira.split(":", 1)[1]
            ).strip()
            if rotulo == "ementa:":
                self.c[
                    "ementa_na_mesma_celula" if len(celulas) == 1 else "ementa_em_outra_celula"
                ] += 1
                alvo = celulas[0] if len(celulas) == 1 else celulas[1]
                self.tags_ementa.update(el.tag for el in alvo.iter() if isinstance(el.tag, str))
            elif rotulo == "processo:":
                m = PROCESSO_COM_CLASSE.match(valor)
                if m:
                    self.formas_processo["NNNNNNN-DD.AAAA.J.TR.OOOO" + m.group(2) + "(classe)"] += 1
                    if m.group(1) == item.get("numeroprocessocommascara"):
                        self.c["processo_igual_ao_campo_com_mascara"] += 1
                    if normalizar(m.group(3)) == normalizar(str(item.get("nomeClasse") or "")):
                        self.c["classe_igual_a_nomeClasse"] += 1
                else:
                    self.formas_processo[forma(valor)] += 1
            elif rotulo.startswith("data"):
                self.formas_data["dd/mm/aaaa" if DATA_BR.match(valor) else forma(valor)] += 1
            elif rotulo.startswith("relator"):
                primeiro = normalizar(valor).split(" ", 1)[0] if valor else ""
                self.titulos_relator[primeiro if primeiro in TITULOS else "<nome, sem título>"] += 1

    def imprimir(self) -> None:
        def secao(titulo: str, dados: Any) -> None:
            print(f"\n## {titulo}")
            print(json.dumps(dados, ensure_ascii=False, indent=2, default=str))

        secao("Contagens", dict(sorted(self.c.items())))
        secao("Campos das comunicações (presença)", dict(self.campos.most_common()))
        secao("Tipos por campo", dict(sorted(self.tipos.items())))
        for campo, contador in self.categorias.items():
            secao(f"Valores de {campo}", contagem_categorias(contador))
        secao(
            "Formas dos valores (dígitos→9, letras→a)",
            {campo: contagem_categorias(c) for campo, c in self.formas.items()},
        )
        secao("Campos de destinatarios[]", dict(self.campos_destinatario.most_common()))
        secao("Valores de destinatarios[].polo", contagem_categorias(self.polos))
        secao("Campos de destinatarioadvogados[]", dict(self.campos_advogado_vinculo.most_common()))
        secao(
            "Campos de destinatarioadvogados[].advogado", dict(self.campos_advogado.most_common())
        )
        secao(
            "Ementas: destinatários por ementa", dict(sorted(self.destinatarios_por_ementa.items()))
        )
        secao("Ementas: advogados por ementa", dict(sorted(self.advogados_por_ementa.items())))
        secao("Ementas: órgãos distintos", len(self.orgaos_ementa))
        secao("Ementas: linhas na primeira tabela", dict(sorted(self.linhas_tabela.items())))
        secao("Ementas: células por linha", dict(sorted(self.celulas_por_linha.items())))
        secao("Ementas: rótulos do cabeçalho", contagem_categorias(self.rotulos, MIN_ROTULO))
        secao("Ementas: forma da célula Processo", contagem_categorias(self.formas_processo))
        secao("Ementas: forma da célula Data", contagem_categorias(self.formas_data))
        secao("Ementas: primeiro token do relator", contagem_categorias(self.titulos_relator))
        secao("Ementas: tags dentro da célula Ementa", dict(self.tags_ementa.most_common()))
        if self.tamanhos_texto:
            t = sorted(self.tamanhos_texto)
            secao(
                "Ementas: tamanho do texto (caracteres)",
                {
                    "min": t[0],
                    "p50": int(statistics.median(t)),
                    "p95": t[int(len(t) * 0.95) - 1] if len(t) > 1 else t[0],
                    "max": t[-1],
                },
            )


def metadados(cliente: httpx.Client, sigla: str, data: str) -> dict[str, Any] | None:
    resposta = cliente.get(API.format(sigla=sigla, data=data))
    limites = {k: v for k, v in resposta.headers.items() if k.lower().startswith("x-ratelimit")}
    print(
        f"metadados: HTTP {resposta.status_code}, {len(resposta.content)} bytes, limites={limites}"
    )
    if resposta.status_code != 200:
        return None
    corpo: dict[str, Any] = resposta.json()
    descricao = {}
    for chave, valor in corpo.items():
        if chave in METADADOS_IMPRIMIVEIS:
            descricao[chave] = valor
        elif chave == "hash":
            descricao[chave] = f"<{tipo(valor)}, {len(str(valor))} caracteres>"
        elif chave == "url" and isinstance(valor, str):
            partes = urlsplit(valor)
            consulta = parse_qs(partes.query)
            descricao[chave] = {
                "host": partes.hostname,
                "parametros": sorted(consulta),
                "X-Amz-Expires": consulta.get("X-Amz-Expires", [None])[0],
            }
        else:
            descricao[chave] = f"<{tipo(valor)}>"
    print("campos dos metadados:", json.dumps(descricao, ensure_ascii=False))
    return corpo


def analisar(cliente: httpx.Client, sigla: str, data: str, agregados: Agregados) -> None:
    print(f"\n# {sigla} {data}")
    meta = metadados(cliente, sigla, data)
    if meta is None or not meta.get("url"):
        return
    with tempfile.TemporaryDirectory(prefix="spike-djen-") as tmp:
        caminho = Path(tmp) / "caderno.zip"
        try:
            inicio = time.monotonic()
            with cliente.stream("GET", meta["url"], timeout=300) as resposta:
                print(f"download: HTTP {resposta.status_code}")
                if resposta.status_code != 200:
                    return
                with caminho.open("wb") as arquivo:
                    for bloco in resposta.iter_bytes():
                        arquivo.write(bloco)
            tamanho = caminho.stat().st_size
            sha = hashlib.sha256(caminho.read_bytes()).hexdigest()
            print(
                f"zip: {tamanho} bytes em {time.monotonic() - inicio:.1f} s; "
                f"sha256 confere com hash: {sha == str(meta.get('hash', '')).lower()}"
            )
            total_itens = 0
            with zipfile.ZipFile(caminho) as zf:
                nomes = zf.infolist()
                formas_nomes = Counter(forma(i.filename) for i in nomes)
                descompactado = sum(i.file_size for i in nomes)
                print(f"entradas: {len(nomes)}, descompactado: {descompactado} bytes")
                print("formas dos nomes:", dict(formas_nomes))
                for info in nomes:
                    with zf.open(info) as f:
                        pagina = json.load(f)
                    if not isinstance(pagina, dict):
                        agregados.c["entradas_nao_objeto"] += 1
                        continue
                    agregados.c["entradas"] += 1
                    chaves = ",".join(sorted(pagina))
                    agregados.c[f"chaves_da_entrada[{chaves}]"] += 1
                    itens = pagina.get("items") or []
                    if pagina.get("count") != len(itens):
                        agregados.c["entradas_count_diferente_de_len_items"] += 1
                    total_itens += len(itens)
                    for item in itens:
                        agregados.item(item)
            total_meta = meta.get("total_comunicacoes", meta.get("total"))
            print(
                f"comunicações no zip: {total_itens}; total nos metadados: {total_meta}; "
                f"confere: {total_itens == total_meta}"
            )
        finally:
            caminho.unlink(missing_ok=True)
            print("zip apagado:", not caminho.exists())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tribunal", default="TJPR")
    parser.add_argument("datas", nargs="+", help="AAAA-MM-DD")
    args = parser.parse_args()
    agregados = Agregados()
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30) as cliente:
        for data in args.datas:
            try:
                analisar(cliente, args.tribunal.upper(), data, agregados)
            except Exception as exc:
                # Só o tipo: mensagens do httpx podem conter a URL temporária.
                print(f"erro em {data}: {type(exc).__name__}")
            time.sleep(1)
    print("\n# Agregado de todas as datas")
    agregados.imprimir()
    return 0


if __name__ == "__main__":
    sys.exit(main())
