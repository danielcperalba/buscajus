"""Linha de comando ``buscajus``.

Comandos:

- ``buscajus ingest djen --tribunal T --de AAAA-MM-DD --ate AAAA-MM-DD [--forcar]``
- ``buscajus ingest reprocessar --fonte djen [--tribunal T] --de AAAA-MM-DD --ate AAAA-MM-DD``
- ``buscajus ingest verificar-versoes --tribunal T [--dias 30]``
- ``buscajus ingest status [--fonte F] [--tribunal T] [--de AAAA-MM-DD] [--ate AAAA-MM-DD]``

A coleta do DJEN exige o modelo de NER configurado (camada 2 da anonimização); sem ele, o
comando falha antes de qualquer acesso à fonte.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date

from buscajus.core.config import obter_config
from buscajus.core.logging import configurar_logging
from buscajus.db.engine import obter_engine
from buscajus.ingest import status
from buscajus.ingest.anonimizacao.pipeline import ErroAnonimizacao
from buscajus.ingest.bruto import ArmazenamentoBruto
from buscajus.ingest.djen import fabrica
from buscajus.ingest.djen.conector import hoje_sao_paulo
from buscajus.ingest.djen.parser import VERSAO_PARSER
from buscajus.ingest.djen.versoes import verificar_versoes
from buscajus.ingest.reprocessamento import reprocessar_cadernos


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

    djen = subcomandos.add_parser("djen", help="coleta cadernos do DJEN de um período")
    djen.add_argument("--tribunal", required=True)
    djen.add_argument("--de", type=_data, required=True)
    djen.add_argument("--ate", type=_data, required=True)
    djen.add_argument("--forcar", action="store_true", help="reprocessa cadernos já concluídos")
    djen.set_defaults(executar=_djen)

    rep = subcomandos.add_parser("reprocessar", help="refaz o parser a partir do bruto, sem rede")
    rep.add_argument("--fonte", choices=["djen"], required=True)
    rep.add_argument("--tribunal")
    rep.add_argument("--de", type=_data, required=True)
    rep.add_argument("--ate", type=_data, required=True)
    rep.set_defaults(executar=_reprocessar)

    ver = subcomandos.add_parser("verificar-versoes", help="confere a versão dos cadernos recentes")
    ver.add_argument("--tribunal", required=True)
    ver.add_argument("--dias", type=int, default=30)
    ver.set_defaults(executar=_verificar_versoes)

    st = subcomandos.add_parser("status", help="relatório de coleta por unidade")
    st.add_argument("--fonte", choices=["djen", "tjdft"])
    st.add_argument("--tribunal")
    st.add_argument("--de", type=_data)
    st.add_argument("--ate", type=_data)
    st.set_defaults(executar=_status)
    return parser


def _imprimir(dados: object) -> None:
    sys.stdout.write(json.dumps(dados, ensure_ascii=False, indent=2, default=str) + "\n")


def _coleta() -> fabrica.ColetaDjen:
    return fabrica.criar_coleta(obter_config(), obter_engine())


def _djen(args: argparse.Namespace) -> int:
    coleta = _coleta()
    try:
        unidades = coleta.conector.planejar(args.tribunal, args.de, args.ate)
        resumos = coleta.orquestrador.executar(unidades, forcar=args.forcar)
    finally:
        coleta.fechar()
    _imprimir(
        [
            {
                "unidade": r.unidade.descricao,
                "resultado": str(r.resultado),
                "comunicacoes": r.contadores.recebidos,
                "aceitos": r.contadores.aceitos,
                "rejeitados_anonimizacao": len(r.contadores.rejeitados_anonimizacao),
                "falhas_parser": r.contadores.falhas_parser,
                "quarentena": r.contadores.quarentena,
                "cancelados": r.contadores.cancelados,
                "anomalias": r.contadores.anomalias,
                "erro": r.erro,
            }
            for r in resumos
        ]
    )
    return 1 if any(r.erro for r in resumos) else 0


def _reprocessar(args: argparse.Namespace) -> int:
    config = obter_config()
    resultados = reprocessar_cadernos(
        obter_engine(),
        ArmazenamentoBruto(config.diretorio_raw),
        fabrica.processador(config),
        de=args.de,
        ate=args.ate,
        tribunal=args.tribunal,
        versao_parser=VERSAO_PARSER,
    )
    _imprimir(
        [
            {
                "tribunal": r.tribunal,
                "data": r.data,
                "itens": r.itens,
                "falhas_parser": r.contadores.falhas_parser,
                "quarentena": r.contadores.quarentena,
                "cancelados": r.contadores.cancelados,
                "bloqueados": r.contadores.bloqueados,
                "anomalias": r.contadores.anomalias,
            }
            for r in resultados
        ]
    )
    return 0


def _verificar_versoes(args: argparse.Namespace) -> int:
    config = obter_config()
    coleta = _coleta()
    try:
        resultados = verificar_versoes(
            obter_engine(),
            coleta.orquestrador,
            coleta.cliente,
            coleta.bruto,
            url_api=config.djen.url_api,
            regra=fabrica.regra_estado(config),
            tribunal=args.tribunal.upper(),
            hoje=hoje_sao_paulo(),
            dias=args.dias,
        )
    finally:
        coleta.fechar()
    _imprimir([vars(r) for r in resultados])
    return 1 if any(r.erro for r in resultados) else 0


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
    try:
        codigo: int = args.executar(args)
    except ErroAnonimizacao as exc:
        sys.stderr.write(f"buscajus: {exc}\n")
        return 2
    return codigo


if __name__ == "__main__":
    sys.exit(main())
