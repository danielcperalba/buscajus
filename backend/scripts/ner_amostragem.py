"""F1-36: amostra estratificada para avaliar o NER de pessoas. Roda NA MÁQUINA DO ANOTADOR.

Condições (ARCHITECTURE.md, seção 6.3): ambiente local restrito aos anotadores, disco
criptografado, fora do repositório e do CI; nada enviado a serviços de terceiros.

O script baixa os cadernos do DJEN das datas pedidas (exige acesso do Brasil), aplica a
camada 1 (destinatários → iniciais) e o mascaramento de CPF com o pipeline real, sorteia
~300 ementas estratificadas pelo nome do órgão (50% criminal, 25% família, 25% cível) e
grava **apenas** o texto da ementa e o estrato. Não grava número do processo, link,
destinatários nem o id da comunicação. Cada ZIP é apagado ao fim do dia processado.

A saída no terminal tem só contagens. Uso (de ``backend/``)::

    uv run python scripts/ner_amostragem.py --saida /caminho/criptografado/ner-avaliacao-privado \\
        2026-10-13 2026-10-14 2026-10-15

Ementas recusadas pela invariante da camada 1 não entram na amostra.
"""

import argparse
import json
import os
import random
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from buscajus.core.config import Config
from buscajus.ingest.anonimizacao.camada2 import Entidade
from buscajus.ingest.anonimizacao.pipeline import AnonimizadorDjen
from buscajus.ingest.conector import Checkpoint, UnidadeColeta, UnidadeNaoPronta, UnidadeSemDados
from buscajus.ingest.djen.conector import ConectorDjen
from buscajus.ingest.djen.parser import FalhaParser, analisar
from buscajus.ingest.http import ClienteHttp
from buscajus.ingest.texto import chave

PROPORCAO = {"criminal": 0.50, "familia": 0.25, "civel": 0.25}
# No TJPR, família e sucessões ficam na 11ª e na 12ª Câmara Cível.
ORGAOS_FAMILIA_PADRAO = ("11ª Câmara Cível", "12ª Câmara Cível")
NOME_PASTA = "ner-avaliacao-privado"


class SemNer:
    """Só a camada 1: a avaliação mede justamente o que a camada 2 precisa pegar."""

    versao = "nenhum"

    def detectar(self, texto: str) -> Sequence[Entidade]:
        return []


def estrato(orgao: str, familia: set[str]) -> str:
    nome = chave(orgao)
    if "criminal" in nome:
        return "criminal"
    if nome in familia:
        return "familia"
    return "civel"


def _verificar_ambiente(saida: Path) -> None:
    if os.environ.get("CI"):
        sys.exit("recusado: este script não roda em CI")
    raiz = subprocess.run(  # noqa: S603
        ["git", "-C", str(Path(__file__).parent), "rev-parse", "--show-toplevel"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if raiz:
        repo = Path(raiz).resolve()
        destino = saida.resolve()
        dentro = destino == repo or repo in destino.parents
        if dentro and destino != repo / NOME_PASTA:
            sys.exit(
                f"recusado: a saída fica dentro do repositório (use fora dele ou {NOME_PASTA}/)"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("datas", nargs="+", type=date.fromisoformat)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--tribunal", default="TJPR")
    parser.add_argument("--total", type=int, default=300)
    parser.add_argument("--orgaos-familia", default=",".join(ORGAOS_FAMILIA_PADRAO))
    parser.add_argument("--semente", type=int, default=None)
    args = parser.parse_args()
    _verificar_ambiente(args.saida)

    familia = {chave(o) for o in args.orgaos_familia.split(",") if o.strip()}
    config = Config()
    contagens: Counter[str] = Counter()
    por_estrato: dict[str, list[str]] = {e: [] for e in PROPORCAO}
    with (
        ClienteHttp(config.http, config.djen.requisicoes_por_segundo) as cliente,
        tempfile.TemporaryDirectory(prefix="ner-cadernos-") as tmp,
    ):
        conector = ConectorDjen(
            config.djen.model_copy(update={"tribunais": [args.tribunal.upper()]}),
            cliente,
            AnonimizadorDjen(SemNer()),
            Path(tmp),
        )
        for dia in args.datas:
            unidade = UnidadeColeta("djen", args.tribunal.upper(), dia, dia, paginada=False)
            try:
                for lote in conector.coletar(unidade, Checkpoint()):
                    contagens["rejeitadas_camada_1"] += len(lote.contadores.rejeitados_anonimizacao)
                    for item in lote.itens:
                        try:
                            texto = analisar(str(item["texto"])).ementa
                        except FalhaParser:
                            contagens["falhas_parser"] += 1
                            continue
                        por_estrato[estrato(str(item.get("nomeOrgao") or ""), familia)].append(
                            texto
                        )
                        contagens["ementas"] += 1
            except (UnidadeSemDados, UnidadeNaoPronta):
                contagens["dias_sem_caderno"] += 1
            except Exception as exc:
                # Só o tipo: a mensagem de exceções genéricas pode trazer conteúdo.
                print(f"erro em {dia}: {type(exc).__name__}")
                contagens["dias_com_erro"] += 1

    sorteio = random.Random(args.semente)  # noqa: S311 (amostragem, não criptografia)
    amostra: list[dict[str, str]] = []
    for nome, proporcao in PROPORCAO.items():
        quantidade = min(round(args.total * proporcao), len(por_estrato[nome]))
        amostra += [
            {"estrato": nome, "texto": t} for t in sorteio.sample(por_estrato[nome], quantidade)
        ]
    sorteio.shuffle(amostra)

    args.saida.mkdir(parents=True, exist_ok=True, mode=0o700)
    destino = args.saida / "amostra.jsonl"
    with destino.open("w", encoding="utf-8") as arquivo:
        for i, registro in enumerate(amostra, start=1):
            linha = {"id_amostra": f"a{i:03d}", **registro, "texto_anotado": None}
            arquivo.write(json.dumps(linha, ensure_ascii=False) + "\n")
    destino.chmod(0o600)

    print(
        json.dumps(
            {
                "contagens": dict(contagens),
                "disponiveis_por_estrato": {k: len(v) for k, v in por_estrato.items()},
                "amostra_por_estrato": dict(Counter(r["estrato"] for r in amostra)),
                "arquivo": str(destino),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
