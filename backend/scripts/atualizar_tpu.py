"""Atualiza a tabela de classes da TPU do CNJ versionada no repositório (F2-03).

Baixa as classes das Tabelas Processuais Unificadas pela API pública do CNJ e grava em
``src/buscajus/db/dados/tpu_classes.json`` só o necessário: código, nome, código do pai,
sigla e situação (ativa ou inativa). Ficam de fora o glossário e os campos de auditoria
(``usuario_inclusao``, ``usuario_alteracao``), que identificam servidores do CNJ.

A data de referência é a maior ``data_versao`` das classes. Depois de atualizar o arquivo,
crie uma migração que chame ``buscajus.db.classes_cnj.carregar_tpu`` para recarregar a tabela.

Uso (de ``backend/``)::

    uv run python scripts/atualizar_tpu.py
"""

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import httpx

URL = "https://gateway.cloud.pje.jus.br/tpu/api/v1/publico/download/classes"
USER_AGENT = "BuscaJus/tpu (+https://github.com/danielcperalba/buscajus)"
DESTINO = Path(__file__).parent.parent / "src/buscajus/db/dados/tpu_classes.json"


def _classe(bruta: dict[str, Any]) -> dict[str, Any]:
    return {
        "codigo": int(bruta["cod_item"]),
        "nome": " ".join(str(bruta["nome"]).split()),
        "codigo_pai": int(bruta["cod_item_pai"]) if bruta.get("cod_item_pai") else None,
        "sigla": (bruta.get("sigla") or "").strip() or None,
        "ativa": bruta.get("situacao") == "A",
    }


def main() -> int:
    resposta = httpx.get(URL, headers={"User-Agent": USER_AGENT}, timeout=120)
    resposta.raise_for_status()
    brutas = resposta.json()
    classes = sorted((_classe(b) for b in brutas), key=lambda c: c["codigo"])
    referencia = max(str(b.get("data_versao") or "")[:10] for b in brutas)
    conteudo = {
        "fonte": URL,
        "data_referencia": referencia,
        "baixado_em": date.today().isoformat(),  # noqa: DTZ011 (data local da atualização)
        "total": len(classes),
        "classes": classes,
    }
    # Uma classe por linha: diffs legíveis quando a TPU mudar.
    linhas = [json.dumps(c, ensure_ascii=False) for c in classes]
    cabecalho = {k: v for k, v in conteudo.items() if k != "classes"}
    texto = json.dumps(cabecalho, ensure_ascii=False, indent=2)[:-2]
    texto += ',\n  "classes": [\n    ' + ",\n    ".join(linhas) + "\n  ]\n}\n"
    if json.loads(texto) != conteudo:
        raise RuntimeError("serialização da TPU não confere com o conteúdo")
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(texto, encoding="utf-8")
    print(f"{len(classes)} classes, referência {referencia} -> {DESTINO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
