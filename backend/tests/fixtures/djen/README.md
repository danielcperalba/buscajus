# Fixtures sintéticas do DJEN (F1-02)

**Nenhum dado real.** As ementas foram escritas do zero no formato das ementas de acórdão do TJPR. Todas as pessoas são nomes fictícios marcadores com sobrenomes inventados. Os processos usam o ano 2099 e a origem 9999, então não podem existir. Os CPFs são números de exemplo conhecidos. **Nunca versione um caderno real.**

Tudo é gerado por [`__init__.py`](__init__.py) a partir de [`dados.py`](dados.py). Para regerar, a partir de `backend/tests`:

```bash
uv run python -m fixtures.djen
```

O teste `tests/test_fixtures_djen.py` confere que os arquivos versionados batem com o gerador e que cobrem os casos abaixo.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `caderno-2026-10-15-v1.zip` | 26 comunicações em 3 arquivos `TJPR-D-2026-10-15_{n}.json` (`{"count", "items"}`, JSON com `ensure_ascii`, como no real): 20 ementas de acórdão e 6 de outros tipos |
| `caderno-2026-10-15-v2.zip` | Versão 2 do mesmo dia: sem a ementa 900020 e com a 900005 cancelada |
| `caderno-2026-10-17-v1.zip` | Caderno sem nenhuma ementa de acórdão (resultado válido, não é erro) |
| `metadados-{data}-v{n}.json` | Resposta de `GET /api/v1/caderno/TJPR/{data}/D` com o `hash` correto |
| `metadados-2026-10-15-v1-hash-incorreto.json` | Mesmos metadados com `hash` que não confere |
| `metadados-2026-10-15-nao-processado.json` | `status` "Em processamento" (caderno ainda não pronto) |
| `comunicacao-900020-cancelada.json` | `GET /api/v1/comunicacao` (checagem pontual) da ementa que sumiu no v2: cancelada |
| `comunicacao-900001-ativa.json` | Checagem pontual de uma ementa ativa |
| `comunicacao-nao-encontrada.json` | Checagem pontual sem resultado |
| `erro-429.json` | Corpo de uma resposta 429 (os testes acrescentam ou não `Retry-After`) |

O dia sem caderno não tem arquivo: a API responde 404.

## Casos cobertos nas ementas

- Destinatário PF citado no texto: em caixa alta, sem acento (`JOAO` × `JOÃO`), em caixa mista, só com primeiro e último nome, em minúsculas, com entidades HTML (todo o texto vem codificado, como no DJEN), com entidades numéricas (900012) e com entidades escapadas duas vezes (`&amp;Atilde;`, 900009).
- Advogado PF citado no texto (900018).
- Casos difíceis de F1-34: MEI com `ME` (900006) e com CPF colado ao nome (900007), razão social com nome de pessoa (900008), massa falida (900009), condomínio (900010), espólio (900004), entes públicos (900011, 900012, Ministério Público), banco, seguradora e cooperativa.
- CPF formatado (900007) e sem formatação (900016), além de números de 11 dígitos que **não** podem ser mascarados (900016): dentro de um número de processo sem máscara, dentro de um CNPJ sem máscara e com dígito verificador inválido.
- Pessoas que não são destinatárias (vítimas e testemunhas, 900001, 900002, 900020), que só a camada 2 (NER) pega.
- Nomes que devem ficar: relator no cabeçalho, ministro e desembargador citados em precedentes, `Lei Maria da Penha`.
- Variações do cabeçalho: `Relator(a)`, `Relatora`, `Relator`, `Data de Julgamento`, sem data de julgamento (900014), ementa sem tabela (900013).
- PII residual para a quarentena (F1-24): rótulo `Apelante:`, e-mail e telefone (900019).
- Item cancelado no próprio caderno (900015: `ativo = false`, `status = "C"`, `data_cancelamento`).

As comunicações que não são ementa usam nomes com o prefixo `DESCART` (em maiúsculas), no texto e nos destinatários, e não podem aparecer em nenhuma tabela, arquivo bruto ou log.

## Suposições a confirmar no F1-01

O formato segue o que já foi observado nos cadernos reais (seção 3.2 do ARCHITECTURE.md). Estes detalhes ainda são suposições e serão conferidos quando o script do F1-01 rodar: os valores de `status` de uma comunicação ativa e de uma cancelada (`"P"` e `"C"` aqui), o tipo de `codigoClasse` e `idOrgao`, os campos extras dos metadados e o HTML exato das células (`<strong>`, `&nbsp;`, ementa na própria célula `colspan=2` depois de `<br>`).
