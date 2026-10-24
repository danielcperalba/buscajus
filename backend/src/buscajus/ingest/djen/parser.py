"""Parser do ``texto`` das ementas do DJEN (F1-19, F1-20; ARCHITECTURE.md, seção 5.1).

O ``texto`` (já anonimizado) é HTML: uma tabela de cabeçalho com ``Processo``,
``Relator(a)``, ``Órgão Julgador`` e ``Data do Julgamento``, seguida da ementa numa célula
``colspan=2``. Do cabeçalho só se extraem os rótulos da lista branca; os demais são
descartados. Sem tabela, o parser tenta os rótulos no início do texto e, por fim, usa o
texto inteiro.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from lxml import etree
from lxml import html as lxml_html

from buscajus.core.erros import ErroSeguro
from buscajus.ingest.texto import chave, decodificar, normalizar_espacos

VERSAO_PARSER = "djen-1"
# Ementa mais curta que isso é tratada como falha de parser.
MINIMO_CARACTERES = 40

Campo = Literal["processo", "relator", "data_julgamento", "ementa"]
RotuloCabecalho = Campo | Literal["descartado"]

# Lista branca de rótulos (normalizados: sem acento, minúsculos, sem ":").
ROTULOS: dict[str, Campo] = {
    "processo": "processo",
    "relator": "relator",
    "relator(a)": "relator",
    "relatora": "relator",
    "data do julgamento": "data_julgamento",
    "data de julgamento": "data_julgamento",
    "ementa": "ementa",
}

_BLOCOS = frozenset(
    {
        "p",
        "div",
        "tr",
        "li",
        "ul",
        "ol",
        "table",
        "tbody",
        "thead",
        "blockquote",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    }
)
_CELULAS = frozenset({"td", "th"})
_ROTULO_EM_LINHA = re.compile(r"^([^:]{2,40}):\s*(.*)$", re.DOTALL)
_PROCESSO = re.compile(r"^\s*([\d.\-\s]+?)\s*(?:\((.*)\))?\s*$", re.DOTALL)
_DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_ROTULO_EMENTA = re.compile(r"^\s*ementa\s*:\s*", re.IGNORECASE)


class FalhaParser(ErroSeguro):
    """O texto não rendeu uma ementa utilizável. A mensagem não traz conteúdo."""


@dataclass(frozen=True)
class EmentaDjen:
    ementa: str
    relator: str | None
    processo: str | None  # número como veio no cabeçalho
    classe: str | None  # classe colada ao número no cabeçalho
    data_julgamento: date | None
    data_julgamento_invalida: bool
    origem: Literal["tabela", "rotulos_no_texto", "texto_inteiro"]

    @property
    def fallback(self) -> bool:
        return self.origem != "tabela"


def texto_de(elemento: etree._Element) -> str:
    """Texto do elemento com ``<br>`` e blocos convertidos em quebras de linha."""
    partes: list[str] = []

    def visitar(el: etree._Element) -> None:
        tag = el.tag if isinstance(el.tag, str) else ""
        if tag == "br" or tag in _BLOCOS:
            partes.append("\n")
        elif tag in _CELULAS:
            partes.append(" ")
        if tag and el.text:
            partes.append(el.text)
        for filho in el:
            visitar(filho)
            if filho.tail:
                partes.append(filho.tail)
        if tag in _BLOCOS:
            partes.append("\n")

    visitar(elemento)
    return normalizar_espacos(decodificar("".join(partes)))


def _rotulo(texto: str) -> RotuloCabecalho:
    return ROTULOS.get(chave(texto).rstrip(":").strip(), "descartado")


def _data(valor: str) -> tuple[date | None, bool]:
    valor = valor.strip()
    if not valor:
        return None, False
    if _DATA.match(valor):
        try:
            return datetime.strptime(valor, "%d/%m/%Y").date(), False  # noqa: DTZ007
        except ValueError:
            pass
    return None, True


def _processo(valor: str | None) -> tuple[str | None, str | None]:
    if not valor:
        return None, None
    m = _PROCESSO.match(valor)
    if not m:
        return valor.strip() or None, None
    classe = (m.group(2) or "").strip() or None
    return m.group(1).replace(" ", "") or None, classe


def _celula_ementa(celula: etree._Element) -> str:
    texto = texto_de(celula)
    return _ROTULO_EMENTA.sub("", texto, count=1)


def analisar(texto_html: str) -> EmentaDjen:
    if not texto_html or not texto_html.strip():
        raise FalhaParser("texto vazio")
    try:
        raiz = lxml_html.fragment_fromstring(texto_html, create_parent="div")
    except (etree.ParserError, ValueError) as exc:
        raise FalhaParser("HTML não pôde ser lido") from exc

    tabela = next(iter(raiz.iter("table")), None)
    if tabela is None:
        return _sem_tabela(texto_de(raiz))

    campos: dict[Campo, str] = {}
    partes_ementa: list[str] = []
    for linha in tabela.iter("tr"):
        celulas = [c for c in linha if isinstance(c.tag, str) and c.tag in _CELULAS]
        if not celulas:
            continue
        primeira = texto_de(celulas[0])
        m = _ROTULO_EM_LINHA.match(primeira)
        if not m:
            continue
        campo = _rotulo(m.group(1))
        if campo == "descartado":
            continue
        if campo == "ementa":
            alvo = celulas[0] if len(celulas) == 1 else celulas[1]
            partes_ementa.append(_celula_ementa(alvo))
            continue
        valor = " ".join(texto_de(c) for c in celulas[1:]) if len(celulas) > 1 else m.group(2)
        campos.setdefault(campo, " ".join(valor.split()))

    # Texto fora da tabela de cabeçalho também faz parte da ementa.
    pai = tabela.getparent()
    if pai is not None:
        cauda = tabela.tail
        pai.remove(tabela)
        if cauda:
            # Sem a tabela, a cauda dela ficaria órfã: preservá-la num elemento próprio.
            span = etree.SubElement(pai, "span")
            span.text = cauda
    fora = texto_de(raiz)
    if fora:
        partes_ementa.append(fora)

    return _resultado(campos, "\n\n".join(p for p in partes_ementa if p), "tabela")


def _sem_tabela(texto: str) -> EmentaDjen:
    """Rótulos em linhas no início do texto; se não houver nenhum, o texto inteiro."""
    linhas = texto.split("\n")
    campos: dict[Campo, str] = {}
    inicio_ementa = 0
    achou_rotulo = False
    for i, linha in enumerate(linhas):
        if not linha.strip():
            continue
        m = _ROTULO_EM_LINHA.match(linha)
        if not m:
            inicio_ementa = i
            break
        campo = _rotulo(m.group(1))
        # Sem nenhum rótulo de cabeçalho antes, "EMENTA:" é o começo do próprio texto.
        if campo in ("descartado", "ementa") and not achou_rotulo:
            inicio_ementa = i
            break
        achou_rotulo = True
        if campo == "ementa":
            resto = m.group(2).strip()
            linhas[i] = resto
            inicio_ementa = i
            break
        if campo != "descartado":
            campos.setdefault(campo, " ".join(m.group(2).split()))
        inicio_ementa = i + 1
    if not achou_rotulo:
        return _resultado({}, texto, "texto_inteiro")
    return _resultado(campos, "\n".join(linhas[inicio_ementa:]), "rotulos_no_texto")


def _resultado(
    campos: dict[Campo, str],
    ementa: str,
    origem: Literal["tabela", "rotulos_no_texto", "texto_inteiro"],
) -> EmentaDjen:
    ementa = normalizar_espacos(ementa)
    if len(ementa) < MINIMO_CARACTERES:
        raise FalhaParser(f"ementa com {len(ementa)} caracteres (mínimo {MINIMO_CARACTERES})")
    data, invalida = _data(campos.get("data_julgamento", ""))
    processo, classe = _processo(campos.get("processo"))
    return EmentaDjen(
        ementa=ementa,
        relator=campos.get("relator") or None,
        processo=processo,
        classe=classe,
        data_julgamento=data,
        data_julgamento_invalida=invalida,
        origem=origem,
    )


def processo_confere(processo_cabecalho: str | None, numero_estruturado: str) -> bool:
    """O número do cabeçalho bate com o campo estruturado (só dígitos)?"""
    if processo_cabecalho is None:
        return True

    def digitos(valor: str) -> str:
        return "".join(c for c in valor if c.isdigit())

    return digitos(processo_cabecalho) == digitos(numero_estruturado)


Analisador = Callable[[str], EmentaDjen]
