"""Recorte da ementa nos acórdãos do eproc do TJRJ, antes da anonimização (F1-50).

O TJRJ não publica "Ementa de Acórdão" no DJEN: publica o tipo "Acórdão" com o inteiro teor
em HTML (eproc de 2º grau). Medição só com agregados (cadernos de 28/10 e 05/11/2026, 909 e
465 itens): o título ``EMENTA`` vem sempre antes do título ``ACÓRDÃO``, num bloco próprio; antes
dele ficam as partes e os advogados; depois do ``ACÓRDÃO``, o dispositivo e a linha "Rio de
Janeiro, 5 de novembro de 2026." (data do julgamento, em 100% dos itens). Não há rótulo de
relator.

O recorte guarda só os blocos entre os dois títulos e a data. Partes, advogados e o texto do
acórdão são descartados em memória, antes do anonimizador e do bruto: o que segue adiante é
uma tabela no formato das ementas do TJPR (``Data do Julgamento`` e ``Ementa``), lida pelo
mesmo parser. Sem os dois títulos na ordem, o item não é aproveitado (falha de parser).
"""

import html
import re
from collections.abc import Callable, Iterator, Mapping
from typing import Any

from lxml import etree
from lxml import html as lxml_html

from buscajus.ingest.texto import chave, decodificar

_BLOCOS = frozenset({"p", "div", "td", "th", "li", "h1", "h2", "h3", "h4", "h5", "h6"})
_MESES = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}
_DATA_EXTENSO = re.compile(r"^rio de janeiro, (\d{1,2})o? de ([a-z]+) de (\d{4})\b")

Recortador = Callable[[Mapping[str, Any]], dict[str, Any] | None]


def _folhas(raiz: etree._Element) -> Iterator[etree._Element]:
    """Blocos sem outro bloco dentro, na ordem do documento."""
    for el in raiz.iter():
        if not isinstance(el.tag, str) or el.tag not in _BLOCOS:
            continue
        if any(isinstance(d.tag, str) and d.tag in _BLOCOS for d in el.iterdescendants()):
            continue
        yield el


def _texto(el: etree._Element) -> str:
    for br in el.iter("br"):
        br.tail = "\n" + (br.tail or "")
    conteudo = etree.tostring(el, method="text", encoding="unicode", with_tail=False)
    linhas = decodificar(conteudo).split("\n")
    return "\n".join(" ".join(linha.split()) for linha in linhas).strip()


def _data(chaves: list[str]) -> str | None:
    """``dd/mm/aaaa`` da linha "Rio de Janeiro, 5 de novembro de 2026."."""
    for valor in chaves:
        m = _DATA_EXTENSO.match(valor)
        if m and m.group(2) in _MESES:
            return f"{int(m.group(1)):02d}/{_MESES[m.group(2)]:02d}/{m.group(3)}"
    return None


def recortar_eproc(texto_html: str) -> str | None:
    """Tabela com a data do julgamento e a ementa, ou ``None`` se o formato não bater."""
    if not texto_html or not texto_html.strip():
        return None
    try:
        raiz = lxml_html.fragment_fromstring(texto_html, create_parent="div")
    except (etree.ParserError, ValueError):
        return None
    blocos = [b for b in (_texto(el) for el in _folhas(raiz)) if b]
    chaves = [chave(b).rstrip(":").strip() for b in blocos]
    inicio = next((i for i, c in enumerate(chaves) if c == "ementa"), None)
    if inicio is None:
        return None
    fim = next((i for i in range(inicio + 1, len(chaves)) if chaves[i] == "acordao"), None)
    if fim is None or fim == inicio + 1:
        return None
    ementa = "".join(f"<p>{html.escape(b)}</p>" for b in blocos[inicio + 1 : fim])
    data = _data(chaves[fim + 1 :])
    linha_data = f"<tr><td>Data do Julgamento:</td><td>{data}</td></tr>" if data is not None else ""
    return f'<table>{linha_data}<tr><td colspan="2">Ementa: {ementa}</td></tr></table>'


def recortar_tjrj(comunicacao: Mapping[str, Any]) -> dict[str, Any] | None:
    """Comunicação com o ``texto`` recortado; ``None`` descarta o item (falha de parser)."""
    recortado = recortar_eproc(str(comunicacao.get("texto") or ""))
    if recortado is None:
        return None
    return {**comunicacao, "texto": recortado}


# Tribunais cujo ``texto`` precisa de recorte antes da anonimização.
RECORTADORES: Mapping[str, Recortador] = {"TJRJ": recortar_tjrj}
