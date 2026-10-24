"""NER falso para os testes: "reconhece" uma lista fixa de nomes, como um modelo faria."""

from collections.abc import Sequence

from buscajus.ingest.anonimizacao.camada2 import Entidade
from buscajus.ingest.anonimizacao.nomes import trechos_protegidos
from fixtures.djen import dados

# O falso detecta as vítimas e testemunhas (camada 2) e também nomes que precisam ficar,
# para provar que as exceções funcionam: relatores, ministro citado, epônimo.
NOMES_DETECTADOS = (
    *dados.NOMES_CAMADA_2,
    *dados.RELATORES,
    "Bonifácio Cardeal",
    "Maria da Penha",
)


class DetectorFalso:
    versao = "falso-1"

    def __init__(self, nomes: Sequence[str] = NOMES_DETECTADOS) -> None:
        self._nomes = tuple(nomes)
        self.chamadas = 0

    def detectar(self, texto: str) -> Sequence[Entidade]:
        self.chamadas += 1
        return [Entidade(i, f) for i, f in trechos_protegidos(texto, self._nomes)]
