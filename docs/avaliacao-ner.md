# Avaliação do NER de pessoas (F1-36)

Escolha do modelo da camada 2 da anonimização (ARCHITECTURE.md, seção 6.3). **Só dados
sintéticos**: nenhuma ementa real foi usada nesta avaliação. A validação com dados reais é a
revisão por amostra das ementas já anonimizadas (seção 6.7, F1-42), feita pelo dono do projeto.

## Decisão (30/10/2026)

| Item | Valor |
|---|---|
| Modelo | [`Luciano/bertimbau-base-lener_br`](https://huggingface.co/Luciano/bertimbau-base-lener_br): BERTimbau base (`neuralmind/bert-base-portuguese-cased`, MIT) ajustado no LeNER-Br, sem treino próprio |
| Licença | **MIT** (no cartão do modelo) |
| Revisão fixada | `824f48e1b86fe24a86bd5f845f068c60468274a7` (`anonimizacao.revisao_ner`) |
| Limiar | **0,1** de probabilidade de pessoa por palavra (`anonimizacao.limiar_ner`) |
| Caixa alta | Também lê uma variante do texto sem caixa alta (`anonimizacao.caixa_ner = true`) |
| Janelas | 512 tokens com sobreposição de 128 |
| Exceções | Relator, magistrados com título antes do nome (`Rel.`, `Min.`, `Des.`, `Juiz`…) e lista de epônimos (já existentes na camada 2) |
| Pesos | Volume de modelos (`diretorio_modelos/ner`), só por `buscajus modelos baixar-ner`; carregamento `local_files_only` |
| Custo | ~135 ms por ementa em CPU (média do conjunto sintético; ~1.500 ementas/dia no TJPR ≈ 3,5 min) |

**Por quê**

- Os três modelos treinados no LeNER-Br chegam a **0 vazamentos** no conjunto sintético com a
  variante de caixa, de 0,05 a 0,7 de limiar; o spaCy `pt_core_news_lg` deixa escapar 18 de 137
  nomes (13%), sobretudo em caixa alta, nomes isolados e apelidos.
- Entre os do LeNER-Br: o `large` empata em recall e custa ~3,6× mais (490 ms por ementa);
  o `pierreguillou/ner-bert-base-cased-pt-lenerbr` empata também, mas **não declara licença**
  no repositório (sem licença, não há permissão de uso), então foi descartado.
- **Limiar 0,1**: o critério é recall primeiro (anonimizar a mais é aceitável; deixar passar
  um nome, não). Nenhum nome escapa de 0,05 a 0,7, e a precisão não muda nessa faixa; 0,1 fica
  no começo da faixa, com margem para o texto real ser mais difícil que o sintético. O primeiro
  vazamento aparece em 0,9.
- **Variante de caixa**: sem ela, o modelo escolhido deixa escapar 2 nomes em caixa alta (um
  nome com partículas e um apelido entre aspas) em ementas inteiras em maiúsculas.

## Candidatos e licenças

| Modelo | Base | Licença | Situação |
|---|---|---|---|
| `Luciano/bertimbau-base-lener_br` (rev. `824f48e`) | BERTimbau base, LeNER-Br | MIT | **Escolhido** |
| `Luciano/bertimbau-large-lener_br` (rev. `c515eb0`) | BERTimbau large, LeNER-Br | MIT | Mesmo recall, ~3,6× mais lento |
| `pierreguillou/ner-bert-base-cased-pt-lenerbr` (rev. `4ca0a39`) | BERTimbau base, LeNER-Br | Não declarada | Descartado (licença) |
| spaCy `pt_core_news_lg` 3.8.0 | WikiNER/UD | CC BY-SA 4.0 | Recall insuficiente (0,869) |

Observação: o cartão do conjunto LeNER-Br no Hugging Face (`peluz/lener_br`) marca a licença
como desconhecida. Usamos só os pesos publicados sob MIT, sem redistribuir o conjunto nem
treinar sobre ele.

## Conjunto sintético

`backend/tests/fixtures/ner/dados.py`: 70 ementas escritas do zero (60 no estilo do TJPR e 10 no do TJDFT; 35 criminais,
15 de família e 20 cíveis), com **137 nomes a anonimizar** e **9 a manter**. Todos os nomes são
fictícios; processos do ano 2099. Cobre vítima, testemunha, corréu, "o menor J." (iniciais já
aplicadas, que não contam como nome), nomes em caixa alta, nomes com partículas (`de`, `da`,
`dos`, `D'Arc`, `van der`), apelidos entre aspas (`vulgo "Tonhão"`), nomes colados a pontuação
(`Vítima:Fulana;acusado:Beltrano`), só prenome ou só sobrenome, nomes que são palavras comuns
(`Rosa`, `Vitória`, `Luz`, `Jesus Cruz da Paz`), nomes estrangeiros e hifenizados, uma ementa
toda em maiúsculas e uma com mais de 512 tokens. Os nomes a manter são relatores, ministros e
desembargadores citados em precedentes e epônimos (`Lei Maria da Penha`, `Lei Carolina
Dieckmann`). Lugares e empresas não são marcados: trocá-los por iniciais não conta como erro.

Métricas, com as exceções da camada 2 já aplicadas:

- *vazados*: nomes a anonimizar com algum token que ficou no texto;
- *recall (nome inteiro)*: nomes com todos os tokens substituídos;
- *recall (algum token)*: nomes com pelo menos um token substituído;
- *precisão*: substituições que caíram num nome a anonimizar (o resto é anonimização a mais);
- *manter preservados*: relatores, magistrados citados e epônimos que ficaram.

Reproduzir (em `backend/`; baixa os modelos para o cache do Hugging Face da máquina):

```bash
uv run --group ner --with "spacy>=3.8,<3.9" \
  --with "pt_core_news_lg @ https://github.com/explosion/spacy-models/releases/download/pt_core_news_lg-3.8.0/pt_core_news_lg-3.8.0-py3-none-any.whl" \
  python scripts/ner_avaliacao.py --saida relatorio.md
```

O job `backend-ner` do CI cobra **0 vazamentos** nesse conjunto com o modelo e o limiar
fixados (`tests/ingest/test_modelo_ner.py`).

## Resultados (30/10/2026, CPU)

### spaCy `pt_core_news_lg`

| | nomes | vazados | recall (nome inteiro) | recall (algum token) | precisão | manter preservados |
|---|---|---|---|---|---|---|
| criminal | 73 | 12 | 0.836 | 0.849 | 0.925 | 6/6 |
| família | 34 | 1 | 0.971 | 1.000 | 0.919 | 1/1 |
| cível | 30 | 5 | 0.833 | 0.867 | 0.839 | 2/2 |
| **total** | 137 | 18 | 0.869 | 0.891 | 0.904 | 9/9 |

Tempo médio por ementa: 11 ms.

### `Luciano/bertimbau-base-lener_br` (escolhido)

| | nomes | vazados | recall (nome inteiro) | recall (algum token) | precisão | manter preservados |
|---|---|---|---|---|---|---|
| limiar 0,05, sem variante de caixa | 137 | 2 | 0.985 | 0.993 | 0.993 | 9/9 |
| limiar 0,1 a 0,5, sem variante de caixa | 137 | 2 | 0.985 | 0.993 | 0.993 | 9/9 |
| limiar 0,7, sem variante de caixa | 137 | 3 | 0.978 | 0.978 | 0.993 | 9/9 |
| limiar 0,9, sem variante de caixa | 137 | 4 | 0.971 | 0.971 | 0.993 | 9/9 |
| limiar 0,05, com variante de caixa | 137 | 0 | 1.000 | 1.000 | 0.993 | 9/9 |
| **limiar 0,1, com variante de caixa** | 137 | **0** | 1.000 | 1.000 | 0.993 | 9/9 |
| limiar 0,2 a 0,7, com variante de caixa | 137 | 0 | 1.000 | 1.000 | 0.993 | 9/9 |
| limiar 0,9, com variante de caixa | 137 | 3 | 0.978 | 0.978 | 0.993 | 9/9 |

Tempo médio por ementa: 76 ms sem a variante de caixa, 135 ms com ela.

Configuração escolhida, por estrato:

| | nomes | vazados | recall (nome inteiro) | precisão | manter preservados |
|---|---|---|---|---|---|
| criminal | 73 | 0 | 1.000 | 1.000 | 6/6 |
| família | 34 | 0 | 1.000 | 0.971 | 1/1 |
| cível | 30 | 0 | 1.000 | 1.000 | 2/2 |
| **total** | 137 | 0 | 1.000 | 0.993 | 9/9 |

A única substituição a mais no conjunto é um doutrinador citado ("segundo leciona…"), aceitável
pelo critério.

### `Luciano/bertimbau-large-lener_br`

| | nomes | vazados | recall (nome inteiro) | precisão | manter preservados |
|---|---|---|---|---|---|
| limiar 0,05 a 0,3, sem variante de caixa | 137 | 0 | 1.000 | 0.993 | 9/9 |
| limiar 0,5 a 0,7, sem variante de caixa | 137 | 1 | 0.993 | 0.993 | 9/9 |
| limiar 0,9, sem variante de caixa | 137 | 4 | 0.971 | 0.993 | 9/9 |
| limiar 0,05 a 0,7, com variante de caixa | 137 | 0 | 1.000 | 0.993 | 9/9 |
| limiar 0,9, com variante de caixa | 137 | 3 | 0.978 | 0.993 | 9/9 |

Tempo médio por ementa: 253 ms sem a variante de caixa, 490 ms com ela.

### `pierreguillou/ner-bert-base-cased-pt-lenerbr`

| | nomes | vazados | recall (nome inteiro) | precisão | manter preservados |
|---|---|---|---|---|---|
| limiar 0,05 a 0,9, sem variante de caixa | 137 | 1 | 0.993 | 0.993 | 9/9 |
| limiar 0,05 a 0,9, com variante de caixa | 137 | 0 | 1.000 | 0.993 | 9/9 |

Tempo médio por ementa: 88 ms sem a variante de caixa, 138 ms com ela.

## Limites desta avaliação

- O conjunto sintético é pequeno e escrito por nós: mede se o modelo e as regras cobrem os
  casos conhecidos, não a taxa de vazamento real. Essa vem da revisão por amostra (critério:
  0 vazamentos em 100 ementas, ARCHITECTURE.md, seção 6.7).
- O modelo é *cased*: a variante de caixa compensa nomes em maiúsculas, mas grafias muito fora do
  padrão (nomes em minúsculas, nomes partidos) podem escapar. Cada vazamento achado na revisão
  vira caso sintético novo nas fixtures, e a correção é conferida por `buscajus revisao verificar`.
