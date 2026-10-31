# BuscaJus

Busca gratuita de jurisprudência brasileira por contexto (semântica), a partir de fontes oficiais. Cada resultado traz o número do processo, os dados de citação e o link para a fonte oficial.

- Arquitetura e decisões: [ARCHITECTURE.md](ARCHITECTURE.md)
- Backlog por fases: [BACKLOG.md](BACKLOG.md)

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `backend/` | Pacote Python `buscajus` (FastAPI, ingestão, embeddings), migrações Alembic e testes |
| `backend/src/buscajus/api/` | API HTTP |
| `backend/src/buscajus/ingest/` | Conectores (DJEN, TJDFT), anonimização, normalização, upsert |
| `backend/src/buscajus/embed/` | Geração de embeddings |
| `backend/src/buscajus/db/` | Acesso a banco e migrações |
| `backend/src/buscajus/core/` | Configuração e logging |
| `frontend/` | Interface web (Next.js) |
| `compose.yaml` | Ambiente local: Postgres + pgvector, migrações, API, worker e web |
| `compose.prod.yaml` | Produção: Caddy, redes internas, limites de memória e backup agendado (`compose.prod.8gb.yaml`: limites reduzidos para 8 GB) |
| `ops/` | Backup, restauração e Caddyfile |
| `docs/` | Implantação, lançamento, backup e relatórios |
| `data/` | Dados locais (brutos filtrados, modelos); fora do git |

## Rodar com Docker Compose

```bash
cp .env.example .env        # opcional: os padrões já funcionam
docker compose up --build
```

- API: http://localhost:8000/api/v1/saude (documentação em `/docs`)
- Web: http://localhost:3000

O serviço `migracoes` aplica as migrações antes de a API e o worker subirem.

## Desenvolvimento

Requisitos: [uv](https://docs.astral.sh/uv/) (Python 3.12 é instalado por ele), Node 24 e pnpm.

No Codespaces, o [devcontainer](.devcontainer/devcontainer.json) instala o uv e as dependências e libera o tráfego entre as redes do Docker, que o Codespace bloqueia por padrão (só para desenvolvimento).

### Backend

```bash
cd backend
uv sync
uv run ruff format . && uv run ruff check . && uv run mypy
uv run pytest
```

Os testes marcados com `banco` precisam de um Postgres com pgvector e de um banco descartável:

```bash
docker compose up -d db
docker compose exec db psql -U buscajus -c "CREATE DATABASE buscajus_teste"
BUSCAJUS_TEST_DATABASE_URL=postgresql+psycopg://buscajus:buscajus@127.0.0.1:5432/buscajus_teste uv run pytest
```

No Windows (PowerShell), defina a variável antes:
`$env:BUSCAJUS_TEST_DATABASE_URL='postgresql+psycopg://buscajus:buscajus@127.0.0.1:5432/buscajus_teste'`.
Use `127.0.0.1`, não `localhost`: no Windows, `localhost` tenta `::1` primeiro e cada conexão
perde ~2 s, o que faz a suíte parecer travada.

Migrações fora do compose: `uv run alembic upgrade head` (usa `BUSCAJUS_DATABASE_URL`).

### Ingestão

```bash
# Coleta os cadernos do DJEN de um período (do mais recente ao mais antigo); --forcar refaz os concluídos
uv run buscajus ingest djen --tribunal TJPR --de 2026-10-01 --ate 2026-10-15 [--forcar]

# Refaz parser, PII residual e upsert a partir do bruto filtrado, sem rede
uv run buscajus ingest reprocessar --fonte djen [--tribunal TJPR] --de 2026-10-01 --ate 2026-10-15

# Confere a versão dos cadernos recentes e reprocessa os que mudaram (checagem pontual dos ausentes)
uv run buscajus ingest verificar-versoes --tribunal TJPR [--dias 30]

# Coleta os acórdãos do TJDFT por dia de publicação (do mais recente ao mais antigo); --forcar recoleta
uv run buscajus ingest tjdft --de 2026-10-01 --ate 2026-10-15 [--forcar]

# Confere os dias de 31 a 90 dias atrás do TJDFT (tamanho 1 por dia) e recoleta os que mudaram
uv run buscajus ingest conferir-tjdft [--de-dias 31] [--ate-dias 90]

# Estado e contagens de cada unidade de coleta
uv run buscajus ingest status [--fonte djen|tjdft] [--tribunal TJPR] [--de AAAA-MM-DD] [--ate AAAA-MM-DD]
```

- **As coletas exigem o modelo de NER** (`BUSCAJUS_ANONIMIZACAO__MODELO_NER`, camada 2 da anonimização, F1-36/F1-37). Sem ele, `ingest djen`, `ingest tjdft` e `verificar-versoes` saem com código 2 antes de qualquer acesso à fonte.
- A API do DJEN bloqueia IPs fora do Brasil: a coleta roda de uma máquina no Brasil.
- O relatório de `status` traz comunicações lidas, acórdãos aceitos, rejeitados pela anonimização, quarentena, cancelados, falhas de parser, respostas 429 e o último erro; nas janelas do TJDFT, também os descartados por segredo de justiça (só a contagem).
- Os comandos imprimem só o resultado (JSON) na saída padrão; os logs, em JSON, vão para a saída de erro.
- Acórdão removido (segredo superveniente ou pedido de remoção aceito) perde ementa e decisão no banco e no histórico, e os arquivos brutos são reescritos sem ele; um bloqueio impede que volte.
- No TJDFT, cada dia é conferido antes de gravar: se os uuids únicos não baterem com o total da API, o dia é relido (até 3 vezes) e, persistindo, fica com erro.
- O agendador do `worker` (DJEN: coleta diária e checagem de versões; TJDFT: dia mais recente, reconsulta do anterior e recoleta dos últimos 30 dias) fica desligado por padrão (`BUSCAJUS_AGENDADOR__ATIVO=false`).
- A tabela de classes processuais (`classe_cnj`) vem da TPU do CNJ, num arquivo versionado. Para atualizá-la: `uv run python scripts/atualizar_tpu.py` (em `backend/`) e uma migração que chame `carregar_tpu`.

### API

```bash
# Contrato da API (versionado em frontend/openapi.json; regenere quando os esquemas mudarem)
uv run buscajus api openapi > ../frontend/openapi.json

# API com dados sintéticos fixos, para o frontend antes da busca real
BUSCAJUS_API__MOCK=true uv run uvicorn buscajus.api.app:criar_app --factory --reload

# Pedidos de remoção: listar, decidir (aceitar apaga o conteúdo; ver ARCHITECTURE 4.5) e
# apagar o e-mail dos pedidos resolvidos há mais de api.retencao_contato_dias
uv run buscajus remocao listar
uv run buscajus remocao aceitar 12 --decisao "nome de parte no texto"
uv run buscajus remocao rejeitar 13 --decisao "não há dado pessoal no texto"
uv run buscajus remocao limpar-contatos
```

- A busca usa o full-text do Postgres; o ramo vetorial entra depois que o modelo de embeddings for fixado (F3-06).
- Limite por IP: 60 consultas por minuto (busca, detalhe, processo e relatores; `/filtros` e `/cobertura` ficam fora, com cache) e 5 pedidos de remoção por hora (`BUSCAJUS_API__*`).

### Avaliação da busca (Fase 3)

```bash
# Modelos de embedding ficam num grupo opcional (torch CPU)
uv sync --group embeddings

# Pool top-20 de cada sistema para julgamento (planilha CSV com a coluna relevancia)
uv run buscajus eval pool --consultas eval/consultas.yaml --saida pool.csv \
    --modelo intfloat/multilingual-e5-base@<revisão> [--modelo ...] [--limite 50000]

# nDCG@10, Recall@50, MRR e latência com a planilha julgada
uv run buscajus eval metricas --consultas eval/consultas.yaml --julgamentos julgado.csv --modelo ...
```

- O pool traz o início das ementas: mantenha o CSV fora do repositório.
- `eval/consultas.yaml` é uma proposta inicial, pendente de revisão jurídica (F3-01).
- Testes com o modelo real minúsculo: `uv run pytest -m modelo` (exigem o grupo `embeddings`).

### Frontend

```bash
cd frontend
pnpm install
pnpm dev            # usa a API em API_URL (padrão: http://127.0.0.1:8000)
pnpm test           # Vitest + Testing Library
pnpm lint && pnpm typecheck && pnpm format:check && pnpm build
pnpm exec playwright install chromium   # uma vez
pnpm e2e            # Playwright: sobe a API mock (porta 8100) e o site construído (3100)
```

- `CONTATO_EMAIL` (opcional): e-mail do projeto exibido como texto na página de remoção.
- `API_TIMEOUT_MS` (padrão 8000) e `API_TIMEOUT_SITUACAO_MS` (3000): timeouts das chamadas à API; no detalhe do acórdão, API fora do ar ou lenta vira 503.
- Sem banco: suba a API em modo mock (`BUSCAJUS_API__MOCK=true`, seção API acima) e rode `pnpm dev`.
- Os tipos da API vêm de `openapi.json`. Quando o contrato mudar: `uv run buscajus api openapi > ../frontend/openapi.json` em `backend/` e `pnpm api:gerar` aqui; o build falha se os tipos estiverem desatualizados.
- Dependências novas só entram com 14 dias de publicação (`minimumReleaseAge` em `pnpm-workspace.yaml`).

### Backup e restauração

```bash
ops/backup.sh /caminho/dos/backups          # pg_dump dentro do contêiner db, com retenção (avulso)
ops/restaurar.sh arquivo.dump [banco]       # restaura num banco separado e mostra contagens
```

Procedimento e teste de restauração em [docs/backup.md](docs/backup.md). Em produção, o serviço `backup` do `compose.prod.yaml` agenda o backup diário.

### Produção

```bash
cp .env.prod.example .env      # DOMINIO, EMAIL_ACME, POSTGRES_PASSWORD, BACKUP_*
docker compose up -d --build   # o .env aponta COMPOSE_FILE=compose.prod.yaml
```

Só o proxy reverso (Caddy) fica exposto; `web` e `api` não. Na API, `BUSCAJUS_API__PROXIES_CONFIAVEIS=1` e `BUSCAJUS_AMBIENTE=producao` (que recusa a senha padrão do banco), já fixos no compose. Guia em [docs/implantacao.md](docs/implantacao.md), checklist em [docs/lancamento.md](docs/lancamento.md) e decisões no ARCHITECTURE.md, seção 12.2.

### Pre-commit

```bash
uvx pre-commit install
```

Os hooks rodam ruff e prettier com as versões dos lockfiles e bloqueiam arquivos ZIP fora de `backend/tests/fixtures/` e qualquer arquivo de `ner-avaliacao-privado/`.

## Privacidade

Não guardamos nomes de partes nem de advogados, e nomes de pessoas físicas citados nas ementas são trocados por iniciais antes de qualquer gravação. Os detalhes estão no [ARCHITECTURE.md](ARCHITECTURE.md), seção 6.
