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

## Ambiente

- APIs do DJEN bloqueiam acesso de fora do Brasil; não contorne (sem proxy ou VPN).
- Coleta com dados reais roda só pelo `worker` do `compose.yaml` (contêiner Linux, tmpfs para
  cadernos), nunca direto no Windows: lá a permissão `0700` da área temporária não se aplica.
- Versões fixadas: Python 3.12 e uv 0.13.4 (backend), Node 24 e pnpm 12.3.4 (frontend).
- Checagens do CI: em `backend/`, `uv run ruff format --check .`, `uv run ruff check .`,
  `uv run mypy`, `uv run pytest`; em `frontend/`, `pnpm lint`, `pnpm typecheck`,
  `pnpm format:check`, `pnpm build`. Testes de banco exigem `BUSCAJUS_TEST_DATABASE_URL`.
