"""Carregamento do modelo de NER (camada 2) a partir da configuração.

O modelo é escolhido no F1-36 e implementado no F1-37. Até lá, não há detector: com
``anonimizacao.modelo_ner`` vazio devolve ``None`` e o pipeline não é criado (falha fechada).
"""

from buscajus.core.config import ConfigAnonimizacao
from buscajus.ingest.anonimizacao.camada2 import DetectorPessoas
from buscajus.ingest.anonimizacao.pipeline import ErroAnonimizacao


def carregar_detector(config: ConfigAnonimizacao) -> DetectorPessoas | None:
    if not config.modelo_ner:
        return None
    raise ErroAnonimizacao(
        f"modelo de NER {config.modelo_ner!r} ainda não implementado (F1-37, depende do F1-36)"
    )
