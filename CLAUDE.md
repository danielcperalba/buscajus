# BuscaJus — instruções para agentes

Plataforma gratuita de busca de jurisprudência por contexto. Decisões técnicas em
[ARCHITECTURE.md](ARCHITECTURE.md); tarefas, status e pontos de parada em [BACKLOG.md](BACKLOG.md).
Leia os dois antes de começar.

## Regra de dados reais (obrigatória)

Um agente de IA rodando na nuvem é um terceiro para a LGPD. Cadernos do DJEN e respostas do TJDFT
trazem nomes de partes, advogados, vítimas e testemunhas.

- Nunca leia, imprima ou coloque no contexto textos, ementas, nomes ou números de processo reais.
- Para investigar dados reais, escreva scripts que imprimam só contagens, tipos, formatos e
  estatísticas (padrão: `backend/scripts/spike_caderno_djen.py`). Revise o script antes de rodar.
- Fixtures são sempre sintéticas: nomes marcadores, processos do ano 2099, CPFs de exemplo. O
  repositório é público; nunca versione caderno, resposta ou trecho real.
- Nunca acesse `ner-avaliacao-privado/` nem o conjunto do F1-36.
- Arquivos temporários de cadernos reais são apagados ao final, inclusive em erro.

## Fluxo de trabalho

- Uma branch e um PR por bloco de tarefas, com o ID da tarefa no título dos commits.
- CI verde antes do próximo bloco. **Os merges são feitos pelo dono do repositório**, não pelo agente.
- Atualize o status no BACKLOG.md e o ARCHITECTURE.md quando uma decisão mudar.
- Não execute tarefas marcadas como ponto de parada no BACKLOG sem aprovação explícita.

## Credenciais

- Operações no GitHub (push, abrir PR, acompanhar o CI) só pelo `gh`, autenticado pelo dono do
  repositório; o `git` já usa o `gh` como credencial.
- Nunca extraia, imprima ou use tokens de gerenciadores de credenciais (`git credential fill`,
  Git Credential Manager, keyring) nem os passe para chamadas diretas à API.
- Se o `gh` estiver deslogado ou falhar por autenticação, pare e peça ao dono do repositório.
- Nunca peça nem aceite tokens ou senhas pelo chat; o login é sempre feito pelo dono, no terminal dele.

## Ambiente

- APIs do DJEN bloqueiam acesso de fora do Brasil; não contorne (sem proxy ou VPN).
- Coleta com dados reais roda só pelo `worker` do `compose.yaml` (contêiner Linux, tmpfs para
  cadernos), nunca direto no Windows: lá a permissão `0700` da área temporária não se aplica.
- Versões fixadas: Python 3.12 e uv 0.13.4 (backend), Node 24 e pnpm 12.3.4 (frontend).
- Checagens do CI: em `backend/`, `uv run ruff format --check .`, `uv run ruff check .`,
  `uv run mypy`, `uv run pytest --cov` (piso de 90% nos conectores); em `frontend/`, `pnpm lint`, `pnpm typecheck`,
  `pnpm format:check`, `pnpm test`, `pnpm build` e, com o build pronto, `pnpm e2e` (Playwright contra a API mock). Testes de banco exigem `BUSCAJUS_TEST_DATABASE_URL`
  apontando para `127.0.0.1` (não `localhost`; ver README).
