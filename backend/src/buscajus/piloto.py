"""Piloto local com dados reais (F1-43, F1-44; ARCHITECTURE.md, seção 6.7).

Banco local só para teste e revisão: nada vai para a internet nem para backup. A sequência é
carga → revisão → resultado → limpeza (README, "Piloto local").

Os comandos têm duas metades:

- **no terminal do dono** (Windows ou outro): ``buscajus piloto carregar`` e
  ``buscajus piloto limpar`` conferem que o repositório e a pasta da revisão não estão numa
  pasta sincronizada com nuvem e chamam o ``worker`` do compose;
- **dentro do worker** (contêiner Linux, tmpfs para os cadernos): ``executar-carga`` e
  ``executar-limpeza``, que se recusam a rodar fora dele.

A carga (F1-43) é **ponto de parada**: só roda com a aprovação do dono do projeto.
"""

import os
import shutil
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url

from buscajus.core.config import Config
from buscajus.core.erros import ErroSeguro
from buscajus.ingest.anonimizacao.modelo_ner import carregar_detector
from buscajus.ingest.anonimizacao.pipeline import CAMADAS, criar_anonimizador
from buscajus.ingest.conector import UnidadeColeta
from buscajus.ingest.runner import Resultado, ResumoUnidade
from buscajus.ingest.tjdft.anonimizacao import criar_anonimizador as criar_anonimizador_tjdft

DIAS_UTEIS = 5
# Quantos dias para trás, no máximo, para achar os dias úteis com dados (feriados).
JANELA_MAXIMA = 20
HOSTS_LOCAIS = frozenset({"db", "127.0.0.1", "localhost", "::1"})
# Variável que o compose define só no worker (compose.yaml).
VARIAVEL_CONTEINER = "BUSCAJUS_EM_CONTEINER"
# Acórdãos sintéticos de desenvolvimento: processos do ano 2099 (fixtures e dados de teste).
ANO_SINTETICO = "2099"

# Nomes de pastas de clientes de sincronização com nuvem.
_PASTAS_NUVEM = (
    "onedrive",
    "dropbox",
    "google drive",
    "googledrive",
    "meu drive",
    "my drive",
    "icloud drive",
    "iclouddrive",
    "icloud~",
    "mobile documents",
    "box sync",
    "box",
    "mega",
    "megasync",
    "pcloud",
    "sync.com",
    "nextcloud",
    "owncloud",
    "yandex.disk",
)
_VARIAVEIS_NUVEM = ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")


class ErroPiloto(ErroSeguro):
    pass


# --- Pastas sincronizadas com nuvem ----------------------------------------------------------


def raizes_nuvem(ambiente: Mapping[str, str] | None = None) -> list[Path]:
    """Pastas raiz de sincronização conhecidas pelas variáveis de ambiente (OneDrive)."""
    env = os.environ if ambiente is None else ambiente
    return [Path(env[v]).resolve() for v in _VARIAVEIS_NUVEM if env.get(v)]


def em_pasta_nuvem(caminho: Path, ambiente: Mapping[str, str] | None = None) -> str | None:
    """Motivo, se o caminho estiver dentro de uma pasta sincronizada com nuvem."""
    resolvido = caminho.resolve()
    for raiz in raizes_nuvem(ambiente):
        if resolvido == raiz or raiz in resolvido.parents:
            return f"dentro da pasta do OneDrive ({raiz})"
    for parte in (resolvido, *resolvido.parents):
        nome = parte.name.lower()
        if any(nome == p or nome.startswith((f"{p} -", f"{p}-")) for p in _PASTAS_NUVEM):
            return f"dentro de uma pasta sincronizada com nuvem ({parte})"
    return None


def raiz_repositorio(inicio: Path | None = None) -> Path:
    atual = (inicio or Path.cwd()).resolve()
    for pasta in (atual, *atual.parents):
        if (pasta / "compose.yaml").exists() and (pasta / "backend").is_dir():
            return pasta
    raise ErroPiloto("rode o comando de dentro do repositório (não achei o compose.yaml)")


def conferir_pastas(caminhos: Iterable[Path], ambiente: Mapping[str, str] | None = None) -> None:
    for caminho in caminhos:
        motivo = em_pasta_nuvem(caminho, ambiente)
        if motivo:
            raise ErroPiloto(
                f"recusado: {caminho} está {motivo}. Mova o repositório e a pasta da revisão "
                "para fora de pastas sincronizadas (OneDrive, Dropbox, Google Drive, iCloud…)."
            )


# --- Dentro do worker -----------------------------------------------------------------------


def conferir_conteiner(config: Config, ambiente: Mapping[str, str] | None = None) -> None:
    """Recusa rodar fora do worker do compose de desenvolvimento, ou com banco remoto."""
    env = os.environ if ambiente is None else ambiente
    if sys.platform != "linux" or env.get(VARIAVEL_CONTEINER) != "1":
        raise ErroPiloto(
            "recusado: o piloto com dados reais roda só no worker do compose "
            "(use `buscajus piloto carregar|limpar` no seu terminal)"
        )
    if config.ambiente == "producao":
        raise ErroPiloto("recusado: o piloto não roda no ambiente de produção")
    host = make_url(config.database_url).host
    if host not in HOSTS_LOCAIS:
        raise ErroPiloto("recusado: o piloto usa só o banco local do compose")


def dias_uteis_anteriores(hoje: date, janela: int = JANELA_MAXIMA) -> list[date]:
    """Dias de semana antes de hoje, do mais recente ao mais antigo."""
    dias = [hoje - timedelta(days=i) for i in range(1, janela + 1)]
    return [d for d in dias if d.weekday() < 5]


@dataclass
class Volumes:
    """Só agregados: o que o dono do projeto recebe depois da carga."""

    dias: dict[str, list[str]] = field(default_factory=dict)
    comunicacoes: int = 0
    ementas_aceitas: dict[str, int] = field(default_factory=dict)
    substituicoes: dict[str, dict[str, int]] = field(default_factory=dict)
    quarentena: dict[str, int] = field(default_factory=dict)
    rejeitados_anonimizacao: dict[str, int] = field(default_factory=dict)
    falhas_parser: dict[str, int] = field(default_factory=dict)
    descartados_segredo: int = 0
    erros: dict[str, int] = field(default_factory=dict)

    def somar(self, fonte: str, resumo: ResumoUnidade) -> None:
        c = resumo.contadores
        if fonte == "djen":
            self.comunicacoes += c.recebidos
        else:
            self.descartados_segredo += c.segredo
        for campo, valor in (
            ("ementas_aceitas", c.aceitos),
            ("quarentena", c.quarentena),
            ("rejeitados_anonimizacao", len(c.rejeitados_anonimizacao)),
            ("falhas_parser", c.falhas_parser),
            ("erros", 1 if resumo.erro else 0),
        ):
            destino: dict[str, int] = getattr(self, campo)
            destino[fonte] = destino.get(fonte, 0) + valor


Executar = Callable[[UnidadeColeta], ResumoUnidade]


def carregar_dias(
    planejar: Callable[[date], UnidadeColeta],
    executar: Executar,
    candidatos: Sequence[date],
    dias_uteis: int,
    tem_dados: Callable[[ResumoUnidade], bool],
) -> tuple[list[str], list[ResumoUnidade]]:
    """Processa os dias candidatos até achar ``dias_uteis`` com dados."""
    com_dados: list[str] = []
    resumos: list[ResumoUnidade] = []
    for dia in candidatos:
        if len(com_dados) >= dias_uteis:
            break
        resumo = executar(planejar(dia))
        resumos.append(resumo)
        if tem_dados(resumo):
            com_dados.append(dia.isoformat())
    return com_dados, resumos


def executar_carga(
    config: Config, engine: Engine, *, hoje: date, dias_uteis: int = DIAS_UTEIS
) -> Volumes:
    """Carga piloto: ``dias_uteis`` cadernos do TJPR (DJEN) e dias do TJDFT, no banco local."""
    from buscajus.ingest.djen import fabrica as fabrica_djen
    from buscajus.ingest.tjdft import fabrica as fabrica_tjdft

    conferir_conteiner(config)
    detector = carregar_detector(config.anonimizacao, config.diretorio_modelos)
    volumes = Volumes()
    candidatos = dias_uteis_anteriores(hoje)

    anon_djen = criar_anonimizador(detector)
    coleta = fabrica_djen.criar_coleta(config, engine, anonimizador=anon_djen, tribunal="TJPR")
    try:
        dias, resumos = carregar_dias(
            lambda d: coleta.conector.planejar("TJPR", d, d)[0],
            lambda u: coleta.orquestrador.executar([u], forcar=True)[0],
            candidatos,
            dias_uteis,
            lambda r: r.resultado == Resultado.CONCLUIDA,
        )
    finally:
        coleta.fechar()
    volumes.dias["djen"] = dias
    for resumo in resumos:
        volumes.somar("djen", resumo)
    volumes.substituicoes["djen"] = dict(anon_djen.substituicoes)

    anon_tjdft = criar_anonimizador_tjdft(detector)
    coleta_tjdft = fabrica_tjdft.criar_coleta(config, engine, anonimizador=anon_tjdft)
    try:
        dias, resumos = carregar_dias(
            lambda d: coleta_tjdft.conector.planejar("TJDFT", d, d)[0],
            lambda u: coleta_tjdft.orquestrador.executar([u], forcar=True)[0],
            candidatos,
            dias_uteis,
            lambda r: r.resultado == Resultado.CONCLUIDA and r.contadores.recebidos > 0,
        )
    finally:
        coleta_tjdft.fechar()
    volumes.dias["tjdft"] = dias
    for resumo in resumos:
        volumes.somar("tjdft", resumo)
    volumes.substituicoes["tjdft"] = {
        c: v for c, v in anon_tjdft.substituicoes.items() if c != "camada1"
    }
    return volumes


# Tabelas de coleta: apagadas por inteiro (só o piloto as usa no banco local).
TABELAS_COLETA = ("coleta_bruta", "caderno_djen", "coleta_janela", "tarefa")


def executar_limpeza(config: Config, engine: Engine) -> dict[str, int]:
    """Apaga os dados reais do piloto do banco e do volume raw. Devolve só contagens.

    Ficam o esquema, a tabela ``classe_cnj`` (TPU) e os acórdãos sintéticos de
    desenvolvimento (processos do ano 2099).
    """
    conferir_conteiner(config)
    contagens = limpar_banco(engine)
    contagens["arquivos_raw"] = limpar_diretorio(config.diretorio_raw)
    contagens["arquivos_tmp_cadernos"] = limpar_diretorio(config.diretorio_tmp_cadernos)
    return contagens


_REAIS = f"substring(numero_processo from 10 for 4) <> '{ANO_SINTETICO}'"


def limpar_banco(engine: Engine) -> dict[str, int]:
    contagens: Counter[str] = Counter()
    with engine.begin() as conexao:
        reais = f"SELECT id FROM acordao WHERE {_REAIS}"  # noqa: S608 (constantes)
        contagens["acordao_historico"] = conexao.execute(
            text(f"DELETE FROM acordao_historico WHERE acordao_id IN ({reais})")  # noqa: S608
        ).rowcount
        conexao.execute(
            text(f"UPDATE acordao SET duplicata_de = NULL WHERE duplicata_de IN ({reais})")  # noqa: S608
        )
        conexao.execute(text("UPDATE acordao SET coleta_bruta_id = NULL"))
        pedidos = f"""
            SELECT id FROM pedido_remocao
            WHERE acordao_id IN ({reais})
               OR (acordao_id IS NULL
                   AND substring(numero_processo from 10 for 4) <> '{ANO_SINTETICO}')
        """  # noqa: S608 (constantes)
        contagens["bloqueio"] = conexao.execute(
            text(f"""
                DELETE FROM bloqueio b
                WHERE b.pedido_remocao_id IN ({pedidos})
                   OR (b.numero_processo IS NOT NULL
                       AND substring(b.numero_processo from 10 for 4) <> '{ANO_SINTETICO}')
                   OR (b.id_fonte IS NOT NULL AND NOT EXISTS (
                        SELECT 1 FROM acordao a
                        WHERE a.fonte = b.fonte AND a.id_fonte = b.id_fonte
                          AND substring(a.numero_processo from 10 for 4) = '{ANO_SINTETICO}'))
            """)  # noqa: S608
        ).rowcount
        contagens["pedido_remocao"] = conexao.execute(
            text(f"DELETE FROM pedido_remocao WHERE id IN ({pedidos})")  # noqa: S608
        ).rowcount
        contagens["acordao"] = conexao.execute(
            text(f"DELETE FROM acordao WHERE {_REAIS}")  # noqa: S608
        ).rowcount
        for tabela in TABELAS_COLETA:
            contagens[tabela] = conexao.execute(text(f"DELETE FROM {tabela}")).rowcount  # noqa: S608
    # Linhas apagadas continuam nas páginas do disco até o VACUUM: reescreve as tabelas.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conexao:
        tabelas = ("acordao", "acordao_historico", "pedido_remocao", "bloqueio", *TABELAS_COLETA)
        conexao.execute(text(f"VACUUM (FULL) {', '.join(tabelas)}"))
    return dict(contagens)


def limpar_diretorio(diretorio: Path) -> int:
    """Apaga tudo dentro do diretório (que continua existindo). Devolve quantos arquivos."""
    if not diretorio.exists():
        return 0
    arquivos = sum(1 for p in diretorio.rglob("*") if p.is_file() or p.is_symlink())
    for item in diretorio.iterdir():
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink()
    return arquivos


# --- No terminal do dono ---------------------------------------------------------------------


def comando_worker(*argumentos: str) -> list[str]:
    return ["docker", "compose", "run", "--rm", "-T", "worker", "buscajus", "piloto", *argumentos]


def chamar_worker(raiz: Path, argumentos: Sequence[str]) -> tuple[int, str]:
    """Roda o subcomando no worker; os logs (stderr) passam direto, o stdout é devolvido."""
    processo = subprocess.run(  # noqa: S603
        comando_worker(*argumentos),
        cwd=raiz,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return processo.returncode, processo.stdout


def volumes_dict(volumes: Volumes) -> dict[str, Any]:
    return {
        "dias": volumes.dias,
        "comunicacoes_djen": volumes.comunicacoes,
        "ementas_aceitas": volumes.ementas_aceitas,
        "substituicoes_por_camada": volumes.substituicoes,
        "quarentena": volumes.quarentena,
        "rejeitados_anonimizacao": volumes.rejeitados_anonimizacao,
        "falhas_parser": volumes.falhas_parser,
        "descartados_segredo_tjdft": volumes.descartados_segredo,
        "unidades_com_erro": volumes.erros,
        "camadas": list(CAMADAS),
    }
