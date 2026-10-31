"""Linha de comando ``buscajus``.

Comandos:

- ``buscajus ingest djen --tribunal T --de AAAA-MM-DD --ate AAAA-MM-DD [--forcar]``
- ``buscajus ingest tjdft --de AAAA-MM-DD --ate AAAA-MM-DD [--forcar]``
- ``buscajus ingest conferir-tjdft [--de-dias 31] [--ate-dias 90]``
- ``buscajus ingest reprocessar --fonte djen [--tribunal T] --de AAAA-MM-DD --ate AAAA-MM-DD``
- ``buscajus ingest verificar-versoes --tribunal T [--dias 30]``
- ``buscajus ingest status [--fonte F] [--tribunal T] [--de AAAA-MM-DD] [--ate AAAA-MM-DD]``
- ``buscajus remocao listar | aceitar ID --decisao TEXTO | rejeitar ID --decisao TEXTO``
- ``buscajus remocao limpar-contatos [--dias N]``
- ``buscajus api openapi`` (imprime o contrato; versionado em ``frontend/openapi.json``)
- ``buscajus eval pool --consultas ARQ --saida ARQ.csv [--modelo NOME[@REVISAO]]... [--k 20]``
- ``buscajus eval metricas --consultas ARQ --julgamentos ARQ.csv [--modelo NOME[@REVISAO]]...``
- ``buscajus modelos baixar-ner`` (pesos do NER para o volume de modelos; passo explícito)
- ``buscajus revisao amostrar --n 100 | revisar | resultado | verificar`` (revisão por amostra)
- ``buscajus piloto carregar | limpar`` (piloto local, pelo worker do compose)

As coletas do DJEN e do TJDFT exigem o modelo de NER configurado (camada 2 da anonimização);
sem ele, o comando falha antes de qualquer acesso à fonte.
"""

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path

from buscajus import piloto, revisao
from buscajus.busca import pedidos
from buscajus.core.config import obter_config
from buscajus.core.logging import configurar_logging
from buscajus.db.engine import obter_engine
from buscajus.embed.avaliacao import (
    avaliar,
    carregar_consultas,
    exportar_pool,
    gerar_pool,
    importar_julgamentos,
)
from buscajus.embed.embedder import EmbedderSentenceTransformers
from buscajus.embed.indice import (
    BuscaTextoPostgres,
    IndiceVetorialMemoria,
    Sistema,
    documentos_ativos,
)
from buscajus.ingest import status
from buscajus.ingest.anonimizacao.modelo_ner import baixar_modelo, carregar_detector
from buscajus.ingest.anonimizacao.pipeline import ErroAnonimizacao
from buscajus.ingest.bruto import ArmazenamentoBruto
from buscajus.ingest.djen import fabrica
from buscajus.ingest.djen.conector import hoje_sao_paulo
from buscajus.ingest.djen.parser import VERSAO_PARSER
from buscajus.ingest.djen.versoes import verificar_versoes
from buscajus.ingest.reprocessamento import reprocessar_cadernos
from buscajus.ingest.runner import ResumoUnidade
from buscajus.ingest.tjdft import fabrica as fabrica_tjdft
from buscajus.ingest.tjdft.conferencia import conferir_dias_antigos
from buscajus.ingest.tjdft.fabrica import ConectorDesativado


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

    tjdft = subcomandos.add_parser("tjdft", help="coleta acórdãos do TJDFT por dia de publicação")
    tjdft.add_argument("--de", type=_data, required=True)
    tjdft.add_argument("--ate", type=_data, required=True)
    tjdft.add_argument("--forcar", action="store_true", help="recoleta dias já concluídos")
    tjdft.set_defaults(executar=_tjdft)

    conf = subcomandos.add_parser(
        "conferir-tjdft", help="confere os dias antigos do TJDFT e recoleta os que mudaram"
    )
    conf.add_argument("--de-dias", type=int, default=31)
    conf.add_argument("--ate-dias", type=int, default=90)
    conf.set_defaults(executar=_conferir_tjdft)

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

    remocao = comandos.add_parser("remocao", help="decisão dos pedidos de remoção (F4-12)")
    sub_remocao = remocao.add_subparsers(dest="subcomando", required=True)
    listar = sub_remocao.add_parser("listar", help="pedidos pendentes")
    listar.set_defaults(executar=_remocao_listar)
    for nome, ajuda, funcao in (
        ("aceitar", "remove o acórdão (ou os do processo) e apaga o conteúdo", _remocao_aceitar),
        ("rejeitar", "registra a recusa", _remocao_rejeitar),
    ):
        decidir = sub_remocao.add_parser(nome, help=ajuda)
        decidir.add_argument("pedido", type=int)
        decidir.add_argument("--decisao", required=True, help="justificativa registrada")
        decidir.set_defaults(executar=funcao)
    limpar = sub_remocao.add_parser(
        "limpar-contatos", help="apaga o e-mail dos pedidos resolvidos há mais de N dias"
    )
    limpar.add_argument("--dias", type=int, help="padrão: api.retencao_contato_dias")
    limpar.set_defaults(executar=_remocao_limpar)

    api = comandos.add_parser("api", help="contrato da API")
    sub_api = api.add_subparsers(dest="subcomando", required=True)
    openapi = sub_api.add_parser("openapi", help="imprime o OpenAPI em JSON")
    openapi.set_defaults(executar=_openapi)

    avaliacao = comandos.add_parser("eval", help="avaliação da busca (F3-04)")
    sub_eval = avaliacao.add_subparsers(dest="subcomando", required=True)
    pool = sub_eval.add_parser("pool", help="exporta o pool top-k de cada sistema para julgamento")
    pool.add_argument("--saida", type=Path, required=True)
    pool.add_argument("--k", type=int, default=20)
    pool.set_defaults(executar=_eval_pool)
    metricas = sub_eval.add_parser("metricas", help="nDCG@10, Recall@50, MRR e latência")
    metricas.add_argument("--julgamentos", type=Path, required=True)
    metricas.set_defaults(executar=_eval_metricas)
    for sub in (pool, metricas):
        sub.add_argument("--consultas", type=Path, required=True)
        sub.add_argument(
            "--modelo",
            action="append",
            default=[],
            help="NOME[@REVISAO]; repetível (padrão: embeddings.modelo da configuração)",
        )
        sub.add_argument("--limite", type=int, help="máximo de acórdãos no índice temporário")

    modelos = comandos.add_parser("modelos", help="pesos dos modelos locais")
    sub_modelos = modelos.add_subparsers(dest="subcomando", required=True)
    baixar = sub_modelos.add_parser(
        "baixar-ner", help="baixa a revisão fixada do NER para o volume de modelos"
    )
    baixar.set_defaults(executar=_baixar_ner)

    rev = comandos.add_parser("revisao", help="revisão por amostra da anonimização (F1-42)")
    sub_rev = rev.add_subparsers(dest="subcomando", required=True)
    amostra = sub_rev.add_parser("amostrar", help="sorteia ementas anonimizadas do banco local")
    amostra.add_argument("--n", type=int, default=revisao.META_APROVACAO)
    amostra.add_argument("--fracao-tjdft", type=float, default=revisao.FRACAO_TJDFT)
    amostra.add_argument("--desde", type=_data, help="só acórdãos coletados a partir da data")
    amostra.add_argument(
        "--nova-rodada", action="store_true", help="arquiva a amostra atual e sorteia outra"
    )
    amostra.add_argument("--semente", type=int)
    amostra.set_defaults(executar=_revisao_amostrar)
    rv = sub_rev.add_parser("revisar", help="mostra uma ementa por vez: ok ou vazou")
    rv.set_defaults(executar=_revisao_revisar)
    res = sub_rev.add_parser("resultado", help="agregados da rodada e relatório em docs/")
    res.add_argument("--relatorio", type=Path, help="padrão: docs/revisao-anonimizacao.md")
    res.add_argument("--meta", type=int, default=revisao.META_APROVACAO)
    res.set_defaults(executar=_revisao_resultado)
    ver = sub_rev.add_parser(
        "verificar", help="confere se as regras atuais pegam os trechos marcados (contagens)"
    )
    ver.set_defaults(executar=_revisao_verificar)
    for sub in (amostra, rv, res, ver):
        sub.add_argument("--pasta", type=Path, help=f"padrão: {revisao.NOME_PASTA}/ na raiz")

    pil = comandos.add_parser("piloto", help="piloto local com dados reais (F1-43, F1-44)")
    sub_pil = pil.add_subparsers(dest="subcomando", required=True)
    carregar = sub_pil.add_parser(
        "carregar", help="carga piloto pelo worker do compose (ponto de parada F1-43)"
    )
    carregar.add_argument("--dias-uteis", type=int, default=piloto.DIAS_UTEIS)
    carregar.set_defaults(executar=_piloto_carregar)
    limpar_piloto = sub_pil.add_parser("limpar", help="apaga todos os dados reais do piloto")
    limpar_piloto.add_argument("--sim", action="store_true", help="não pede confirmação")
    limpar_piloto.set_defaults(executar=_piloto_limpar)
    for sub in (carregar, limpar_piloto):
        sub.add_argument("--pasta-revisao", type=Path, help=f"padrão: {revisao.NOME_PASTA}/")
    exec_carga = sub_pil.add_parser("executar-carga", help="(só no worker) carga piloto")
    exec_carga.add_argument("--dias-uteis", type=int, default=piloto.DIAS_UTEIS)
    exec_carga.set_defaults(executar=_piloto_executar_carga)
    exec_limpeza = sub_pil.add_parser("executar-limpeza", help="(só no worker) limpeza")
    exec_limpeza.set_defaults(executar=_piloto_executar_limpeza)
    return parser


def _imprimir(dados: object) -> None:
    sys.stdout.write(json.dumps(dados, ensure_ascii=False, indent=2, default=str) + "\n")


def _coleta(tribunal: str) -> fabrica.ColetaDjen:
    return fabrica.criar_coleta(obter_config(), obter_engine(), tribunal=tribunal)


def _djen(args: argparse.Namespace) -> int:
    coleta = _coleta(args.tribunal)
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


def _tjdft(args: argparse.Namespace) -> int:
    coleta = fabrica_tjdft.criar_coleta(obter_config(), obter_engine())
    try:
        unidades = coleta.conector.planejar("TJDFT", args.de, args.ate)
        resumos = coleta.orquestrador.executar(unidades, forcar=args.forcar)
    finally:
        coleta.fechar()
    _imprimir([_resumo_tjdft(r) for r in resumos])
    return 1 if any(r.erro for r in resumos) else 0


def _conferir_tjdft(args: argparse.Namespace) -> int:
    engine = obter_engine()
    coleta = fabrica_tjdft.criar_coleta(obter_config(), engine)
    try:
        dias = conferir_dias_antigos(
            engine,
            coleta.conector,
            coleta.orquestrador,
            hoje=hoje_sao_paulo(),
            de_dias=args.de_dias,
            ate_dias=args.ate_dias,
        )
    finally:
        coleta.fechar()
    _imprimir([vars(d) for d in dias])
    return 1 if any(d.erro for d in dias) else 0


def _resumo_tjdft(resumo: ResumoUnidade) -> dict[str, object]:
    c = resumo.contadores
    return {
        "unidade": resumo.unidade.descricao,
        "resultado": str(resumo.resultado),
        "recebidos": c.recebidos,
        "aceitos": c.aceitos,
        "descartados_segredo": c.segredo,
        "descartados_outros": c.descartados - c.segredo,
        "rejeitados_anonimizacao": len(c.rejeitados_anonimizacao),
        "falhas_parser": c.falhas_parser,
        "quarentena": c.quarentena,
        "erro": resumo.erro,
    }


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
    coleta = _coleta(args.tribunal)
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


def _remocao_listar(_args: argparse.Namespace) -> int:
    _imprimir([vars(p) for p in pedidos.listar(obter_engine())])
    return 0


def _remocao_aceitar(args: argparse.Namespace) -> int:
    config = obter_config()
    removidos = pedidos.aceitar(
        obter_engine(), ArmazenamentoBruto(config.diretorio_raw), args.pedido, args.decisao
    )
    _imprimir({"pedido": args.pedido, "status": "aceito", "acordaos_removidos": removidos})
    return 0


def _remocao_rejeitar(args: argparse.Namespace) -> int:
    pedidos.rejeitar(obter_engine(), args.pedido, args.decisao)
    _imprimir({"pedido": args.pedido, "status": "rejeitado"})
    return 0


def _remocao_limpar(args: argparse.Namespace) -> int:
    dias = args.dias if args.dias is not None else obter_config().api.retencao_contato_dias
    _imprimir({"contatos_apagados": pedidos.limpar_contatos(obter_engine(), dias)})
    return 0


def _openapi(_args: argparse.Namespace) -> int:
    from buscajus.api.app import criar_app, openapi_json

    sys.stdout.write(openapi_json(criar_app()))
    return 0


def _sistemas(args: argparse.Namespace) -> tuple[list[Sistema], dict[str, str]]:
    """Índice temporário: um sistema vetorial por modelo, mais o full-text do Postgres."""
    config = obter_config()
    engine = obter_engine()
    documentos = documentos_ativos(engine, args.limite)
    padrao = config.embeddings.modelo
    if padrao and config.embeddings.revisao:
        padrao += f"@{config.embeddings.revisao}"
    sistemas: list[Sistema] = []
    for modelo in args.modelo or ([padrao] if padrao else []):
        nome, _, revisao = modelo.partition("@")
        embedder = EmbedderSentenceTransformers(
            nome,
            revisao=revisao or None,
            dispositivo=config.embeddings.dispositivo,
            tamanho_lote=config.embeddings.tamanho_lote,
            diretorio_cache=str(config.diretorio_modelos),
        )
        sistemas.append(
            IndiceVetorialMemoria(
                embedder,
                documentos,
                tokens_por_trecho=config.embeddings.tokens_por_trecho,
                sobreposicao=config.embeddings.sobreposicao_tokens,
            )
        )
    sistemas.append(BuscaTextoPostgres(engine))
    return sistemas, {d.id: d.texto for d in documentos}


def _eval_pool(args: argparse.Namespace) -> int:
    consultas = carregar_consultas(args.consultas)
    sistemas, textos = _sistemas(args)
    itens = gerar_pool(consultas, sistemas, args.k)
    exportar_pool(itens, textos, args.saida)
    _imprimir({"consultas": len(consultas), "itens": len(itens), "saida": str(args.saida)})
    return 0


def _eval_metricas(args: argparse.Namespace) -> int:
    consultas = carregar_consultas(args.consultas)
    julgamentos = importar_julgamentos(args.julgamentos)
    sistemas, _ = _sistemas(args)
    _imprimir([r.resumo() for r in avaliar(consultas, sistemas, julgamentos)])
    return 0


def _baixar_ner(_args: argparse.Namespace) -> int:
    config = obter_config()
    caminho = baixar_modelo(config.anonimizacao, config.diretorio_modelos)
    carregar_detector(config.anonimizacao, config.diretorio_modelos)  # confere o carregamento
    _imprimir({"modelo": config.anonimizacao.modelo_ner, "caminho": str(caminho)})
    return 0


def _pasta_revisao(pasta: Path | None) -> Path:
    if pasta is not None:
        return pasta
    try:
        return piloto.raiz_repositorio() / revisao.NOME_PASTA
    except piloto.ErroPiloto:
        return Path(revisao.NOME_PASTA)


def _revisao_amostrar(args: argparse.Namespace) -> int:
    pasta = _pasta_revisao(args.pasta)
    piloto.conferir_pastas([pasta])
    _imprimir(
        revisao.amostrar(
            obter_engine(),
            pasta,
            n=args.n,
            fracao_tjdft=args.fracao_tjdft,
            desde=args.desde,
            nova_rodada=args.nova_rodada,
            semente=args.semente,
        )
    )
    return 0


def _revisao_revisar(args: argparse.Namespace) -> int:
    pasta = _pasta_revisao(args.pasta)
    piloto.conferir_pastas([pasta])
    _imprimir(revisao.revisar(obter_engine(), pasta))
    return 0


def _revisao_resultado(args: argparse.Namespace) -> int:
    relatorio = args.relatorio
    if relatorio is None:
        relatorio = piloto.raiz_repositorio() / "docs" / "revisao-anonimizacao.md"
    _imprimir(revisao.resultado(_pasta_revisao(args.pasta), relatorio, meta=args.meta))
    return 0


def _revisao_verificar(args: argparse.Namespace) -> int:
    config = obter_config()
    detector = carregar_detector(config.anonimizacao, config.diretorio_modelos)
    if detector is None:
        raise ErroAnonimizacao("nenhum modelo de NER configurado (camada 2)")
    _imprimir(revisao.verificar(_pasta_revisao(args.pasta), detector))
    return 0


def _piloto_conferir(args: argparse.Namespace) -> Path:
    raiz = piloto.raiz_repositorio()
    piloto.conferir_pastas([raiz, _pasta_revisao(args.pasta_revisao)])
    return raiz


def _piloto_carregar(args: argparse.Namespace) -> int:
    raiz = _piloto_conferir(args)
    codigo, saida = piloto.chamar_worker(
        raiz, ["executar-carga", "--dias-uteis", str(args.dias_uteis)]
    )
    sys.stdout.write(saida)
    return codigo


def _piloto_limpar(args: argparse.Namespace, ler: Callable[[str], str] = input) -> int:
    raiz = _piloto_conferir(args)
    pasta = _pasta_revisao(args.pasta_revisao)
    if not args.sim:
        sys.stderr.write(
            "Isto apaga TODOS os dados reais do piloto: acórdãos, histórico e coleta no banco "
            f"local, os arquivos do volume raw e a pasta {pasta}.\n"
        )
        if ler("Digite APAGAR para confirmar: ").strip() != "APAGAR":
            sys.stderr.write("buscajus: limpeza cancelada\n")
            return 1
    codigo, saida = piloto.chamar_worker(raiz, ["executar-limpeza"])
    if codigo != 0:
        sys.stdout.write(saida)
        return codigo
    resultado = json.loads(saida) if saida.strip() else {}
    resultado["arquivos_pasta_revisao"] = piloto.limpar_diretorio(pasta)
    if pasta.exists():
        pasta.rmdir()
    _imprimir(resultado)
    return 0


def _piloto_executar_carga(args: argparse.Namespace) -> int:
    volumes = piloto.executar_carga(
        obter_config(), obter_engine(), hoje=hoje_sao_paulo(), dias_uteis=args.dias_uteis
    )
    _imprimir(piloto.volumes_dict(volumes))
    return 1 if any(volumes.erros.values()) else 0


def _piloto_executar_limpeza(_args: argparse.Namespace) -> int:
    _imprimir(piloto.executar_limpeza(obter_config(), obter_engine()))
    return 0


def _saidas_em_utf8() -> None:
    """No Windows a saída padrão é cp1252 com CRLF; o resultado sai sempre em UTF-8 com LF."""
    for fluxo in (sys.stdout, sys.stderr):
        reconfigurar = getattr(fluxo, "reconfigure", None)
        if reconfigurar is not None:
            reconfigurar(encoding="utf-8", newline="\n")


def main(argv: Sequence[str] | None = None) -> int:
    _saidas_em_utf8()
    configurar_logging(obter_config().nivel_log)
    args = _parser().parse_args(argv)
    try:
        codigo: int = args.executar(args)
    except (
        ErroAnonimizacao,
        ConectorDesativado,
        pedidos.PedidoInvalido,
        revisao.ErroRevisao,
        piloto.ErroPiloto,
    ) as exc:
        sys.stderr.write(f"buscajus: {exc}\n")
        return 2
    except ModuleNotFoundError as exc:
        if exc.name not in ("sentence_transformers", "torch"):
            raise
        sys.stderr.write(
            "buscajus: os modelos de embedding exigem o grupo opcional "
            "(uv sync --group embeddings)\n"
        )
        return 2
    return codigo


if __name__ == "__main__":
    sys.exit(main())
