"""Geração da citação (F4-10; ARCHITECTURE.md, seção 9).

    DJEN:  {TRIBUNAL}, {órgão}, {classe} nº {número}, Rel. {relator}[, j. {data}], DJEN de {data}.
    TJDFT: {TRIBUNAL}, {órgão}, {classe} nº {número}, Rel. {relator} | Rel. p/ acórdão {designado}
           [, j. {data}][, publ. {local} {data}].

- ``{classe}`` é ``classe_citacao`` (DJEN: a do cabeçalho; TJDFT: o nome da TPU); sem ela,
  ``classe_nome``.
- No DJEN, ``DJEN de`` usa a data de disponibilização; a de publicação não é calculada.
- No TJDFT, com relator designado, ``Rel. p/ acórdão`` com ele, no lugar do relator original.
- Partes ausentes saem junto com o separador (nunca "Rel. None"). Datas em ``dd/mm/aaaa``.
"""

from collections.abc import Mapping
from datetime import date
from typing import Any


def _data(valor: date | None) -> str | None:
    return valor.strftime("%d/%m/%Y") if valor else None


def citar(acordao: Mapping[str, Any]) -> str:
    """``acordao``: colunas de ``acordao`` (fonte, tribunal, orgao_julgador, classe_*, …)."""
    classe = acordao.get("classe_citacao") or acordao.get("classe_nome")
    numero = acordao.get("numero_processo_mascara")
    processo = " nº ".join(p for p in (classe, numero) if p)

    if acordao.get("fonte") == "tjdft" and acordao.get("relator_designado"):
        relator = f"Rel. p/ acórdão {acordao['relator_designado']}"
    elif acordao.get("relator"):
        relator = f"Rel. {acordao['relator']}"
    else:
        relator = None

    julgamento = _data(acordao.get("data_julgamento"))
    partes = [acordao.get("tribunal"), acordao.get("orgao_julgador"), processo, relator]
    partes.append(f"j. {julgamento}" if julgamento else None)
    if acordao.get("fonte") == "djen":
        disponibilizacao = _data(acordao.get("data_disponibilizacao"))
        partes.append(f"DJEN de {disponibilizacao}" if disponibilizacao else None)
    else:
        publicacao = _data(acordao.get("data_publicacao"))
        if publicacao:
            local = acordao.get("local_publicacao")
            partes.append(f"publ. {local} {publicacao}" if local else f"publ. {publicacao}")
    texto = ", ".join(str(p) for p in partes if p)
    return texto if texto.endswith(".") else texto + "."
