"""Linha de comando ``buscajus``.

Comandos:

- ``buscajus ingest status [--fonte F] [--tribunal T] [--de AAAA-MM-DD] [--ate AAAA-MM-DD]``
"""

import argparse
import sys
from collections.abc import Sequence
from datetime import date

from buscajus.core.config import obter_config
from buscajus.core.logging import configurar_logging
from buscajus.db.engine import obter_engine
from buscajus.ingest import status


def _data(valor: str) -> date:
    try:
        return date.fromisoformat(valor)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"data inválida (use AAAA-MM-DD): {valor}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="buscajus")
    comandos = parser.add_subparsers(dest="comando", required=True)

    ingest = comandos.add_parser("ingest", help="coleta de fontes")
    subcomandos = ingest.add_subparsers(dest="subcomando", required=True)

    st = subcomandos.add_parser("status", help="relatório de coleta por unidade")
    st.add_argument("--fonte", choices=["djen", "tjdft"])
    st.add_argument("--tribunal")
    st.add_argument("--de", type=_data)
    st.add_argument("--ate", type=_data)
    st.set_defaults(executar=_status)
    return parser


def _status(args: argparse.Namespace) -> int:
    with obter_engine().connect() as conexao:
        saidas = []
        if args.fonte in (None, "djen"):
            cadernos = status.listar_cadernos(
                conexao, tribunal=args.tribunal, de=args.de, ate=args.ate
            )
            saidas.append(
                status.formatar_tabela(cadernos, status.COLUNAS_CADERNOS, "Cadernos do DJEN")
            )
        janelas = status.listar_janelas(
            conexao, fonte=args.fonte, tribunal=args.tribunal, de=args.de, ate=args.ate
        )
        if args.fonte is not None or janelas:
            saidas.append(
                status.formatar_tabela(janelas, status.COLUNAS_JANELAS, "Janelas paginadas")
            )
    sys.stdout.write("\n".join(saidas))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    configurar_logging(obter_config().nivel_log)
    args = _parser().parse_args(argv)
    codigo: int = args.executar(args)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
