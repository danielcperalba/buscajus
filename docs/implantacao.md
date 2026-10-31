# Implantação em produção (F8-05)

Guia para colocar o BuscaJus no ar num servidor próprio ou VPS, do zero. Tudo roda pelo [`compose.prod.yaml`](../compose.prod.yaml); o servidor ainda não foi escolhido, então nada aqui depende de provedor. Itens pendentes antes do lançamento: [lancamento.md](lancamento.md).

## Arquitetura em produção

```
internet ──80/443──▶ caddy ──(rede borda)──▶ web (Next.js) ──(rede interna)──▶ api ──▶ db
                                                                         worker ──▶ db
                                                                         worker ──(rede saida)──▶ DJEN, TJDFT
                                                                         backup ──▶ db  → BACKUP_DIR
```

| Serviço | Papel | Exposição | Limite de memória |
|---|---|---|---|
| `caddy` | TLS automático, cabeçalhos de segurança, log sem query string | **único** com portas no host (80, 443 TCP/UDP) | 256 MB |
| `web` | Next.js (páginas no servidor) | redes `borda` e `interna`, sem portas | 512 MB |
| `api` | FastAPI | rede `interna`, sem portas e sem saída para a internet | 2,5 GB |
| `worker` | coleta agendada (desligada por padrão) | rede `interna` + `saida` (só ele acessa as fontes) | 3,5 GB (inclui o tmpfs de 1,1 GB) |
| `db` | Postgres 16 + pgvector | rede `interna`, sem portas | 2 GB |
| `backup` | `pg_dump` diário com retenção | rede `interna` | 512 MB |
| `migracoes` | `alembic upgrade head` a cada subida | rede `interna` | 512 MB |

As redes `borda` e `interna` são `internal`: nada nelas sai para a internet, e o Caddy não alcança a API nem o banco. Todos os serviços reiniciam sozinhos (`unless-stopped`), têm healthcheck (menos o `worker`, que não serve HTTP) e logs do Docker com rotação (5 × 10 MB por contêiner).

## Requisitos do servidor

- **No Brasil.** A API do DJEN bloqueia IPs de fora do país; não use proxy nem VPN para contornar. A coleta roda no `worker` deste servidor.
- **Linux** com Docker Engine 24+ e o plugin Compose v2 (`docker compose`). O tmpfs dos cadernos precisa de Linux (a permissão `0700` não se aplica no Windows).
- **CPU**: 2 vCPU bastam sem embeddings; 4 vCPU quando o modelo de embeddings entrar (F3-06).
- **RAM**: mínimo **16 GB**.
  - Os limites do `compose.prod.yaml` somam **8,75 GB** (db 2 + api 2,5 + worker 3,5 + web 0,5 + caddy 0,25), mais 0,5 GB do `backup` (que usa pouco), o sistema e o cache de disco do Postgres. O limite do `worker` inclui o tmpfs de 1.100 MB (um caderno de até 1 GB fica em RAM durante a leitura), o modelo de NER e o Python; o da `api` já reserva espaço para o modelo de embeddings (e5-base, ~1,5–2 GB).
  - Uso típico hoje é menor (sem embeddings, a `api` fica em ~0,3 GB e o `worker` ocioso em ~0,2 GB), mas os limites valem para o pior caso: um caderno grande no tmpfs junto com a geração de embeddings.
  - O maior caderno do TJPR visto no F1-01 tem 163 MB; o tmpfs só ocupa RAM com o ZIP em uso.
- **Opção de 8 GB** (limites reduzidos, [`compose.prod.8gb.yaml`](../compose.prod.8gb.yaml)): no `.env`, `COMPOSE_FILE=compose.prod.yaml:compose.prod.8gb.yaml`. Os limites passam a somar 6,25 GB (db 1,5 com `shared_buffers` de 256 MB, api 0,75, worker 3, web 0,5, caddy 0,25). O que se perde:
  - **embeddings na `api`**: a busca fica só no full-text, sem o ramo vetorial (busca semântica), quando ele for ligado (F3-06);
  - **geração de embeddings no `worker`**: teria de rodar em outra máquina e chegar pelo banco;
  - **cache do Postgres** menor: buscas mais lentas à medida que a base cresce (medir no F6-08).

  Serve para lançar só com o full-text; para a busca semântica, migre para 16 GB.
- **Disco**: SSD, **80 GB** recomendados. Estimativa para 90 dias de TJPR + TJDFT (~95 mil ementas do TJPR, a ~1.500 por dia útil, e ~21 mil acórdãos do TJDFT, a ~7 mil a cada 30 dias):

  | Item | Estimativa |
  |---|---|
  | Banco (tabelas, histórico, GIN) | 1–1,5 GB |
  | Vetores e HNSW, quando entrarem | ~1 GB |
  | Brutos filtrados (volume `raw`) | centenas de MB |
  | Backups (14 dias × dump comprimido) | 5–10 GB |
  | Imagens Docker e cache de build | 8–12 GB |
  | Sistema, logs, folga | 10 GB |
  | **Total** | **~30 GB** |

  A carga histórica do TJPR desde 23/07/2025 (F1-33) multiplica o banco por ~3; 80 GB cobrem com folga.
- **Rede**: portas 80 e 443 (TCP) e 443 (UDP, HTTP/3) abertas; o resto fechado no firewall. Tráfego de saída do DJEN: ~57–163 MB por dia por tribunal.
- **DNS**: registro A (e AAAA, se houver IPv6) do domínio apontando para o servidor **antes** de subir o Caddy, para a emissão do certificado.

## Do zero ao site no ar

1. **Servidor**: atualize o sistema, crie um usuário sem root para operar, instale o Docker Engine e o plugin Compose e ative o firewall:

   ```bash
   sudo ufw default deny incoming && sudo ufw allow OpenSSH \
     && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw allow 443/udp && sudo ufw enable
   ```

   Atenção: portas publicadas pelo Docker passam por fora do `ufw`. Por isso só o `caddy` publica portas no `compose.prod.yaml`; não acrescente `ports` a outros serviços.

2. **Código**:

   ```bash
   sudo mkdir -p /srv/buscajus /srv/backups/buscajus && sudo chown "$USER" /srv/buscajus /srv/backups/buscajus
   git clone https://github.com/danielcperalba/buscajus.git /srv/buscajus
   cd /srv/buscajus && git checkout <tag ou commit aprovado>
   ```

3. **Configuração**:

   ```bash
   cp .env.prod.example .env && chmod 600 .env
   ```

   Preencha `DOMINIO`, `EMAIL_ACME`, `POSTGRES_PASSWORD` (`openssl rand -base64 32 | tr -d '/+='`), `BACKUP_DIR`, `BACKUP_UID` e `BACKUP_GID` (saída de `id -u` e `id -g` do usuário de operação, dono de `BACKUP_DIR`), `VERSAO` (ex.: o commit) e, quando decididos, `CONTATO_EMAIL` e `BUSCAJUS_HTTP__CONTATO`. O `COMPOSE_FILE=compose.prod.yaml` do `.env` faz todo `docker compose` usar o compose de produção.

   Já fixos no `compose.prod.yaml`, sem precisar de `.env`: `BUSCAJUS_AMBIENTE=producao` (recusa a senha padrão do banco) e `BUSCAJUS_API__PROXIES_CONFIAVEIS=1` (vale o IP que o Caddy põe no `X-Forwarded-For`; ARCHITECTURE.md, seção 12.2).

4. **Subir**:

   ```bash
   docker compose up -d --build
   docker compose ps          # todos "healthy", migracoes "exited (0)"
   ```

   A ordem é automática: `db` saudável → `migracoes` → `api` e `worker` → `web` → `caddy`. O Caddy obtém o certificado no primeiro acesso ao domínio (veja `docker compose logs caddy`).

5. **Conferir**:

   ```bash
   curl -sI https://$DOMINIO/sobre            # 200, Strict-Transport-Security, Content-Security-Policy
   curl -s -o /dev/null -w '%{http_code}\n' https://$DOMINIO/acordao/999999999   # 404
   curl -s -m 3 http://<ip do servidor>:3000/ ; curl -s -m 3 http://<ip do servidor>:8000/   # devem falhar
   docker compose logs caddy | tail -3        # "uri" sem query string, IP truncado
   ls -l /srv/backups/buscajus                # primeiro backup feito ao subir
   ```

   Com a base vazia, a busca não traz resultados e `/sobre` mostra a cobertura zerada; as cargas iniciais estão em [lancamento.md](lancamento.md).

## Migrações

O serviço `migracoes` roda `alembic upgrade head` em toda subida, antes da `api` e do `worker` (que só sobem se ele terminar com código 0). Para rodar ou conferir à mão:

```bash
docker compose run --rm migracoes                          # aplica as pendentes
docker compose run --rm migracoes alembic current          # versão atual
docker compose run --rm migracoes alembic history | head   # versões disponíveis
```

Faça um backup antes de atualizar para uma versão com migração nova (seção [Atualizar a versão](#atualizar-a-versão)). As migrações não têm `downgrade` testado: para voltar atrás, restaure o backup.

## Coleta manual e agendador

A coleta exige o modelo de NER (camada 2 da anonimização). Sem `BUSCAJUS_ANONIMIZACAO__MODELO_NER`, `ingest djen` e `ingest tjdft` saem com código 2 antes de acessar a fonte, e o agendador não coleta nada. Hoje o carregamento do modelo ainda não existe (F1-37, que depende da validação do F1-36).

Comandos pontuais rodam no contêiner do `worker` (mesmos volumes, tmpfs e rede de saída):

```bash
docker compose run --rm worker buscajus ingest status
docker compose run --rm worker buscajus ingest tjdft --de 2026-10-01 --ate 2026-10-15
```

**Ligar o agendador**, só depois que o NER estiver validado (F1-36 aprovado e F1-37 implementado e testado) e com as cargas iniciais conferidas:

1. Implante a versão com o F1-37 e coloque o modelo onde a configuração dele indicar (volume `modelos`, montado em `/dados/modelos`).
2. No `.env`: `BUSCAJUS_ANONIMIZACAO__MODELO_NER=<modelo>`; rode uma coleta manual de um dia e confira `ingest status` (rejeitados, quarentena) antes de seguir.
3. No `.env`: `BUSCAJUS_AGENDADOR__ATIVO=true` (horários e janelas: `BUSCAJUS_AGENDADOR__*`, no `.env.example`).
4. `docker compose up -d worker` e acompanhe `docker compose logs -f worker` no primeiro ciclo.

Para desligar: `BUSCAJUS_AGENDADOR__ATIVO=false` e `docker compose up -d worker`.

## Atualizar a versão

```bash
cd /srv/buscajus
ops/backup.sh /srv/backups/buscajus     # backup avulso antes de atualizar
git fetch && git checkout <nova tag ou commit>
# confira no diff se .env.prod.example ganhou variáveis novas
sed -i "s/^VERSAO=.*/VERSAO=$(git rev-parse --short HEAD)/" .env
docker compose up -d --build     # reconstrói, roda as migrações e recria o que mudou
docker compose ps
docker image prune -f            # remove imagens antigas sem uso
```

`ops/backup.sh` faz um backup avulso no mesmo formato do serviço, pelo `db` do compose de produção (o `COMPOSE_FILE` do `.env` vale para ele). Durante o `up -d --build` o site fica indisponível por alguns segundos enquanto `web` e `api` são recriados. Para voltar à versão anterior: `git checkout` da versão antiga e `docker compose up -d --build`; se a nova tiver rodado migração, restaure o backup feito antes (próxima seção).

## Backups

O serviço `backup` faz um `pg_dump` (formato custom) ao subir, se não houver backup nas últimas 24 horas, e depois todo dia às `BACKUP_HORA_UTC` (padrão 06:30 UTC, 03:30 em Brasília). Grava `{banco}-{AAAAMMDDThhmmssZ}.dump` e `.sha256` em `BACKUP_DIR`, com o dono `BACKUP_UID:BACKUP_GID` e permissão `0600`, e apaga os com mais de `BACKUP_RETENCAO_DIAS` (padrão 14). O healthcheck do serviço fica **unhealthy** se o último backup bem-sucedido tiver mais de 26 horas: monitore com `docker compose ps backup`.

O backup não inclui a área temporária dos cadernos (tmpfs) nem o volume `raw` (brutos filtrados, recriáveis a partir das fontes) nem os certificados do Caddy (reemitidos sozinhos).

### Cópia fora do servidor

Um backup só no próprio servidor não protege contra perda do disco ou do servidor. Copie `BACKUP_DIR` diariamente para outro lugar, **depois** da hora do backup, com uma destas opções (todas por cron do usuário de operação):

- **Outro servidor via SSH** (`rsync`), com uma chave dedicada e restrita no destino:

  ```
  30 4 * * * rsync -a --delete /srv/backups/buscajus/ backup@outro-host:/backups/buscajus/
  ```

- **Armazenamento de objetos** compatível com S3 (`rclone`), com cifragem do lado do cliente (`rclone crypt`), porque o dump contém os pedidos de remoção (e-mails dos solicitantes):

  ```
  30 4 * * * rclone sync /srv/backups/buscajus cifrado:buscajus-backups
  ```

Prefira um destino no Brasil. O destino deve manter as cópias por pelo menos a mesma retenção (com `--delete`, a retenção do servidor vale também lá). Teste a restauração a partir da cópia externa pelo menos uma vez por trimestre.

## Restaurar o backup

O procedimento e o teste estão em [backup.md](backup.md). Em produção:

```bash
cd /srv/buscajus
ops/restaurar.sh /srv/backups/buscajus/<arquivo>.dump buscajus_restauracao   # confere o .sha256 e imprime só contagens
```

O script recusa restaurar por cima do banco principal. Para colocar o restaurado em uso:

1. `docker compose stop worker api web`
2. Troque o banco: renomeie o atual e o restaurado no `psql` do `db` (`ALTER DATABASE buscajus RENAME TO buscajus_antigo; ALTER DATABASE buscajus_restauracao RENAME TO buscajus;`), ou aponte `POSTGRES_DB` para o restaurado.
3. `docker compose up -d` (as migrações rodam e levam o banco à versão do código).
4. Confira e, depois de alguns dias, apague o banco antigo.

Recuperação do servidor inteiro: siga "Do zero ao site no ar" num servidor novo, pare `api`, `worker` e `web`, copie o dump da cópia externa, restaure como acima e suba de novo.

## Operação

- **Logs**: `docker compose logs -f <serviço>`. A API e o worker logam em JSON, sem consultas nem conteúdo (F0-12); o log de acesso do uvicorn é desligado. O do Caddy tira a query string, o `Referer`, cookies e o `Location`, e trunca o IP (/24 no IPv4, /48 no IPv6).
- **Detalhe do acórdão com a API fora do ar ou lenta**: o proxy do Next espera até `API_TIMEOUT_SITUACAO_MS` (3 s) e responde **503** com a página `/indisponivel` e `Retry-After: 30`, sem detalhes do erro. As demais páginas usam `API_TIMEOUT_MS` (8 s) e mostram o estado de erro.
- **Certificado**: renovado pelo Caddy; os dados ficam no volume `caddy_data` (não apague, para não esbarrar no limite de emissões do Let's Encrypt).
- **Pedidos de remoção**: `docker compose run --rm worker buscajus remocao listar` (ver README).
