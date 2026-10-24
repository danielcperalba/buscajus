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
| `docs/` | Relatórios de carga e de avaliação |
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
BUSCAJUS_TEST_DATABASE_URL=postgresql+psycopg://buscajus:buscajus@localhost:5432/buscajus_teste uv run pytest
```

Migrações fora do compose: `uv run alembic upgrade head` (usa `BUSCAJUS_DATABASE_URL`).

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
pnpm lint && pnpm typecheck && pnpm format:check && pnpm build
```

### Pre-commit

```bash
uvx pre-commit install
```

Os hooks rodam ruff e prettier com as versões dos lockfiles e bloqueiam arquivos ZIP fora de `backend/tests/fixtures/` e qualquer arquivo de `ner-avaliacao-privado/`.

## Privacidade

Não guardamos nomes de partes nem de advogados, e nomes de pessoas físicas citados nas ementas são trocados por iniciais antes de qualquer gravação. Os detalhes estão no [ARCHITECTURE.md](ARCHITECTURE.md), seção 6.
