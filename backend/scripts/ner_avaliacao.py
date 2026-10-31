"""F1-36: avaliação de modelos locais de NER de pessoas, **só com ementas sintéticas**.

Lê o conjunto anotado de ``tests/fixtures/ner`` (nomes fictícios; nenhum dado real) e mede,
para cada modelo e limiar, quantos nomes a anonimizar escapam e quantos nomes que devem ficar
(relator, magistrados citados, epônimos) são preservados, já com as exceções da camada 2.

Marcação das fixtures:

- ``[[Nome]]``: pessoa física que deve ser anonimizada;
- ``{{Nome}}``: nome que deve ficar.

Uso (de ``backend/``; os modelos são baixados para o cache do Hugging Face da máquina)::

    uv run --group ner --with "spacy>=3.8,<3.9" python scripts/ner_avaliacao.py \\
        --spacy-modelo pt_core_news_lg --saida relatorio.md

O spaCy e o seu modelo (``python -m spacy download pt_core_news_lg``) só são usados aqui; o
pipeline usa o detector de ``buscajus.ingest.anonimizacao.modelo_ner``.
"""

import argparse
import re
import statistics
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tests"))

from buscajus.core.config import ConfigAnonimizacao
from buscajus.ingest.anonimizacao.camada2 import Entidade, selecionar
from buscajus.ingest.anonimizacao.modelo_ner import (
    DetectorTransformers,
    juntar_palavras,
)
from buscajus.ingest.anonimizacao.nomes import PARTICULAS, alinhado
from fixtures.ner import EMENTAS

MARCACAO = re.compile(r"\[\[(.+?)\]\]|\{\{(.+?)\}\}", re.DOTALL)
CANDIDATOS_HF = (
    ("Luciano/bertimbau-base-lener_br", "824f48e1b86fe24a86bd5f845f068c60468274a7"),
    ("Luciano/bertimbau-large-lener_br", "c515eb0a38f2f464d0fdfd7d27049989aa83e1bc"),
    ("pierreguillou/ner-bert-base-cased-pt-lenerbr", "4ca0a39767b49788a93b59b632b19f614d12e26c"),
)
LIMIARES = (0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9)


@dataclass(frozen=True)
class Marca:
    inicio: int
    fim: int
    anonimizar: bool


def ler_marcacao(anotado: str) -> tuple[str, list[Marca]]:
    partes: list[str] = []
    marcas: list[Marca] = []
    tamanho = 0
    ultimo = 0
    for m in MARCACAO.finditer(anotado):
        antes = anotado[ultimo : m.start()]
        partes.append(antes)
        tamanho += len(antes)
        nome = m.group(1) if m.group(1) is not None else m.group(2)
        marcas.append(Marca(tamanho, tamanho + len(nome), m.group(1) is not None))
        partes.append(nome)
        tamanho += len(nome)
        ultimo = m.end()
    partes.append(anotado[ultimo:])
    return "".join(partes), marcas


def _tokens(texto: str, inicio: int, fim: int) -> list[tuple[int, int]]:
    trecho = alinhado(texto[inicio:fim])
    return [
        (inicio + m.start(), inicio + m.end())
        for m in re.finditer(r"[A-Z0-9]+", trecho)
        if m.group() not in PARTICULAS and len(m.group()) > 1
    ]


def _coberto(token: tuple[int, int], previstas: Sequence[Entidade]) -> bool:
    return any(p.inicio <= token[0] and token[1] <= p.fim for p in previstas)


@dataclass
class Placar:
    ementas: int = 0
    anonimizar: int = 0
    anonimizar_total: int = 0  # todos os tokens do nome substituídos
    anonimizar_parcial: int = 0  # pelo menos um token substituído
    manter: int = 0
    manter_preservados: int = 0
    previstas: int = 0
    previstas_corretas: int = 0

    def somar(self, texto: str, marcas: Sequence[Marca], previstas: Sequence[Entidade]) -> None:
        self.ementas += 1
        for marca in marcas:
            tokens = _tokens(texto, marca.inicio, marca.fim)
            cobertos = [t for t in tokens if _coberto(t, previstas)]
            if marca.anonimizar:
                self.anonimizar += 1
                self.anonimizar_total += bool(tokens) and len(cobertos) == len(tokens)
                self.anonimizar_parcial += bool(cobertos)
            else:
                self.manter += 1
                self.manter_preservados += not cobertos
        ouro = [m for m in marcas if m.anonimizar]
        self.previstas += len(previstas)
        self.previstas_corretas += sum(
            any(p.inicio < m.fim and m.inicio < p.fim for m in ouro) for p in previstas
        )

    @property
    def vazados(self) -> int:
        return self.anonimizar - self.anonimizar_total

    def linha(self) -> dict[str, str]:
        def taxa(a: int, b: int) -> str:
            return f"{a / b:.3f}" if b else "-"

        return {
            "nomes": str(self.anonimizar),
            "vazados": str(self.vazados),
            "recall (nome inteiro)": taxa(self.anonimizar_total, self.anonimizar),
            "recall (algum token)": taxa(self.anonimizar_parcial, self.anonimizar),
            "precisão": taxa(self.previstas_corretas, self.previstas),
            "manter preservados": f"{self.manter_preservados}/{self.manter}",
        }


Detectar = Callable[[str], Sequence[Entidade]]


def avaliar(detectar: Detectar) -> tuple[dict[str, Placar], float]:
    placares: dict[str, Placar] = {}
    tempos: list[float] = []
    for ementa in EMENTAS:
        texto, marcas = ler_marcacao(ementa.texto)
        inicio = time.perf_counter()
        brutas = detectar(texto)
        tempos.append(time.perf_counter() - inicio)
        previstas = selecionar(texto, brutas, [ementa.relator] if ementa.relator else [])
        for chave in (ementa.estrato, "total"):
            placares.setdefault(chave, Placar()).somar(texto, marcas, previstas)
    return placares, statistics.mean(tempos)


def tabela(linhas: Sequence[tuple[str, dict[str, str]]]) -> str:
    colunas = list(linhas[0][1])
    saida = ["| | " + " | ".join(colunas) + " |", "|---" * (len(colunas) + 1) + "|"]
    saida += [
        f"| {rotulo} | " + " | ".join(dados[c] for c in colunas) + " |" for rotulo, dados in linhas
    ]
    return "\n".join(saida)


def detector_hf(nome: str, revisao: str, caixa: bool) -> DetectorTransformers:
    from transformers import AutoModelForTokenClassification, AutoTokenizer

    tokenizador = AutoTokenizer.from_pretrained(nome, revision=revisao)
    modelo = AutoModelForTokenClassification.from_pretrained(nome, revision=revisao)
    return DetectorTransformers(modelo, tokenizador, versao=nome, limiar=0.5, caixa=caixa)


def detector_spacy(nome: str) -> Detectar:
    import spacy

    nlp = spacy.load(nome)

    def detectar(texto: str) -> list[Entidade]:
        return [
            Entidade(e.start_char, e.end_char)
            for e in nlp(texto).ents
            if e.label_ in {"PER", "PERSON", "PESSOA"}
        ]

    return detectar


def secoes_hf(nome: str, revisao: str) -> Iterable[tuple[str, dict[str, str], float]]:
    for caixa in (False, True):
        detector = detector_hf(nome, revisao, caixa)
        cache: dict[str, list[object]] = {}

        def palavras(
            texto: str, d: DetectorTransformers = detector, cache: dict[str, list[object]] = cache
        ) -> list[object]:
            if texto not in cache:
                inicio = time.perf_counter()
                cache[texto] = [d.palavras(texto), time.perf_counter() - inicio]
            return cache[texto]

        for limiar in LIMIARES:

            def detectar(texto: str, limiar: float = limiar) -> Sequence[Entidade]:
                ps, _ = palavras(texto)
                return juntar_palavras(texto, ps, limiar)  # type: ignore[arg-type]

            placares, _ = avaliar(detectar)
            tempo = statistics.mean(float(v[1]) for v in cache.values())  # type: ignore[arg-type]
            rotulo = f"limiar {limiar:g}, {'com' if caixa else 'sem'} variante de caixa"
            yield rotulo, placares["total"].linha(), tempo


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--spacy-modelo", default="pt_core_news_lg")
    parser.add_argument("--sem-spacy", action="store_true")
    args = parser.parse_args()

    marcas = [ler_marcacao(e.texto)[1] for e in EMENTAS]
    secoes = [
        f"Conjunto sintético: {len(EMENTAS)} ementas, "
        f"{sum(m.anonimizar for ms in marcas for m in ms)} nomes a anonimizar, "
        f"{sum(not m.anonimizar for ms in marcas for m in ms)} nomes a manter.",
        "",
    ]
    if not args.sem_spacy:
        placares, tempo = avaliar(detector_spacy(args.spacy_modelo))
        secoes += [
            f"### spaCy `{args.spacy_modelo}`",
            "",
            tabela([(e, p.linha()) for e, p in placares.items()]),
            "",
            f"Tempo médio por ementa: {tempo * 1000:.0f} ms (CPU).",
            "",
        ]
    for nome, revisao in CANDIDATOS_HF:
        linhas = list(secoes_hf(nome, revisao))
        secoes += [
            f"### `{nome}` (revisão `{revisao[:7]}`)",
            "",
            tabela([(rotulo, dados) for rotulo, dados, _ in linhas]),
            "",
            "Tempo médio por ementa (CPU): "
            + ", ".join(
                f"{rotulo.split(', ')[1]}: {tempo * 1000:.0f} ms"
                for rotulo, _, tempo in linhas
                if rotulo.startswith(f"limiar {LIMIARES[0]:g},")
            )
            + ".",
            "",
        ]
    escolhido = ConfigAnonimizacao()
    if escolhido.modelo_ner and escolhido.revisao_ner:
        detector = detector_hf(escolhido.modelo_ner, escolhido.revisao_ner, escolhido.caixa_ner)
        detector.limiar = escolhido.limiar_ner
        placares, tempo = avaliar(detector.detectar)
        secoes += [
            f"### Configuração escolhida, por estrato (`{escolhido.modelo_ner}`, limiar "
            f"{escolhido.limiar_ner:g}, {'com' if escolhido.caixa_ner else 'sem'} variante de "
            "caixa)",
            "",
            tabela([(e, p.linha()) for e, p in placares.items()]),
            "",
        ]
    args.saida.write_text("\n".join(secoes), encoding="utf-8")
    print(f"relatório gravado em {args.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
