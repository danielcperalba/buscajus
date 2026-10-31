"""Modelo de NER da camada 2 (F1-36, F1-37; ARCHITECTURE.md, seção 6.3).

O detector usa um modelo de classificação de tokens do Hugging Face treinado no LeNER-Br,
**sem treino próprio**, com nome e revisão fixados na configuração. Os pesos ficam no volume
de modelos (``diretorio_modelos``) e são baixados só por ``buscajus modelos baixar-ner``;
o carregamento é sempre ``local_files_only``: nada é baixado em tempo de execução.

Como o recall é o que importa, o detector não usa o rótulo mais provável de cada token, e sim
a **probabilidade de pessoa** (soma de ``B-PESSOA`` e ``I-PESSOA``) de cada palavra, comparada
com ``anonimizacao.limiar_ner``. Para nomes em caixa alta (que modelos *cased* reconhecem mal),
o texto também é lido numa variante com as palavras em maiúsculas trocadas por iniciais
maiúsculas, com o mesmo comprimento; vale a maior probabilidade das duas leituras. Ementas
longas são lidas em janelas de ``max_tokens`` com sobreposição.

Sem modelo configurado, ou sem os pesos no volume, não há detector e o pipeline não é criado
(falha fechada).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from buscajus.core.config import ConfigAnonimizacao
from buscajus.ingest.anonimizacao.camada2 import DetectorPessoas, Entidade
from buscajus.ingest.anonimizacao.nomes import PARTICULAS, alinhado
from buscajus.ingest.anonimizacao.pipeline import ErroAnonimizacao

ROTULOS_PESSOA = frozenset({"PESSOA", "PER", "PERSON"})
# Arquivos do repositório do modelo que vão para o volume (sem os pesos em pickle).
ARQUIVOS_MODELO = (
    "config.json",
    "model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.txt",
)
# Entre duas palavras de um mesmo nome: espaço, apóstrofo ("D'Arc") ou hífen.
_PONTE = re.compile(r"[\s'’-]*")
# "e" não une: "Fulano e Beltrano" são duas pessoas.
_PARTICULAS_PONTE = PARTICULAS - {"E"}
_PALAVRA_MAIUSCULA = re.compile(r"\b[^\W\d_]{2,}\b")


@dataclass(frozen=True)
class Palavra:
    inicio: int
    fim: int
    probabilidade: float


def variante_caixa(texto: str) -> str:
    """Palavras em maiúsculas → iniciais maiúsculas, com o mesmo comprimento do texto."""

    def trocar(m: re.Match[str]) -> str:
        palavra = m.group()
        if not palavra.isupper():
            return palavra
        nova = palavra.lower() if alinhado(palavra) in PARTICULAS else palavra.capitalize()
        return nova if len(nova) == len(palavra) else palavra

    return _PALAVRA_MAIUSCULA.sub(trocar, texto)


def juntar_palavras(texto: str, palavras: Sequence[Palavra], limiar: float) -> list[Entidade]:
    """Palavras com probabilidade ≥ limiar viram entidades; partículas no meio são unidas."""
    entidades: list[Entidade] = []
    atual: list[int] | None = None  # [inicio, fim] da entidade em formação
    pendente: int | None = None  # fim da última partícula depois da entidade atual
    for palavra in sorted(palavras, key=lambda p: p.inicio):
        trecho = texto[palavra.inicio : palavra.fim]
        pessoa = palavra.probabilidade >= limiar and any(c.isalpha() for c in trecho)
        fim_atual = pendente if pendente is not None else (atual[1] if atual else 0)
        contigua = atual is not None and _PONTE.fullmatch(texto[fim_atual : palavra.inicio])
        if pessoa and contigua and atual is not None:
            atual[1] = palavra.fim
            pendente = None
        elif pessoa:
            if atual:
                entidades.append(Entidade(atual[0], atual[1]))
            atual, pendente = [palavra.inicio, palavra.fim], None
        elif contigua and (alinhado(trecho) in _PARTICULAS_PONTE or trecho in ("'", "’", "-")):
            pendente = palavra.fim
        else:
            if atual:
                entidades.append(Entidade(atual[0], atual[1]))
            atual, pendente = None, None
    if atual:
        entidades.append(Entidade(atual[0], atual[1]))
    return entidades


class DetectorTransformers:
    """Detector de pessoas sobre um modelo de classificação de tokens (``transformers``)."""

    def __init__(
        self,
        modelo: Any,
        tokenizador: Any,
        *,
        versao: str,
        limiar: float,
        caixa: bool = True,
        max_tokens: int = 512,
        sobreposicao: int = 128,
    ) -> None:
        self._modelo = modelo.eval()
        self._tokenizador = tokenizador
        self.versao = versao
        self.limiar = limiar
        self._caixa = caixa
        self._max_tokens = max_tokens
        self._sobreposicao = sobreposicao
        rotulos: dict[int, str] = modelo.config.id2label
        self._indices_pessoa = [
            int(i) for i, r in rotulos.items() if r.split("-", 1)[-1].upper() in ROTULOS_PESSOA
        ]
        if not self._indices_pessoa:
            raise ErroAnonimizacao("o modelo de NER não tem rótulo de pessoa")

    def _probabilidades(self, texto: str) -> dict[tuple[int, int], float]:
        import torch  # dependência do grupo "ner"

        codificado = self._tokenizador(
            texto,
            truncation=True,
            max_length=self._max_tokens,
            stride=self._sobreposicao,
            return_overflowing_tokens=True,
            return_offsets_mapping=True,
            padding=True,
            return_tensors="pt",
        )
        offsets = codificado.pop("offset_mapping")
        codificado.pop("overflow_to_sample_mapping", None)
        with torch.inference_mode():
            logits = self._modelo(**codificado).logits
        probs = torch.softmax(logits, dim=-1)[..., self._indices_pessoa].sum(dim=-1)
        palavras: dict[tuple[int, int], float] = {}
        for janela in range(probs.shape[0]):
            ids = codificado.word_ids(janela)
            por_palavra: dict[int, list[float]] = {}  # palavra → [inicio, fim, prob]
            for posicao, palavra in enumerate(ids):
                if palavra is None:
                    continue
                inicio, fim = (int(v) for v in offsets[janela][posicao])
                if fim <= inicio:
                    continue
                p = float(probs[janela][posicao])
                atual = por_palavra.setdefault(palavra, [inicio, fim, p])
                atual[0], atual[1], atual[2] = (
                    min(atual[0], inicio),
                    max(atual[1], fim),
                    max(atual[2], p),
                )
            for inicio_f, fim_f, p in por_palavra.values():
                chave = (int(inicio_f), int(fim_f))
                palavras[chave] = max(palavras.get(chave, 0.0), p)
        return palavras

    def palavras(self, texto: str) -> list[Palavra]:
        """Cada palavra com a maior probabilidade de pessoa entre as leituras do texto."""
        if not texto.strip():
            return []
        leituras = [texto]
        if self._caixa:
            variante = variante_caixa(texto)
            if variante != texto:
                leituras.append(variante)
        juntas: dict[tuple[int, int], float] = {}
        for leitura in leituras:
            for chave, p in self._probabilidades(leitura).items():
                juntas[chave] = max(juntas.get(chave, 0.0), p)
        return [Palavra(i, f, p) for (i, f), p in juntas.items()]

    def detectar(self, texto: str) -> Sequence[Entidade]:
        return juntar_palavras(texto, self.palavras(texto), self.limiar)


def _diretorio(diretorio_modelos: Path) -> Path:
    return diretorio_modelos / "ner"


def versao_detector(config: ConfigAnonimizacao) -> str:
    """Nome curto para ``anonimizacao_versao``: modelo, revisão (7 caracteres) e limiar."""
    nome = (config.modelo_ner or "").rsplit("/", 1)[-1]
    return f"{nome}@{(config.revisao_ner or '')[:7]}-l{config.limiar_ner:g}"


def carregar_detector(
    config: ConfigAnonimizacao, diretorio_modelos: Path
) -> DetectorPessoas | None:
    """Detector a partir dos pesos já no volume; ``None`` se não houver modelo configurado."""
    if not config.modelo_ner:
        return None
    if not config.revisao_ner:
        raise ErroAnonimizacao("modelo de NER sem revisão fixada (anonimizacao.revisao_ner)")
    try:
        from transformers import AutoModelForTokenClassification, AutoTokenizer
    except ModuleNotFoundError as exc:
        raise ErroAnonimizacao(
            "o modelo de NER exige o grupo opcional de dependências (uv sync --group ner)"
        ) from exc
    opcoes = {
        "revision": config.revisao_ner,
        "cache_dir": str(_diretorio(diretorio_modelos)),
        "local_files_only": True,
    }
    try:
        tokenizador = AutoTokenizer.from_pretrained(config.modelo_ner, **opcoes)
        modelo = AutoModelForTokenClassification.from_pretrained(config.modelo_ner, **opcoes)
    except OSError as exc:
        raise ErroAnonimizacao(
            "pesos do modelo de NER ausentes no volume de modelos: rode "
            "`buscajus modelos baixar-ner` (nada é baixado em tempo de execução)"
        ) from exc
    return DetectorTransformers(
        modelo,
        tokenizador,
        versao=versao_detector(config),
        limiar=config.limiar_ner,
        caixa=config.caixa_ner,
    )


def baixar_modelo(config: ConfigAnonimizacao, diretorio_modelos: Path) -> Path:
    """Baixa a revisão fixada para o volume de modelos (passo explícito de implantação)."""
    if not config.modelo_ner or not config.revisao_ner:
        raise ErroAnonimizacao("modelo de NER ou revisão não configurados")
    from huggingface_hub import snapshot_download

    caminho = snapshot_download(
        config.modelo_ner,
        revision=config.revisao_ner,
        cache_dir=str(_diretorio(diretorio_modelos)),
        allow_patterns=list(ARQUIVOS_MODELO),
    )
    return Path(caminho)
