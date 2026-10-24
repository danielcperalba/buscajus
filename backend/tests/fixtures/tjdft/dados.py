"""Dados sintéticos das respostas da API de jurisprudência do TJDFT (F2-02).

Nenhum dado real. A estrutura (campos, tipos, formatos, chaves de ``agregacoes`` e
``paginacao``) segue o levantamento de ``backend/scripts/spike_api_tjdft.py``, feito só com
agregados; o conteúdo foi escrito do zero. Todas as pessoas são **nomes fictícios
marcadores**, com sobrenomes inventados, para que os testes possam procurá-los em qualquer
tabela, arquivo ou log sem falso positivo. Os processos usam o ano 2099 e a origem 9999 (com
dígito verificador válido); os uuids têm o prefixo fixo ``0f1c7e00-2099``; os CPFs são números
de exemplo conhecidos.

Os conjuntos no fim do módulo dizem o que cada teste espera.
"""

from dataclasses import dataclass, field
from typing import Any

TRIBUNAL = "TJDFT"
# 45 registros: página cheia (40), última parcial (5) e a página vazia depois do fim.
DIA = "2026-10-14"
# 3 registros, um deles publicado antes das 3h UTC (ainda 14/10 em São Paulo).
DIA_VIRADA = "2026-10-15"
# 41 registros; numa das respostas, a página 1 repete um registro da página 0.
DIA_REPETIDO = "2026-10-16"
# Nenhum registro.
DIA_VAZIO = "2026-10-18"

# Órgãos: grafia mista com ordinal ("3ª Turma Cível") e maiúsculas nas turmas recursais,
# como na API.
ORGAOS = {
    "1ª Turma Cível": 101,
    "3ª Turma Cível": 103,
    "6ª Turma Cível": 106,
    "2ª Turma Criminal": 202,
    "1ª Câmara Criminal": 301,
    "PRIMEIRA TURMA RECURSAL": 401,
    "SEGUNDA TURMA RECURSAL": 402,
}

# Magistrados (fictícios): em maiúsculas e sem título, como em nomeRelator.
REL_CIVEL = "ARISTÓBULO VENTANILHA QUARESMEIRO"
REL_CIVEL_2 = "DEOCLECIANA MORGADÃO TRAVESSEIRO"
REL_CRIMINAL = "HERMENEGILDO SOUTELO VILARONGO"
REL_RECURSAL = "OTACÍLIO VENTANILHA BRUSQUETO"
DESIGNADO = "LEOPOLDINA ARRUDÃO CAMBRAIETA"
REVISOR = "SEBASTIÃO REBOLEDO ALMENARIM"
# Citado num precedente, depois de "Rel. Des.": fica no texto.
DES_PRECEDENTE = "CLEOMENES PARAGUAÇU TORRENTINO"

# Classes da TPU usadas (todas existem em tpu_classes.json).
APELACAO_CIVEL = 198
AGRAVO_INSTRUMENTO = 202
APELACAO_CRIMINAL = 417
RECURSO_INOMINADO = 460
EMBARGOS_DECLARACAO = 1689
HABEAS_CORPUS = 307
AGRAVO_INTERNO = 1208

MEIA_NOITE_SP = "T03:00:00.000Z"

# Pessoas citadas no texto (vítima, réu) que só o NER (camada 2) pega.
VITIMA = "TEODOMIRA CASTELHANOS PIRILAMPO"
REU = "Gumercindo Palharetti Sarmentoso"
# Marcadores que nunca podem aparecer em tabela, arquivo bruto ou log.
MARCADOR_SEGREDO = "SIGILARIO"
MARCADOR_INTEIRO_TEOR = "MARCADORINTEIROTEOR"


@dataclass(frozen=True)
class Registro:
    n: int  # compõe uuid, identificador, sequencial e número do processo
    classe: int
    orgao: str
    relator: str
    julgamento: str  # ISO 8601 em UTC, como na API
    publicacao: str
    local: str  # "DJE" | "PJe"
    ementa: str
    decisao: str
    segredo: bool = False
    designado: str | None = None
    revisor: str | None = None
    # Campos fora da lista branca além dos que todo registro traz.
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def turma_recursal(self) -> bool:
        return "RECURSAL" in self.orgao


EMENTA_PLANO_SAUDE = (
    "DIREITO DO CONSUMIDOR. APELAÇÃO CÍVEL. PLANO DE SAÚDE. NEGATIVA DE COBERTURA DE "
    "TRATAMENTO PRESCRITO. ROL DA ANS. CARÁTER EXEMPLIFICATIVO MITIGADO. DANO MORAL "
    "CONFIGURADO. RECURSO DESPROVIDO.\n"
    "I. CASO EM EXAME\n"
    "1. Apelação contra sentença que condenou a operadora a custear tratamento prescrito pelo "
    "médico assistente e a indenizar danos morais.\n"
    "II. QUESTÃO EM DISCUSSÃO\n"
    "2. A questão em discussão consiste em saber se a recusa de cobertura, fundada na ausência "
    "do procedimento no rol da ANS, é legítima.\n"
    "III. RAZÕES DE DECIDIR\n"
    "3. Comprovada a eficácia do tratamento e a inexistência de substituto terapêutico no rol, "
    "a recusa é abusiva (Lei 9.656/1998, art. 10, § 13).\n"
    "4. A negativa indevida de cobertura em situação de urgência ultrapassa o mero "
    "aborrecimento e gera dano moral.\n"
    "IV. DISPOSITIVO\n"
    "5. Recurso conhecido e desprovido."
)

EMENTA_TURMA_RECURSAL = (
    "JUIZADO ESPECIAL CÍVEL. DIREITO DO CONSUMIDOR. TRANSPORTE AÉREO. CANCELAMENTO DE VOO. "
    "ASSISTÊNCIA MATERIAL NÃO PRESTADA. DANO MORAL. QUANTUM ADEQUADO. RECURSO CONHECIDO E NÃO "
    "PROVIDO. 1. A companhia aérea responde objetivamente pelo cancelamento de voo sem a "
    "assistência material prevista na Resolução 400/2016 da ANAC. 2. O valor fixado na origem "
    "atende à razoabilidade e à proporcionalidade. 3. Sentença mantida por seus próprios "
    "fundamentos (Lei 9.099/1995, art. 46). Condenado o recorrente vencido ao pagamento das "
    "custas e dos honorários advocatícios, fixados em 10% do valor da condenação."
)

# Registro em segredo: os marcadores não podem aparecer em lugar nenhum.
EMENTA_SEGREDO = (
    f"DIREITO DE FAMÍLIA. APELAÇÃO CÍVEL. GUARDA E ALIMENTOS. {MARCADOR_SEGREDO} "
    f"ZULMIRA {MARCADOR_SEGREDO} DOURADINHO. MELHOR INTERESSE DA CRIANÇA. 1. A fixação da "
    "guarda observa o melhor interesse da criança. 2. Recurso conhecido e desprovido."
)

# Apelação criminal: vítima e réu citados (camada 2), CPF formatado e sem formatação,
# números de 11 dígitos que não são CPF, precedente com relator e epônimo que devem ficar.
EMENTA_CRIMINAL = (
    "PENAL E PROCESSO PENAL. APELAÇÃO CRIMINAL. VIOLÊNCIA DOMÉSTICA. LEI MARIA DA PENHA. "
    "LESÃO CORPORAL. PALAVRA DA VÍTIMA. CONDENAÇÃO MANTIDA.\n"
    f"1. Nos crimes praticados no âmbito doméstico, a palavra da vítima {VITIMA}, inscrita no "
    "CPF 529.982.247-25, tem especial relevância quando corroborada pelos demais elementos "
    "de prova.\n"
    f"2. O réu {REU} (CPF 11144477735) não apresentou versão verossímil. Nos autos "
    "52998224725209981699 consta o laudo; a empresa de CNPJ 11144477735000 apenas forneceu "
    "imagens, e o número 12345678900 citado pela defesa não corresponde a documento válido.\n"
    f"3. Precedente: Acórdão 9999999, 2ª Turma Criminal, Rel. Des. {DES_PRECEDENTE}, "
    "j. 01/02/2099.\n"
    "4. Recurso conhecido e desprovido."
)

EMENTA_PII = (
    "DIREITO CIVIL. AGRAVO DE INSTRUMENTO. CUMPRIMENTO DE SENTENÇA. PENHORA DE SALÁRIO. "
    "1. A impenhorabilidade do salário admite mitigação para satisfação de dívida não "
    "alimentar quando preservado o mínimo existencial. 2. Intimações pelo endereço "
    "contato.ficticio@exemplo.invalid. 3. Recurso conhecido e parcialmente provido."
)

EMENTA_EMBARGOS = (
    "PROCESSO CIVIL. EMBARGOS DE DECLARAÇÃO. OMISSÃO, CONTRADIÇÃO OU OBSCURIDADE. AUSÊNCIA. "
    "REDISCUSSÃO DA MATÉRIA. IMPOSSIBILIDADE. 1. Os embargos de declaração não se prestam à "
    "rediscussão do mérito. 2. Embargos conhecidos e rejeitados."
)

EMENTA_HABEAS_CORPUS = (
    "PROCESSO PENAL. HABEAS CORPUS. PRISÃO PREVENTIVA. GARANTIA DA ORDEM PÚBLICA. "
    "FUNDAMENTAÇÃO IDÔNEA. 1. A gravidade concreta da conduta justifica a custódia cautelar. "
    "2. Ordem conhecida e denegada."
)

EMENTA_DESIGNADO = (
    "DIREITO CIVIL. APELAÇÃO CÍVEL. RESPONSABILIDADE CIVIL. ACIDENTE DE TRÂNSITO. CULPA "
    "CONCORRENTE. REDUÇÃO PROPORCIONAL DA INDENIZAÇÃO. 1. Demonstrada a contribuição das duas "
    "partes para o evento, a indenização é reduzida na proporção das culpas (CC, art. 945). "
    "2. Recurso conhecido e parcialmente provido. Maioria."
)

# Temas dos registros de preenchimento: (classe, órgão, relator, cabeçalho, razão de decidir).
TEMAS = (
    (
        APELACAO_CIVEL,
        "1ª Turma Cível",
        REL_CIVEL,
        "DIREITO CIVIL. APELAÇÃO CÍVEL. CONTRATO DE LOCAÇÃO. DESPEJO POR FALTA DE PAGAMENTO.",
        "A falta de pagamento dos aluguéis autoriza a rescisão do contrato e o despejo.",
    ),
    (
        APELACAO_CIVEL,
        "6ª Turma Cível",
        REL_CIVEL_2,
        "DIREITO DO CONSUMIDOR. APELAÇÃO CÍVEL. CONTRATO BANCÁRIO. JUROS REMUNERATÓRIOS.",
        "A taxa de juros só é abusiva quando discrepa substancialmente da média de mercado.",
    ),
    (
        AGRAVO_INSTRUMENTO,
        "3ª Turma Cível",
        REL_CIVEL,
        "PROCESSO CIVIL. AGRAVO DE INSTRUMENTO. TUTELA DE URGÊNCIA. REQUISITOS.",
        "Ausente a probabilidade do direito, a tutela de urgência deve ser indeferida.",
    ),
    (
        AGRAVO_INTERNO,
        "6ª Turma Cível",
        REL_CIVEL_2,
        "PROCESSO CIVIL. AGRAVO INTERNO. DECISÃO MONOCRÁTICA. FUNDAMENTOS NÃO INFIRMADOS.",
        "O agravo interno que não infirma os fundamentos da decisão agravada não prospera.",
    ),
    (
        APELACAO_CRIMINAL,
        "2ª Turma Criminal",
        REL_CRIMINAL,
        "PENAL. APELAÇÃO CRIMINAL. FURTO QUALIFICADO. DOSIMETRIA. PENA-BASE.",
        "A valoração negativa de circunstância judicial exige fundamentação concreta.",
    ),
    (
        RECURSO_INOMINADO,
        "SEGUNDA TURMA RECURSAL",
        REL_RECURSAL,
        "JUIZADO ESPECIAL CÍVEL. RECURSO INOMINADO. TELEFONIA. COBRANÇA INDEVIDA.",
        "A cobrança por serviço não contratado gera o dever de restituir os valores pagos.",
    ),
    (
        EMBARGOS_DECLARACAO,
        "3ª Turma Cível",
        REL_CIVEL,
        "PROCESSO CIVIL. EMBARGOS DE DECLARAÇÃO. PREQUESTIONAMENTO.",
        "O prequestionamento não dispensa a demonstração de vício no julgado.",
    ),
)
DECISOES = (
    "CONHECIDO. DESPROVIDO. UNÂNIME.",
    "RECURSO CONHECIDO E PROVIDO. UNÂNIME.",
    "CONHECIDO. PARCIALMENTE PROVIDO. UNÂNIME.",
)


def _preenchimento(n: int, dia: str) -> Registro:
    classe, orgao, relator, cabecalho, razao = TEMAS[n % len(TEMAS)]
    ementa = (
        f"{cabecalho} 1. {razao} 2. Valor discutido de R$ {n}.250,00, conforme a planilha dos "
        "autos. 3. Recurso conhecido e desprovido."
    )
    return Registro(
        n=n,
        classe=classe,
        orgao=orgao,
        relator=relator,
        julgamento=f"2026-10-0{n % 9 + 1}{MEIA_NOITE_SP}",
        publicacao=f"{dia}{MEIA_NOITE_SP}",
        local="PJe" if n % 4 == 0 else "DJE",
        ementa=ementa,
        decisao=DECISOES[n % len(DECISOES)],
    )


REGISTROS_DIA: tuple[Registro, ...] = (
    Registro(
        n=1,
        classe=APELACAO_CIVEL,
        orgao="3ª Turma Cível",
        relator=REL_CIVEL,
        julgamento="2026-10-08T03:00:00.000Z",
        publicacao=f"{DIA}T20:34:07.000Z",
        local="PJe",
        ementa=EMENTA_PLANO_SAUDE,
        decisao="CONHECIDO. DESPROVIDO. UNÂNIME.",
    ),
    Registro(
        n=2,
        classe=RECURSO_INOMINADO,
        orgao="PRIMEIRA TURMA RECURSAL",
        relator=REL_RECURSAL,
        julgamento="2026-10-06T03:00:00.000Z",
        publicacao=f"{DIA}{MEIA_NOITE_SP}",
        local="PJe",
        ementa=EMENTA_TURMA_RECURSAL,
        decisao="RECURSO CONHECIDO E NÃO PROVIDO. UNÂNIME.",
    ),
    Registro(
        n=3,
        classe=APELACAO_CIVEL,
        orgao="1ª Turma Cível",
        relator=REL_CIVEL,
        julgamento="2026-10-07T03:00:00.000Z",
        publicacao=f"{DIA}{MEIA_NOITE_SP}",
        local="DJE",
        ementa=EMENTA_SEGREDO,
        decisao=f"CONHECIDO. DESPROVIDO. {MARCADOR_SEGREDO}.",
        segredo=True,
    ),
    Registro(
        # Publicado às 22h30 de 13/10 em São Paulo; julgado às 23h de 07/10 em São Paulo.
        n=4,
        classe=AGRAVO_INSTRUMENTO,
        orgao="6ª Turma Cível",
        relator=REL_CIVEL_2,
        julgamento="2026-10-08T02:00:00.000Z",
        publicacao=f"{DIA}T01:30:00.000Z",
        local="DJE",
        ementa=EMENTA_EMBARGOS.replace("EMBARGOS DE DECLARAÇÃO", "AGRAVO DE INSTRUMENTO", 1),
        decisao="CONHECIDO. DESPROVIDO. UNÂNIME.",
    ),
    Registro(
        n=5,
        classe=APELACAO_CRIMINAL,
        orgao="1ª Câmara Criminal",
        relator=REL_CRIMINAL,
        julgamento="2026-10-02T03:00:00.000Z",
        publicacao=f"{DIA}{MEIA_NOITE_SP}",
        local="DJE",
        ementa=EMENTA_CRIMINAL,
        decisao=f"CONHECIDO. DESPROVIDO. MAIORIA. REDIGIRÁ O ACÓRDÃO A DESA. {DESIGNADO}.",
        designado=DESIGNADO,
        revisor=REVISOR,
    ),
    Registro(
        # Campos que a API pode trazer e que nunca chegam ao disco.
        n=6,
        classe=APELACAO_CIVEL,
        orgao="3ª Turma Cível",
        relator=REL_CIVEL,
        julgamento="2026-10-01T03:00:00.000Z",
        publicacao=f"{DIA}{MEIA_NOITE_SP}",
        local="PJe",
        ementa=EMENTA_DESIGNADO,
        decisao="CONHECIDO. PARCIALMENTE PROVIDO. MAIORIA.",
        designado=DESIGNADO,
        extras={
            "inteiroTeorHtml": f"<p>{MARCADOR_INTEIRO_TEOR} relatório e voto</p>",
            "jurisprudenciaEmFoco": [{"titulo": MARCADOR_INTEIRO_TEOR}],
        },
    ),
    Registro(
        n=7,
        classe=AGRAVO_INSTRUMENTO,
        orgao="1ª Turma Cível",
        relator=REL_CIVEL,
        julgamento="2026-10-05T03:00:00.000Z",
        publicacao=f"{DIA}{MEIA_NOITE_SP}",
        local="DJE",
        ementa=EMENTA_PII,
        decisao="CONHECIDO. PARCIALMENTE PROVIDO. UNÂNIME.",
    ),
    Registro(
        n=8,
        classe=EMBARGOS_DECLARACAO,
        orgao="6ª Turma Cível",
        relator=REL_CIVEL_2,
        julgamento="2026-10-09T03:00:00.000Z",
        publicacao=f"{DIA}{MEIA_NOITE_SP}",
        local="PJe",
        ementa=EMENTA_EMBARGOS,
        decisao="EMBARGOS CONHECIDOS E REJEITADOS. UNÂNIME.",
    ),
    Registro(
        n=9,
        classe=HABEAS_CORPUS,
        orgao="2ª Turma Criminal",
        relator=REL_CRIMINAL,
        julgamento="2026-10-09T03:00:00.000Z",
        publicacao=f"{DIA}{MEIA_NOITE_SP}",
        local="DJE",
        ementa=EMENTA_HABEAS_CORPUS,
        decisao="ORDEM CONHECIDA E DENEGADA. UNÂNIME.",
    ),
    *(_preenchimento(n, DIA) for n in range(10, 46)),
)

REGISTROS_VIRADA: tuple[Registro, ...] = (
    # Publicado às 22h10 de 14/10 em São Paulo: vem na consulta de 15/10 (data UTC).
    Registro(
        n=46,
        classe=APELACAO_CIVEL,
        orgao="1ª Turma Cível",
        relator=REL_CIVEL,
        julgamento="2026-10-09T03:00:00.000Z",
        publicacao=f"{DIA_VIRADA}T01:10:00.000Z",
        local="DJE",
        ementa=_preenchimento(46, DIA_VIRADA).ementa,
        decisao="CONHECIDO. DESPROVIDO. UNÂNIME.",
    ),
    _preenchimento(47, DIA_VIRADA),
    Registro(
        n=48,
        classe=RECURSO_INOMINADO,
        orgao="SEGUNDA TURMA RECURSAL",
        relator=REL_RECURSAL,
        julgamento="2026-10-13T03:00:00.000Z",
        publicacao=f"{DIA_VIRADA}T18:20:00.000Z",
        local="PJe",
        ementa=EMENTA_TURMA_RECURSAL.replace("CANCELAMENTO DE VOO", "ATRASO DE VOO", 1),
        decisao="RECURSO CONHECIDO E NÃO PROVIDO. UNÂNIME.",
    ),
)

REGISTROS_REPETIDO: tuple[Registro, ...] = tuple(
    _preenchimento(n, DIA_REPETIDO) for n in range(49, 90)
)
# Na resposta defeituosa, a página 1 traz de novo este registro da página 0.
REPETIDO = 60

# --- Expectativas dos testes ----------------------------------------------------------

# Nomes e números que a anonimização (camada 2 + CPF) deve tirar do texto gravado.
DEVEM_SUMIR = (VITIMA, REU)
CPFS = ("529.982.247-25", "11144477735")
# Números de 11 dígitos que NÃO são CPF a mascarar (colados a outros dígitos ou DV inválido).
NAO_CPFS = ("52998224725209981699", "11144477735000", "12345678900")
# Devem ficar: magistrados (relator, designado, revisor, precedente) e o epônimo.
PRESERVADOS = ("LEI MARIA DA PENHA", f"Rel. Des. {DES_PRECEDENTE}", DESIGNADO)
# Nunca podem aparecer em tabela, arquivo bruto ou log.
NUNCA = (MARCADOR_SEGREDO, MARCADOR_INTEIRO_TEOR)
