# Anotação do conjunto de avaliação do NER (F1-36)

Este guia é para quem vai montar e anotar o conjunto de ~300 ementas usado para escolher o modelo de reconhecimento de nomes de pessoas (camada 2 da anonimização, seção 6.3 do [ARCHITECTURE.md](../ARCHITECTURE.md)). O resultado é o relatório `docs/avaliacao-ner.md`, que traz só métricas agregadas, e a decisão do modelo.

## Condições obrigatórias

As ementas contêm nomes de vítimas, testemunhas e corréus, mesmo depois da camada 1. Por isso, valem estas regras:

- **Máquina local, com disco criptografado, acessível só aos anotadores.** Nada de pasta sincronizada com nuvem (Drive, OneDrive, iCloud, Dropbox).
- **Fora do repositório e do CI.** A pasta padrão é `ner-avaliacao-privado/`, que está no `.gitignore` e é bloqueada pelo pre-commit. O ideal é usar uma pasta fora do clone. O script de amostragem recusa gravar dentro do repositório (exceto nessa pasta) e se recusa a rodar em CI.
- **Nenhum envio a terceiros.** Isso inclui serviços de anotação, APIs de IA (inclusive assistentes de código) e tradutores online. A pré-anotação usa só modelo local.
- **Só o texto da ementa e o estrato.** O arquivo não tem número do processo, link, destinatários nem id da comunicação.
- **Exclusão na data fixada na issue do F1-36.** No máximo 30 dias depois da decisão do modelo, o conjunto e as anotações são apagados, e a exclusão é registrada no BACKLOG (F1-40).

## Passo a passo

Os comandos rodam em `backend/`, numa máquina no Brasil (a API do DJEN bloqueia IPs de fora).

1. **Amostra.** Baixa os cadernos das datas pedidas, aplica a camada 1 e o mascaramento de CPF e sorteia 50% de ementas criminais, 25% de família (11ª e 12ª Câmaras Cíveis, que no TJPR julgam família, sucessões e ECA, como confirmado com o tribunal) e 25% de cíveis:

   ```bash
   uv run python scripts/ner_amostragem.py --saida /caminho/criptografado/ner-avaliacao-privado \
       2026-10-13 2026-10-14 2026-10-15
   ```

   O terminal mostra só contagens. O arquivo gerado é `amostra.jsonl`, uma ementa por linha, com `id_amostra`, `estrato`, `texto` e `texto_anotado` (vazio).

2. **Pré-anotação, opcional e local.** Um modelo local marca os nomes que encontrar, e a pessoa só corrige:

   ```bash
   uv run --with "spacy>=3.8,<3.9" python -m spacy download pt_core_news_lg
   uv run --with "spacy>=3.8,<3.9" python scripts/ner_avaliacao.py preanotar \
       --modelo spacy --entrada PASTA/amostra.jsonl --saida PASTA/amostra-anotada.jsonl
   ```

   A pré-anotação favorece o modelo que a gerou. Por isso, revise cada ementa inteira, não só as marcas.

3. **Anotação.** Edite o campo `texto_anotado` de cada linha, que começa como cópia do `texto` (ou pré-anotado), marcando **todo** nome de pessoa:

   | Marca | Quando usar | Exemplos |
   |---|---|---|
   | `[[...]]` | Pessoa física que deve ser anonimizada | parte, vítima, testemunha, corréu, advogado, perito, servidor citado pelo nome, informante |
   | `{{...}}` | Nome que deve ficar | relator do acórdão; magistrado citado em precedente (`Rel. Min. Fulano`); doutrinador; epônimo (`Lei Maria da Penha`) |

   Regras:

   - Marque o nome como aparece, inteiro ou parcial: `[[Fulano]]`, `[[F. de Tal]]`, `[[FULANO DE TAL]]`. Não marque iniciais que já vieram da camada 1 (`J.S.S.`).
   - Não inclua o título na marca: `Rel. Min. {{Fulano de Tal}}`, `a vítima [[Fulana]]`.
   - Nomes de empresas, órgãos e entes públicos não são marcados.
   - Fora as marcas, não mude nada no texto. O validador confere que o texto sem as marcas é idêntico ao original.
   - Na dúvida se é pessoa física, marque com `[[...]]`.

4. **Validação.**

   ```bash
   uv run python scripts/ner_avaliacao.py validar --entrada PASTA/amostra-anotada.jsonl
   ```

   O validador mostra só o `id_amostra` e o tipo de problema.

5. **Avaliação.** Compara o spaCy `pt_core_news_lg` e um modelo treinado no LeNER-Br (`pierreguillou/ner-bert-base-cased-pt-lenerbr` por padrão; outro pode ser passado em `--lenerbr`), em vários limiares de confiança, com as exceções da camada 2 já aplicadas:

   ```bash
   uv run --with "spacy>=3.8,<3.9" --with "transformers>=4.44,<5" --with torch \
       python scripts/ner_avaliacao.py avaliar --entrada PASTA/amostra-anotada.jsonl \
       --relatorio ../docs/avaliacao-ner.md
   ```

   O relatório traz, por estrato e no total: recall com o nome inteiro substituído, recall com pelo menos um token substituído, precisão, nomes a manter preservados e tempo por ementa. Antes de versionar, confira que o relatório não tem nenhum trecho de ementa.

6. **Decisão.** Preencha a seção "Decisão" do relatório com o modelo, o limiar, a meta de recall e a lista de exceções, e registre a decisão no BACKLOG (F1-36). A meta favorece o recall: um nome trocado por engano custa legibilidade; um que escapa é um vazamento.

7. **Exclusão (F1-40).** Na data fixada, apague a pasta, inclusive cópias, lixeira e backups locais, e registre data, responsável e método no BACKLOG.
