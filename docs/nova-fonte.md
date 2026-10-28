# Como adicionar uma nova fonte (F7-03)

Este guia vale para duas situações: **um novo tribunal no DJEN** (só configuração) e **uma nova fonte** (um conector novo). Antes de começar, leia o [ARCHITECTURE.md](../ARCHITECTURE.md) (seções 3, 6 e 4.5) e as regras de dados reais do [CLAUDE.md](../CLAUDE.md).

**Só fontes oficiais, públicas e gratuitas.** Agregadores privados (Jusbrasil e semelhantes) nunca, nem no futuro (ARCHITECTURE.md, seção 13).

## 1. Novo tribunal no DJEN (sem código)

1. Descubra a data em que o tribunal passou a publicar "Ementa de Acórdão" no caderno, com um script só de agregados (padrão: `backend/scripts/spike_caderno_djen.py`). Nunca leia ementas, nomes ou números reais.
2. Configure:

   ```bash
   BUSCAJUS_DJEN__TRIBUNAIS='["TJPR","TJSC"]'
   BUSCAJUS_DJEN__INICIO_EMENTAS='{"TJPR":"2025-07-23","TJSC":"AAAA-MM-DD"}'
   # Só se o tribunal diferir do padrão:
   BUSCAJUS_DJEN__AJUSTES='{"TJSC":{"tipos_documento_aceitos":["Ementa de Acórdão"],"requisicoes_por_segundo":0.5,"horario":"10:00"}}'
   ```

3. Se o HTML do `texto` tiver rótulos de cabeçalho diferentes, acrescente um `PerfilParser` em `ingest/djen/parser.py` (`PERFIS`), só com dados (rótulos e tamanho mínimo da ementa).
4. Se o tribunal também tiver API própria, decida a prioridade na dedup (`BUSCAJUS_PRIORIDADE_FONTES`, F7-05). O padrão é API do tribunal > DJEN.

O teste `test_segundo_tribunal_so_por_configuracao` (em `backend/tests/ingest/test_fase7.py`) mostra que nada além disso é necessário.

## 2. Nova fonte (um conector)

### Passos

1. **Spike só com agregados**: um script em `backend/scripts/` que imprime contagens, tipos e formas de valores (dígitos → 9, letras → a), nunca valores. Revise o script antes de rodar. Registre os achados no ARCHITECTURE.md (seção 3).
2. **Fixtures sintéticas** em `backend/tests/fixtures/<fonte>/`, geradas por código, com a estrutura real e conteúdo inventado: nomes marcadores com sobrenomes inventados, processos do ano 2099, CPFs de exemplo, um registro sigiloso (se a fonte marcar segredo) e os casos de borda da paginação.
3. **Registro da fonte**: entrada em `ingest/fontes.py` (`FONTES`) e uma migração com `ALTER TYPE fonte ADD VALUE '<fonte>'` (não destrutivo). O teste `test_registro_de_fontes_bate_com_o_tipo_do_banco` confere os dois.
4. **Conector** em `ingest/<fonte>/`, implementando o protocolo `Conector` (`ingest/conector.py`):
   - `planejar(tribunal, inicio, fim)`: unidades de coleta, da mais recente para a mais antiga;
   - `coletar(unidade, checkpoint)`: lotes já filtrados, **anonimizados** e com a **lista branca** aplicada;
   - `fonte`, `lista_branca` e, para o reprocessamento, `normalizar(item)` → `AcordaoNormalizado`.
5. **Normalização** (`AcordaoNormalizado`): número CNJ (`ingest.processo`), relator (`ingest.relator`), datas convertidas para America/Sao_Paulo, `link_oficial` estável e `https`, `classe_citacao`.
6. **Fábrica e CLI**: `ingest/<fonte>/fabrica.py` (falha fechada sem NER), comando `buscajus ingest <fonte>` e, se houver coleta diária, uma tarefa no agendador (desligado por padrão).
7. **Citação**: regra da fonte na seção 9 do ARCHITECTURE.md e em `busca/citacao.py`.
8. **Remoção**: o campo de id da fonte no bruto em `ingest.remocao.CAMPO_ID`.
9. **Documentação**: ARCHITECTURE.md (fonte, campos, lista branca, regras), BACKLOG.md e README (comando).

### Regras obrigatórias

| Regra | Onde |
|---|---|
| Taxa limitada (1 req/s por padrão), sem concorrência, um único IP, sem proxy para contornar bloqueios | `ingest.http.ClienteHttp` |
| 429: `Retry-After` ou 60 s; 5xx/timeout: backoff curto; tentativas limitadas | `ingest.http` |
| Retomada: unidade concluída é pulada; interrompida recomeça ou continua do checkpoint | `ingest.runner`, `ingest.estado` |
| Anonimização **antes de qualquer gravação** (CPF + NER; camada 1 se houver destinatários), falha fechada sem NER | `ingest.anonimizacao` |
| Bruto filtrado: só itens aceitos, anonimizados, com a lista branca aplicada; campo fora dela recusa a gravação | `ingest.bruto` |
| Segredo de justiça (ou marcação equivalente): descartado antes de tudo, com regra defensiva (só passa o valor explícito de "não sigiloso") | ex.: `ingest.tjdft.campos` |
| Arquivos temporários com dados reais: área temporária (tmpfs), apagados no `finally` e na inicialização do worker | `ingest.temporario` |
| Logs e erros sem conteúdo da fonte (só ids, contagens e mensagens controladas) | `core.erros`, `core.logging` |
| Removidos e bloqueios respeitados na recoleta e no reprocessamento | `ingest.upsert`, `ingest.remocao` |
| Integridade da paginação (se paginada): itens únicos = total informado, senão relê | ex.: `ingest.tjdft.conector` |

### Checklist de testes

- [ ] Fixtures sintéticas versionadas e conferidas contra o gerador.
- [ ] Planejamento, paginação/retomada, 429, 5xx, resposta malformada (erro seguro, sem conteúdo).
- [ ] Lista branca: nenhum campo fora dela chega ao disco.
- [ ] Segredo (ou equivalente): todas as variantes inesperadas descartadas; nada no banco, no bruto nem na busca.
- [ ] Anonimização: nomes e CPFs fictícios fora do banco, do bruto e dos logs; magistrados e epônimos preservados.
- [ ] Normalização de ponta a ponta até o banco; citação.
- [ ] Remoção (F2-13): nada do removido sobra; bloqueio respeitado na recoleta.
- [ ] Cobertura dos conectores ≥ 90% (`uv run pytest --cov`).
