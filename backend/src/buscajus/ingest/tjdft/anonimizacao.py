"""Anonimização do TJDFT (F2-12; ARCHITECTURE.md, seção 6.3).

Mesmo contrato do DJEN (:class:`~buscajus.ingest.anonimizacao.Anonimizador`), aplicado à
ementa e à decisão (dispositivo) de cada registro aceito, antes de qualquer gravação:

1. camada 2: NER de pessoas → iniciais, pela mesma interface ``DetectorPessoas`` e com as
   mesmas exceções (magistrados do próprio acórdão, títulos de magistrado em precedentes,
   epônimos);
2. mascaramento de CPF (F1-39);
3. invariante: nenhum CPF sem máscara; se sobrar, o registro é recusado (:class:`Rejeicao`) e
   só o uuid é contado.

Não há camada 1: a API do TJDFT não traz partes nem destinatários. O texto é puro (sem HTML).
Sem detector de NER não há anonimizador: :func:`criar_anonimizador` falha antes de qualquer
acesso à fonte, para que nada real seja gravado sem a camada 2.
"""

from collections.abc import Mapping
from typing import Any

from buscajus.ingest.anonimizacao import Rejeicao
from buscajus.ingest.anonimizacao import camada2 as c2
from buscajus.ingest.anonimizacao.cpf import mascarar_cpf, tem_cpf
from buscajus.ingest.anonimizacao.pipeline import LIMITE_SUBSTITUICOES, ErroAnonimizacao
from buscajus.ingest.relator import normalizar_relator
from buscajus.ingest.texto import decodificar

VERSAO = "cpf-1"
CAMPOS_TEXTO = ("ementa", "decisao")
# Magistrados do próprio acórdão: agentes públicos no exercício da função, ficam no texto.
CAMPOS_MAGISTRADOS = ("nomeRelator", "nomeRelatorDesignado", "nomeRevisor")


def magistrados(registro: Mapping[str, Any]) -> list[str]:
    nomes = []
    for campo in CAMPOS_MAGISTRADOS:
        valor = registro.get(campo)
        relator = normalizar_relator(valor) if isinstance(valor, str) else None
        if relator and relator.chave:
            nomes.append(relator.chave)
    return nomes


class AnonimizadorTjdft:
    def __init__(self, detector: c2.DetectorPessoas) -> None:
        self._detector = detector
        self.versao = f"{VERSAO}+ner-{detector.versao}"

    def __call__(self, item: Mapping[str, Any]) -> dict[str, Any] | Rejeicao:
        uuid = str(item.get("uuid"))
        protegidos = magistrados(item)
        saida = dict(item)
        total = 0
        for campo in CAMPOS_TEXTO:
            valor = item.get(campo)
            if valor is None:
                continue
            if not isinstance(valor, str):
                return Rejeicao(uuid, "texto em formato inesperado")
            texto, pessoas = c2.aplicar(decodificar(valor), self._detector, protegidos)
            texto, cpfs = mascarar_cpf(texto)
            if tem_cpf(texto):
                return Rejeicao(uuid, "CPF restante no texto")
            saida[campo] = texto
            total += pessoas + cpfs
        saida["anonimizacao_versao"] = self.versao
        saida["anonimizacao_substituicoes"] = min(total, LIMITE_SUBSTITUICOES)
        return saida


def criar_anonimizador(detector: c2.DetectorPessoas | None) -> AnonimizadorTjdft:
    """Falha fechada: sem NER configurado, nada do TJDFT é processado nem gravado."""
    if detector is None:
        raise ErroAnonimizacao(
            "nenhum modelo de NER configurado (camada 2): o pipeline não processa dados "
            "reais sem ela (F1-36/F1-37)"
        )
    return AnonimizadorTjdft(detector)
