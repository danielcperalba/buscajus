# Fixtures sintéticas da API do TJDFT (F2-02)

**Nenhum dado real.** A estrutura das respostas (campos, tipos, formatos, ordem dos campos, chaves de `agregacoes` e `paginacao`) segue o levantamento feito com [`backend/scripts/spike_api_tjdft.py`](../../../scripts/spike_api_tjdft.py), que imprime só agregados. O conteúdo foi escrito do zero: todas as pessoas são nomes fictícios marcadores com sobrenomes inventados, os processos usam o ano 2099 e a origem 9999 (`NNNNNNN-DD.2099.8.07.9999`, com dígito verificador válido), os uuids têm o prefixo `0f1c7e00-2099` e os CPFs são números de exemplo conhecidos. **Nunca versione uma resposta real.**

Tudo é gerado por [`__init__.py`](__init__.py) a partir de [`dados.py`](dados.py). Para regerar, a partir de `backend/tests`:

```bash
uv run python -m fixtures.tjdft
```

O teste `tests/test_fixtures_tjdft.py` confere que os arquivos versionados batem com o gerador e que cobrem os casos abaixo.

## Arquivos

Cada arquivo é uma resposta de `POST https://jurisdf.tjdft.jus.br/api/v1/pesquisa` com `base = acordaos`, a `dataPublicacao` do nome e `tamanho = 40`.

| Arquivo | Conteúdo |
|---|---|
| `pesquisa-2026-10-14-p0.json` | Página cheia (40 de 45 registros) |
| `pesquisa-2026-10-14-p1.json` | Última página, parcial (5 registros) |
| `pesquisa-2026-10-14-p2.json` | Página depois do fim: `registros` vazio, `hits.value` ainda 45 |
| `pesquisa-2026-10-15-p0.json` | 3 registros, um publicado às 01:10 UTC (22:10 de 14/10 em São Paulo) |
| `pesquisa-2026-10-16-p0.json` | Página cheia (40 de 41) |
| `pesquisa-2026-10-16-p1.json` | Última página correta (1 registro novo) |
| `pesquisa-2026-10-16-p1-repetida.json` | Última página defeituosa: repete um registro da página 0 (uuids únicos ≠ `hits.value`) |
| `pesquisa-2026-10-18-p0.json` | Dia sem registros (`hits.value = 0`) |

## Casos cobertos (dia 2026-10-14)

- **Turma recursal** (registro 2): `base = "acordaos"`, `subbase = "acordaos-tr"`, `turmaRecursal = true`, órgão em maiúsculas (`PRIMEIRA TURMA RECURSAL`), Recurso Inominado Cível (460). Há outras turmas recursais entre os registros de preenchimento.
- **Segredo de justiça** (registro 3): `segredoJustica = true` e `possuiInteiroTeor = false`, com a ementa completa, como na API. O texto usa o marcador `SIGILARIO`, que não pode aparecer em nenhuma tabela, arquivo bruto ou log.
- **Virada do dia** (registro 4): `dataPublicacao = 2026-10-14T01:30:00.000Z` (13/10 em São Paulo) e `dataJulgamento = 2026-10-08T02:00:00.000Z` (07/10 em São Paulo). Os demais seguem o padrão real: `T03:00:00.000Z` (meia-noite em São Paulo); o registro 1 tem `T20:34:07.000Z`.
- **Relator designado e revisor** (registro 5): `nomeRelatorDesignado` e `nomeRevisor`, que só aparecem em alguns registros; o registro 6 tem só o designado.
- **Anonimização** (registro 5, Apelação Criminal): vítima e réu fictícios citados no texto (só o NER pega), CPF formatado e sem formatação, números de 11 dígitos que **não** são CPF (dentro de número de processo e de CNPJ sem máscara, DV inválido), precedente com `Rel. Des.` e o epônimo `LEI MARIA DA PENHA`, que devem ficar.
- **Campos fora da lista branca** (registro 6): além dos que todo registro traz (`sequencial`, `relatorAtivo`, `uf`, `codigoSistjOrgaoJulgador`, `marcadores`), `inteiroTeorHtml` e `jurisprudenciaEmFoco` com o marcador `MARCADORINTEIROTEOR`, que não pode chegar ao disco.
- **PII residual** (registro 7): e-mail na ementa (quarentena, F1-24).
- `localDePublicacao` `DJE` e `PJe`; `versao` como texto (`"01"`); `codigoClasseCnj` inteiro de classes que existem na TPU; `processo` já com máscara.

Variações que dependem de um registro já conhecido (segredo `null`, ausente, `1` ou `"S"`; `base` diferente; segredo superveniente numa recoleta; classe fora da TPU) são montadas nos testes a partir destes registros.
