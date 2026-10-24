"""Pipeline de anonimização do DJEN (F1-35, F1-38; ARCHITECTURE.md, seção 6.3).

Ordem obrigatória, antes de qualquer gravação, inclusive a do bruto:

1. classificação PF × PJ dos destinatários e advogados (só em memória);
2. camada 1: nomes PF e ambíguos da própria comunicação → iniciais;
3. camada 2: NER de pessoas → iniciais (com as exceções da camada 2);
4. mascaramento de CPF;
5. invariante: nenhum nome PF/ambíguo nem CPF sem máscara sobrou; se sobrou, o item é
   recusado (:class:`Rejeicao`) e não é gravado;
6. lista branca: ``destinatarios`` e ``destinatarioadvogados`` são descartados.

O texto é HTML: as substituições são feitas nos nós de texto (com as entidades decodificadas)
e o HTML é re-serializado. As linhas do cabeçalho com rótulos de metadados (processo,
relator, órgão, data) não são alteradas pelas camadas de nomes.

Sem detector de NER não há pipeline: :func:`criar_anonimizador` falha antes de qualquer
download, para que nada real seja gravado sem a camada 2.
"""

import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from lxml import etree
from lxml import html as lxml_html

from buscajus.core.erros import ErroSeguro
from buscajus.ingest.anonimizacao import Rejeicao
from buscajus.ingest.anonimizacao import camada2 as c2
from buscajus.ingest.anonimizacao.classificacao import classificar
from buscajus.ingest.anonimizacao.cpf import mascarar_cpf, tem_cpf
from buscajus.ingest.anonimizacao.nomes import Casador, sobrepoe, substituir, trechos_protegidos
from buscajus.ingest.djen.campos import LISTA_BRANCA
from buscajus.ingest.relator import normalizar_relator
from buscajus.ingest.texto import chave, decodificar

VERSAO = "c1-1+cpf-1"
LIMITE_SUBSTITUICOES = 32767  # coluna smallint

# Rótulos de metadados do cabeçalho: a linha inteira fica intacta para as camadas de nomes.
ROTULOS_PROTEGIDOS = frozenset(
    {
        "processo",
        "relator",
        "relator(a)",
        "relatora",
        "orgao julgador",
        "data do julgamento",
        "data de julgamento",
    }
)
_ROTULO = re.compile(r"^\s*([^:]{2,40}):")
_TAMANHO_MAXIMO_LINHA_PROTEGIDA = 300


class ErroAnonimizacao(ErroSeguro):
    pass


def _texto(el: etree._Element) -> str:
    return decodificar("".join(str(t) for t in el.itertext()))


def _rotulo(el: etree._Element) -> str | None:
    m = _ROTULO.match(_texto(el))
    return chave(m.group(1)) if m else None


def _linhas_protegidas(raiz: etree._Element) -> tuple[set[etree._Element], str | None]:
    """Linhas de cabeçalho a preservar e o nome do relator (para protegê-lo no corpo)."""
    protegidas: set[etree._Element] = set()
    relator: str | None = None
    for el in raiz.iter("tr", "p", "div"):
        if el is raiz:
            continue
        if el.tag == "tr":
            celulas = [c for c in el if isinstance(c.tag, str) and c.tag in ("td", "th")]
            if not celulas:
                continue
            rotulo = _rotulo(celulas[0])
            valor = " ".join(_texto(c) for c in celulas[1:]) if len(celulas) > 1 else None
        else:
            # Só uma linha isolada de cabeçalho: sem blocos ou quebras dentro dela.
            if len(_texto(el)) > _TAMANHO_MAXIMO_LINHA_PROTEGIDA or any(
                d.tag in ("p", "div", "table", "tr", "br") for d in el.iterdescendants()
            ):
                continue
            rotulo = _rotulo(el)
            valor = None
        if rotulo not in ROTULOS_PROTEGIDOS:
            continue
        protegidas.add(el)
        if rotulo.startswith("relator"):
            bruto = valor if valor is not None else _texto(el).split(":", 1)[1]
            normalizado = normalizar_relator(bruto)
            relator = normalizado.chave if normalizado else None
    return protegidas, relator


def _protegido(el: etree._Element | None, protegidas: set[etree._Element]) -> bool:
    while el is not None:
        if el in protegidas:
            return True
        el = el.getparent()
    return False


def _nos_de_texto(
    raiz: etree._Element, protegidas: set[etree._Element]
) -> Iterable[tuple[etree._Element, str, bool]]:
    """(elemento, "text"|"tail", protegido) para cada nó de texto não vazio."""
    for el in list(raiz.iter()):
        if isinstance(el.tag, str) and el.text:
            yield el, "text", _protegido(el, protegidas)
        if el is not raiz and el.tail:
            yield el, "tail", _protegido(el.getparent(), protegidas)


def _serializar(raiz: etree._Element) -> str:
    partes = [raiz.text or ""]
    partes += [etree.tostring(filho, encoding="unicode", method="html") for filho in raiz]
    return "".join(partes)


def nomes_a_substituir(item: Mapping[str, Any]) -> list[str]:
    """Nomes PF e ambíguos dos destinatários e advogados da comunicação."""
    brutos: list[str] = []
    for destinatario in item.get("destinatarios") or []:
        if isinstance(destinatario, Mapping) and isinstance(destinatario.get("nome"), str):
            brutos.append(destinatario["nome"])
    for vinculo in item.get("destinatarioadvogados") or []:
        advogado = vinculo.get("advogado") if isinstance(vinculo, Mapping) else None
        if isinstance(advogado, Mapping) and isinstance(advogado.get("nome"), str):
            brutos.append(advogado["nome"])
    nomes = []
    for bruto in brutos:
        classificacao = classificar(bruto)
        if classificacao.substituir and classificacao.nome:
            nomes.append(classificacao.nome)
    return nomes


class AnonimizadorDjen:
    def __init__(self, detector: c2.DetectorPessoas) -> None:
        self._detector = detector
        self.versao = f"{VERSAO}+ner-{detector.versao}"

    def __call__(self, item: Mapping[str, Any]) -> dict[str, Any] | Rejeicao:
        id_comunicacao = str(item.get("id"))
        texto = item.get("texto")
        if not isinstance(texto, str) or not texto.strip():
            return Rejeicao(id_comunicacao, "comunicação sem texto")
        nomes = nomes_a_substituir(item)
        try:
            novo_texto, substituicoes = self.anonimizar_html(texto, nomes)
        except (etree.ParserError, ValueError):
            return Rejeicao(id_comunicacao, "HTML não pôde ser lido")
        if novo_texto is None:
            return Rejeicao(id_comunicacao, "nome de destinatário ou CPF restante no texto")
        # Lista branca: só agora os destinatários deixam de existir.
        limpo = {campo: valor for campo, valor in item.items() if campo in LISTA_BRANCA}
        limpo["texto"] = novo_texto
        limpo["anonimizacao_versao"] = self.versao
        limpo["anonimizacao_substituicoes"] = min(substituicoes, LIMITE_SUBSTITUICOES)
        return limpo

    def anonimizar_html(self, texto: str, nomes: list[str]) -> tuple[str | None, int]:
        """Texto anonimizado e número de substituições; ``None`` se a invariante falhar."""
        raiz = lxml_html.fragment_fromstring(texto, create_parent="div")
        protegidas, relator = _linhas_protegidas(raiz)
        protegidos = [relator] if relator else []
        casador = Casador(nomes)
        total = 0
        for el, atributo, protegido in _nos_de_texto(raiz, protegidas):
            valor = decodificar(getattr(el, atributo))
            if not protegido:
                valor, n1 = substituir(valor, casador, protegidos)
                valor, n2 = c2.aplicar(valor, self._detector, protegidos)
                total += n1 + n2
            valor, n3 = mascarar_cpf(valor)
            total += n3
            setattr(el, atributo, valor)

        if not _invariante(raiz, protegidas, casador, protegidos):
            return None, total
        return _serializar(raiz), total


def _invariante(
    raiz: etree._Element,
    protegidas: set[etree._Element],
    casador: Casador,
    protegidos: list[str],
) -> bool:
    """Nenhum nome PF/ambíguo e nenhum CPF em lugar nenhum do texto.

    Vale também para as linhas protegidas do cabeçalho: um nome de parte ali faz o item ser
    recusado. Só o relator e os epônimos ficam de fora.
    """
    valores = [
        decodificar(getattr(el, atributo)) for el, atributo, _ in _nos_de_texto(raiz, protegidas)
    ]
    if any(tem_cpf(valor) for valor in valores):
        return False
    # Cada nó e o texto corrido (nomes partidos entre nós, ex.: "<b>JOÃO</b> SILVA").
    for valor in [*valores, " ".join(valores)]:
        trechos = trechos_protegidos(valor, (*c2.EPONIMOS, *protegidos))
        if any(not sobrepoe(o.inicio, o.fim, trechos) for o in casador.encontrar(valor)):
            return False
    return True


FabricaDetector = Callable[[], c2.DetectorPessoas]


def criar_anonimizador(detector: c2.DetectorPessoas | None) -> AnonimizadorDjen:
    """Falha fechada: sem NER configurado, nada é processado nem gravado."""
    if detector is None:
        raise ErroAnonimizacao(
            "nenhum modelo de NER configurado (camada 2): o pipeline não processa dados "
            "reais sem ela (F1-36/F1-37)"
        )
    return AnonimizadorDjen(detector)
