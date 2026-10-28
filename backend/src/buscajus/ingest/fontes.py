"""Registro das fontes de dados (F7-04).

Cada fonte tem um identificador (o mesmo do tipo ``fonte`` do Postgres), um nome para exibição
e o link da origem. Adicionar uma fonte nova é: entrada aqui, ``ALTER TYPE fonte ADD VALUE``
numa migração (não destrutivo) e um conector que implemente o protocolo (docs/nova-fonte.md).
A cobertura (acórdãos e período por tribunal) é lida do banco e exibida em /sobre.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FonteDados:
    id: str
    nome: str
    url: str
    descricao: str


FONTES: dict[str, FonteDados] = {
    "djen": FonteDados(
        id="djen",
        nome="Diário de Justiça Eletrônico Nacional (DJEN)",
        url="https://comunica.pje.jus.br/",
        descricao="Ementas de acórdãos publicadas no caderno diário do CNJ.",
    ),
    "tjdft": FonteDados(
        id="tjdft",
        nome="Jurisprudência do TJDFT",
        url="https://jurisdf.tjdft.jus.br/",
        descricao="Acórdãos da API pública de jurisprudência do TJDFT.",
    ),
}
