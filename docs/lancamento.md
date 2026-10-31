# Checklist de lançamento (F8-06)

Marque cada item com a data e quem conferiu. O guia de implantação está em [implantacao.md](implantacao.md).

## Decisões pendentes do dono do projeto

- [ ] **Revisão jurídica das páginas** `/sobre` e `/privacidade` (rascunhos do F5-10), incluindo a base legal, a retenção do e-mail dos pedidos de remoção (`api.retencao_contato_dias`, 90 dias) e o aviso de reprodução da fonte oficial.
- [ ] **Revisão jurídica da lista de epônimos** (nomes que a camada 2 do NER mantém no texto, em `ingest/anonimizacao/camada2.py`).
- [ ] **`CONTATO_EMAIL`**: e-mail próprio do projeto, exibido na página de remoção; também em `BUSCAJUS_HTTP__CONTATO` (identificação nas requisições às fontes).
- [ ] **Anonimização aprovada na revisão por amostra** (F1-42): 0 vazamentos em 100 ementas revisadas do piloto local (F1-43), com o resultado em `docs/revisao-anonimizacao.md`, e o piloto limpo (F1-44) com a exclusão registrada (F1-40). Modelo de NER já escolhido e implementado (F1-36, F1-37).
- [ ] **Cargas iniciais**: carga inicial do TJPR (F1-29), carga histórica desde 23/07/2025 (F1-33) e carga do TJDFT (F2-11), todas depois do NER, rodadas no servidor (`docker compose run --rm worker …`), com o relatório de `ingest status` registrado.
- [ ] **Revisão da quarentena** da carga inicial (F6-10).
- [ ] **Ligar o agendador** (`BUSCAJUS_AGENDADOR__ATIVO=true`) depois das cargas conferidas.
- [ ] **Revisão mensal** depois do lançamento: amostra de 30 ementas novas (`buscajus revisao amostrar --n 30 --desde …`), com o mesmo fluxo.
- [ ] **Busca semântica**: lançar só com o full-text, ou esperar o modelo de embeddings (F3-05 em diante, F4-05) e a avaliação (F6-07). Hoje o ramo vetorial está desligado.
- [ ] **Servidor e domínio**: provedor no Brasil, plano (requisitos em implantacao.md), domínio e destino da cópia externa dos backups.

## Técnico: servidor

- [ ] Servidor no Brasil, Linux, com 16 GB de RAM (ou 8 GB com `compose.prod.8gb.yaml`, só full-text) e o disco dos requisitos, **com criptografia em repouso**; acesso SSH só por chave, sem login de root.
- [ ] Pesos do NER no volume `modelos` (`docker compose run --rm worker buscajus modelos baixar-ner`).
- [ ] Firewall: só 22 (ou a porta do SSH), 80/tcp, 443/tcp e 443/udp abertas.
- [ ] Atualizações automáticas de segurança do sistema ligadas.
- [ ] DNS A/AAAA do domínio apontando para o servidor.
- [ ] `.env` a partir do `.env.prod.example`, com `chmod 600`; senha do banco forte e única; nada do `.env` no git.

## Técnico: implantação

- [ ] `docker compose up -d --build` com todos os serviços `healthy` e `migracoes` com código 0.
- [ ] Certificado TLS emitido; `http://` redireciona para `https://`.
- [ ] Cabeçalhos presentes: `Strict-Transport-Security`, `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`; sem `Server` nem `X-Powered-By`.
- [ ] Nenhuma violação de CSP no console do navegador em `/`, `/busca`, `/acordao/<id>`, `/sobre` e `/remocao`.
- [ ] Portas 3000, 8000 e 5432 inacessíveis de fora (`curl` a partir de outra máquina).
- [ ] Limite de taxa: muitas buscas com `X-Forwarded-For` falsificados diferentes ainda recebem o aviso de limite (o IP considerado é o da conexão).
- [ ] Log do Caddy sem query string nem `Referer`, com IP truncado; logs de `api`, `web` e `worker` sem consultas.
- [ ] `/acordao/<id inexistente>` responde 404; com a API parada (`docker compose stop api`), `/acordao/<id>` responde 503 em ~3 s com a página de indisponibilidade; depois, `docker compose start api`.
- [ ] `BUSCAJUS_AMBIENTE=producao` e `BUSCAJUS_API__PROXIES_CONFIAVEIS=1` em vigor (`docker compose exec api env | grep BUSCAJUS_A`).
- [ ] `BUSCAJUS_API__MOCK=false` (a busca vem do banco, não dos dados sintéticos).

## Técnico: backup e recuperação

- [ ] Primeiro backup feito ao subir; `docker compose ps backup` saudável no dia seguinte (backup agendado rodou).
- [ ] Cópia externa diária configurada e conferida no destino.
- [ ] Restauração testada a partir da cópia externa num banco separado (`ops/restaurar.sh`, só contagens), registrada em backup.md.

## Técnico: conteúdo e privacidade

- [ ] Verificações automáticas de privacidade e segredo (F6-03, F6-04) verdes na versão implantada.
- [ ] Amostra da base real conferida só por contagens e agregados (nenhum texto real fora do servidor).
- [ ] Canal de remoção testado de ponta a ponta com um pedido sintético (`buscajus remocao listar` e `rejeitar`).
- [ ] `/sobre` mostra a cobertura real por tribunal e período.

## Depois do lançamento

- [ ] Acompanhar `ingest status`, a quarentena e os logs do `worker` na primeira semana.
- [ ] Teste de carga leve na base de 90 dias (F6-08) e notas de escala (F7-07).
- [ ] Teste de restauração trimestral.
