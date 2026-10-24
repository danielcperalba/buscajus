"""Dados sintéticos do caderno do DJEN (F1-02).

Nenhum dado real. As ementas foram escritas do zero, no formato das ementas de acórdão do
TJPR, e todas as pessoas são **nomes fictícios marcadores**: sobrenomes inventados, para que
os testes possam procurar o nome em qualquer tabela, arquivo ou log sem falso positivo.
Números de processo usam o ano 2099 e a origem 9999 (com dígito verificador válido), então
não correspondem a processos reais. Os CPFs são números de exemplo conhecidos.

Os conjuntos no fim do módulo dizem o que cada teste espera: o que deve sumir do texto
gravado, o que deve ficar e o que nunca pode aparecer em lugar nenhum.
"""

from dataclasses import dataclass

DATA = "2026-10-15"
DATA_SEM_EMENTAS = "2026-10-17"
TRIBUNAL = "TJPR"


@dataclass(frozen=True)
class Pessoa:
    nome: str
    polo: str = "P"


@dataclass(frozen=True)
class Advogado:
    nome: str
    oab: str


@dataclass(frozen=True)
class Ementa:
    id: int
    sequencial: int  # compõe o número do processo
    orgao: str
    id_orgao: int
    classe: str
    codigo_classe: int
    relator: str
    data_julgamento: str | None
    corpo: tuple[str, ...]  # parágrafos, em texto puro (o gerador codifica as entidades)
    destinatarios: tuple[Pessoa, ...]
    advogados: tuple[Advogado, ...] = ()
    formato: str = "tabela"  # "tabela" | "sem_tabela"
    rotulo_relator: str = "Relator(a)"
    rotulo_data: str = "Data do Julgamento"
    cancelada: bool = False
    escape_duplo: bool = False  # entidades do corpo escapadas duas vezes (&amp;Atilde;)
    entidades_numericas: bool = False  # &#227; em vez de &atilde;
    # nomeClasse do JSON, quando difere da classe do cabeçalho (44% no TJPR, F1-01).
    nome_classe_fonte: str | None = None
    # link nulo (1.180 comunicações no F1-01).
    sem_link: bool = False


@dataclass(frozen=True)
class Outra:
    """Comunicação que não é ementa de acórdão: deve ser descartada sem deixar rastro."""

    id: int
    sequencial: int
    tipo_documento: str
    tipo_comunicacao: str
    orgao: str
    id_orgao: int
    classe: str
    codigo_classe: int
    texto: str
    destinatarios: tuple[Pessoa, ...]
    advogados: tuple[Advogado, ...] = ()


MP = Pessoa("MINISTÉRIO PÚBLICO DO ESTADO DO PARANÁ", "A")
ADV_DEFESA = Advogado("LEOCÁDIO BARRANCOS VIEIRA", "98765")
ADV_CIVEL = Advogado("PERPÉTUA GOUVEIA ALCANTARILHA", "87654")

EMENTAS: tuple[Ementa, ...] = (
    Ementa(
        id=900001,
        sequencial=1001,
        orgao="3ª Câmara Criminal",
        id_orgao=70003,
        classe="Apelação Criminal",
        codigo_classe=417,
        relator="Desembargador Aristeu Prudente Valença",
        data_julgamento="09/10/2026",
        corpo=(
            "EMENTA: DIREITO PENAL. APELAÇÃO CRIMINAL. ROUBO MAJORADO PELO CONCURSO DE "
            "AGENTES. RECONHECIMENTO PESSOAL. PROVA SUFICIENTE. RECURSO DESPROVIDO.",
            "I. CASO EM EXAME 1. Apelação interposta por ANACLETO BORGONOVI QUINTELA contra "
            "sentença que o condenou pela prática de roubo majorado.",
            "II. QUESTÃO EM DISCUSSÃO 2. A questão consiste em saber se o reconhecimento "
            "realizado pela vítima Clotilde Ravanello observou o art. 226 do CPP.",
            "III. RAZÕES DE DECIDIR 3. O reconhecimento foi corroborado por outras provas, "
            "conforme orientação do Superior Tribunal de Justiça (HC 712.345/SP, Rel. Min. "
            "Bonifácio Cardeal, Sexta Turma, j. 10/03/2025). 4. A palavra da vítima tem "
            "especial relevância nos crimes patrimoniais.",
            "IV. DISPOSITIVO 5. Recurso desprovido.",
        ),
        destinatarios=(MP, Pessoa("ANACLETO BORGONOVI QUINTELA")),
        advogados=(ADV_DEFESA,),
        nome_classe_fonte="Ação Penal - Procedimento Ordinário",
    ),
    Ementa(
        id=900002,
        sequencial=1002,
        orgao="1ª Câmara Criminal",
        id_orgao=70001,
        classe="Apelação Criminal",
        codigo_classe=417,
        relator="Desembargadora Celestina Moura Brandão",
        data_julgamento="08/10/2026",
        corpo=(
            "EMENTA: DIREITO PENAL. VIOLÊNCIA DOMÉSTICA. LESÃO CORPORAL. LEI MARIA DA PENHA. "
            "PALAVRA DA VÍTIMA. CONDENAÇÃO MANTIDA.",
            "1. O apelante JOAO PEDRO ESCARLATINO DE ANDRADE foi condenado por lesão corporal "
            "praticada contra a ex-companheira Florisbela Mantovanelli, no âmbito da Lei Maria "
            "da Penha.",
            "2. Nos crimes praticados no contexto de violência doméstica, a palavra da vítima "
            "tem especial relevo quando coerente com o laudo pericial.",
            "3. A defesa de João Escarlatino não demonstrou causa de exclusão da ilicitude.",
            "4. Recurso desprovido.",
        ),
        destinatarios=(MP, Pessoa("JOÃO PEDRO ESCARLATINO DE ANDRADE")),
        advogados=(ADV_DEFESA,),
        rotulo_relator="Relatora",
    ),
    Ementa(
        id=900003,
        sequencial=1003,
        orgao="12ª Câmara Cível",
        id_orgao=70112,
        classe="Agravo de Instrumento",
        codigo_classe=202,
        relator="Desembargador Teobaldo Siqueira Lins",
        data_julgamento="07/10/2026",
        corpo=(
            "EMENTA: DIREITO DE FAMÍLIA. AGRAVO DE INSTRUMENTO. ALIMENTOS PROVISÓRIOS. "
            "BINÔMIO NECESSIDADE-POSSIBILIDADE. REDUÇÃO INDEVIDA.",
            "1. Agravo interposto contra decisão que fixou alimentos provisórios em favor do "
            "filho menor representado por Maria das Dores Zanfirelli.",
            "2. A capacidade contributiva do alimentante não foi afastada pelos documentos "
            "juntados. 3. Recurso conhecido e desprovido.",
        ),
        destinatarios=(Pessoa("MARIA DAS DORES ZANFIRELLI", "A"), Pessoa("RODOLFO ARANTIM")),
        advogados=(ADV_CIVEL,),
    ),
    Ementa(
        id=900004,
        sequencial=1004,
        orgao="11ª Câmara Cível",
        id_orgao=70111,
        classe="Apelação Cível",
        codigo_classe=198,
        relator="Desembargador Teobaldo Siqueira Lins",
        data_julgamento="06/10/2026",
        corpo=(
            "EMENTA: DIREITO CIVIL. SUCESSÕES. INVENTÁRIO E PARTILHA. COLAÇÃO DE BENS. "
            "DOAÇÃO EM VIDA A HERDEIRO. ADIANTAMENTO DA LEGÍTIMA.",
            "1. Discute-se a partilha dos bens deixados por Hermenegilda Castanheira e a "
            "obrigação de colação do imóvel doado em vida ao herdeiro OSVALDINO PRATES.",
            "2. A doação de ascendente a descendente importa adiantamento da legítima (art. "
            "544 do Código Civil), devendo o bem ser trazido à colação. 3. Sentença mantida.",
        ),
        destinatarios=(
            Pessoa("ESPÓLIO DE HERMENEGILDA CASTANHEIRA", "A"),
            Pessoa("OSVALDINO CASTANHEIRA PRATES"),
        ),
        advogados=(ADV_CIVEL,),
    ),
    Ementa(
        id=900005,
        sequencial=1005,
        orgao="3ª Turma Recursal dos Juizados Especiais",
        id_orgao=70203,
        classe="Recurso Inominado Cível",
        codigo_classe=460,
        relator="Juiz Evandro Pimentel Assunção",
        data_julgamento="05/10/2026",
        corpo=(
            "EMENTA: RECURSO INOMINADO. DIREITO DO CONSUMIDOR. DESCONTOS INDEVIDOS EM "
            "BENEFÍCIO PREVIDENCIÁRIO. EMPRÉSTIMO NÃO CONTRATADO. DANO MORAL CONFIGURADO.",
            "1. O BANCO FICTÍCIO DO SUL S.A. não comprovou a contratação do empréstimo "
            "consignado. 2. Restituição em dobro dos valores descontados. 3. Indenização por "
            "danos morais mantida. Recurso desprovido.",
        ),
        destinatarios=(
            Pessoa("BANCO FICTÍCIO DO SUL S.A."),
            Pessoa("TEREZINHA APARECIDA MOSCARDINI", "A"),
        ),
        advogados=(ADV_CIVEL,),
        nome_classe_fonte="Procedimento do Juizado Especial Cível",
    ),
    Ementa(
        id=900006,
        sequencial=1006,
        orgao="4ª Turma Recursal dos Juizados Especiais",
        id_orgao=70204,
        classe="Recurso Inominado Cível",
        codigo_classe=460,
        relator="Juíza Leonor Bittencourt Faria",
        data_julgamento="05/10/2026",
        corpo=(
            "EMENTA: RECURSO INOMINADO. PRESTAÇÃO DE SERVIÇOS. MICROEMPREENDEDOR INDIVIDUAL. "
            "VÍCIO NA INSTALAÇÃO DE ESQUADRIAS. RESCISÃO CONTRATUAL.",
            "1. Os serviços prestados por ROSALVO TEIXEIRINHA MENDONÇA apresentaram vícios "
            "comprovados por laudo. 2. Devolução do valor pago. Recurso parcialmente provido.",
        ),
        destinatarios=(
            Pessoa("ROSALVO TEIXEIRINHA MENDONÇA ME"),
            Pessoa("QUITÉRIA SALDANHA BORBOREMA", "A"),
        ),
        rotulo_relator="Relator",
    ),
    Ementa(
        id=900007,
        sequencial=1007,
        orgao="9ª Câmara Cível",
        id_orgao=70109,
        classe="Apelação Cível",
        codigo_classe=198,
        relator="Desembargadora Celestina Moura Brandão",
        data_julgamento="02/10/2026",
        corpo=(
            "EMENTA: APELAÇÃO CÍVEL. EXECUÇÃO DE TÍTULO EXTRAJUDICIAL. EMPRESÁRIO INDIVIDUAL. "
            "PENHORA DE BENS PESSOAIS. POSSIBILIDADE.",
            "1. O empresário individual Gumercindo Palharini, inscrito no CPF sob o nº "
            "529.982.247-25, responde com seu patrimônio pessoal pelas obrigações da "
            "atividade. 2. Não há separação patrimonial entre a pessoa natural e a firma "
            "individual. 3. Recurso desprovido.",
        ),
        destinatarios=(
            Pessoa("GUMERCINDO PALHARINI 52998224725"),
            Pessoa("COOPERATIVA DE CRÉDITO FICTÍCIA DO VALE", "A"),
        ),
        advogados=(ADV_CIVEL,),
    ),
    Ementa(
        id=900008,
        sequencial=1008,
        orgao="17ª Câmara Cível",
        id_orgao=70117,
        classe="Apelação Cível",
        codigo_classe=198,
        relator="Desembargador Aristeu Prudente Valença",
        data_julgamento="01/10/2026",
        corpo=(
            "EMENTA: APELAÇÃO CÍVEL. COMPRA E VENDA DE MÓVEIS PLANEJADOS. ATRASO NA ENTREGA. "
            "MULTA CONTRATUAL. CABIMENTO.",
            "1. A TIBÚRCIO VALADARES COMÉRCIO DE MÓVEIS LTDA descumpriu o prazo de entrega "
            "ajustado com a consumidora ADALGISA FONTOURA REBELO. 2. Multa contratual devida. "
            "Recurso desprovido.",
        ),
        destinatarios=(
            Pessoa("TIBÚRCIO VALADARES COMÉRCIO DE MÓVEIS LTDA"),
            Pessoa("ADALGISA FONTOURA REBELO", "A"),
        ),
        advogados=(ADV_CIVEL,),
    ),
    Ementa(
        id=900009,
        sequencial=1009,
        orgao="18ª Câmara Cível",
        id_orgao=70118,
        classe="Agravo de Instrumento",
        codigo_classe=202,
        relator="Desembargador Teobaldo Siqueira Lins",
        data_julgamento="30/09/2026",
        corpo=(
            "EMENTA: AGRAVO DE INSTRUMENTO. FALÊNCIA. HABILITAÇÃO DE CRÉDITO TRABALHISTA. "
            "CLASSIFICAÇÃO. LIMITE DE 150 SALÁRIOS MÍNIMOS.",
            "1. Crédito de IRACEMA GUSMÃO TREVISANUTO habilitado na falência da MASSA FALIDA "
            "DE CONSTRUTORA HORIZONTE IMAGINÁRIO LTDA. 2. Observância do limite do art. 83, "
            "I, da Lei 11.101/2005. 3. Recurso parcialmente provido.",
        ),
        destinatarios=(
            Pessoa("MASSA FALIDA DE CONSTRUTORA HORIZONTE IMAGINÁRIO LTDA"),
            Pessoa("IRACEMA GUSMÃO TREVISANUTO", "A"),
        ),
        escape_duplo=True,
    ),
    Ementa(
        id=900010,
        sequencial=1010,
        orgao="10ª Câmara Cível",
        id_orgao=70110,
        classe="Apelação Cível",
        codigo_classe=198,
        relator="Desembargadora Celestina Moura Brandão",
        data_julgamento="29/09/2026",
        corpo=(
            "EMENTA: APELAÇÃO CÍVEL. CONDOMÍNIO EDILÍCIO. COBRANÇA DE TAXAS CONDOMINIAIS. "
            "OBRIGAÇÃO PROPTER REM.",
            "1. O CONDOMÍNIO EDIFÍCIO SOLAR DAS ACÁCIAS FICTÍCIAS cobra cotas vencidas da "
            "unidade de Waldemar Cortezini Bragança. 2. A obrigação acompanha o imóvel. "
            "Recurso desprovido.",
        ),
        destinatarios=(
            Pessoa("CONDOMÍNIO EDIFÍCIO SOLAR DAS ACÁCIAS FICTÍCIAS", "A"),
            Pessoa("WALDEMAR CORTEZINI BRAGANÇA"),
        ),
        advogados=(ADV_CIVEL,),
    ),
    Ementa(
        id=900011,
        sequencial=1011,
        orgao="5ª Câmara Cível",
        id_orgao=70105,
        classe="Apelação / Remessa Necessária",
        codigo_classe=1728,
        relator="Desembargador Aristeu Prudente Valença",
        data_julgamento="28/09/2026",
        corpo=(
            "EMENTA: DIREITO À SAÚDE. FORNECIMENTO DE MEDICAMENTO. RESPONSABILIDADE "
            "SOLIDÁRIA DOS ENTES FEDERATIVOS.",
            "1. O ESTADO DO PARANÁ e o MUNICÍPIO DE VILA IMAGINÁRIA respondem solidariamente "
            "pelo fornecimento do fármaco a GENOVEVA LISBOA. 2. Tema 793 do STF. 3. Sentença "
            "mantida em remessa necessária.",
        ),
        destinatarios=(
            Pessoa("ESTADO DO PARANÁ"),
            Pessoa("MUNICÍPIO DE VILA IMAGINÁRIA"),
            Pessoa("GENOVEVA PIRAQUARA LISBOA", "A"),
        ),
    ),
    Ementa(
        id=900012,
        sequencial=1012,
        orgao="7ª Câmara Cível",
        id_orgao=70107,
        classe="Apelação Cível",
        codigo_classe=198,
        relator="Desembargador Teobaldo Siqueira Lins",
        data_julgamento="25/09/2026",
        corpo=(
            "EMENTA: APELAÇÃO CÍVEL. PREVIDENCIÁRIO. AUXÍLIO-ACIDENTE. REDUÇÃO DA CAPACIDADE "
            "LABORATIVA COMPROVADA.",
            "1. O INSTITUTO NACIONAL DO SEGURO SOCIAL - INSS não infirmou a conclusão do "
            "laudo pericial. 2. Benefício devido desde a cessação do auxílio por "
            "incapacidade temporária. Recurso desprovido.",
        ),
        destinatarios=(
            Pessoa("INSTITUTO NACIONAL DO SEGURO SOCIAL - INSS"),
            Pessoa("DORIVAL ESPIGÃO MARTINELLO", "A"),
        ),
        entidades_numericas=True,
        sem_link=True,
    ),
    Ementa(
        id=900013,
        sequencial=1013,
        orgao="2ª Câmara Criminal",
        id_orgao=70002,
        classe="Habeas Corpus Criminal",
        codigo_classe=307,
        relator="Desembargadora Celestina Moura Brandão",
        data_julgamento="09/10/2026",
        corpo=(
            "EMENTA: HABEAS CORPUS. TRÁFICO DE DROGAS. PRISÃO PREVENTIVA. GARANTIA DA ORDEM "
            "PÚBLICA. ORDEM DENEGADA.",
            "1. Paciente SEVERINO ARCANJO TOLENTINI preso com expressiva quantidade de "
            "entorpecentes. 2. Fundamentação idônea. 3. Ordem denegada.",
        ),
        destinatarios=(MP, Pessoa("SEVERINO ARCANJO TOLENTINI")),
        advogados=(ADV_DEFESA,),
        formato="sem_tabela",
    ),
    Ementa(
        id=900014,
        sequencial=1014,
        orgao="8ª Câmara Cível",
        id_orgao=70108,
        classe="Embargos de Declaração Cível",
        codigo_classe=1689,
        relator="Desembargador Aristeu Prudente Valença",
        data_julgamento=None,
        corpo=(
            "EMENTA: EMBARGOS DE DECLARAÇÃO. OMISSÃO INEXISTENTE. REDISCUSSÃO DA MATÉRIA. "
            "EMBARGOS REJEITADOS.",
            "1. Os embargos de declaração não se prestam à rediscussão do mérito. 2. Embargos "
            "opostos por Severino Tolentini rejeitados.",
        ),
        destinatarios=(
            Pessoa("SEVERINO ARCANJO TOLENTINI", "A"),
            Pessoa("BANCO FICTÍCIO DO SUL S.A."),
        ),
        advogados=(ADV_CIVEL,),
    ),
    Ementa(
        id=900015,
        sequencial=1015,
        orgao="6ª Câmara Cível",
        id_orgao=70106,
        classe="Apelação Cível",
        codigo_classe=198,
        relator="Desembargador Teobaldo Siqueira Lins",
        data_julgamento="24/09/2026",
        corpo=(
            "EMENTA: APELAÇÃO CÍVEL. SEGURO DE VIDA. DOENÇA PREEXISTENTE. MÁ-FÉ NÃO "
            "COMPROVADA. INDENIZAÇÃO DEVIDA.",
            "1. A seguradora não exigiu exames prévios. 2. Recurso desprovido.",
        ),
        destinatarios=(
            Pessoa("SEGURADORA FICTÍCIA BRASILEIRA S/A"),
            Pessoa("OLÍMPIA RESENDE BOTTEGA", "A"),
        ),
        cancelada=True,
    ),
    Ementa(
        id=900016,
        sequencial=1016,
        orgao="15ª Câmara Cível",
        id_orgao=70115,
        classe="Apelação Cível",
        codigo_classe=198,
        relator="Desembargadora Celestina Moura Brandão",
        data_julgamento="23/09/2026",
        corpo=(
            "EMENTA: APELAÇÃO CÍVEL. AÇÃO MONITÓRIA. CHEQUE PRESCRITO. DOCUMENTO HÁBIL.",
            "1. O cheque prescrito emitido por pessoa inscrita no CPF 11144477735 é documento "
            "hábil à ação monitória (Súmula 299 do STJ). 2. Nos autos nº "
            "52998224725209981699, a empresa de CNPJ 11144477735000 juntou o título. 3. O "
            "número 12345678900 informado não corresponde a documento válido. Recurso "
            "desprovido.",
        ),
        destinatarios=(
            Pessoa("DISTRIBUIDORA FICTÍCIA DE ALIMENTOS EIRELI", "A"),
            Pessoa("HONORATO VASCONCELOS PIEDADE"),
        ),
    ),
    Ementa(
        id=900017,
        sequencial=1017,
        orgao="12ª Câmara Cível",
        id_orgao=70112,
        classe="Apelação Cível",
        codigo_classe=198,
        relator="Desembargador Teobaldo Siqueira Lins",
        data_julgamento="22/09/2026",
        corpo=(
            "EMENTA: DIREITO DE FAMÍLIA. DIVÓRCIO. PARTILHA DE BENS. REGIME DA COMUNHÃO "
            "PARCIAL. IMÓVEL ADQUIRIDO NA CONSTÂNCIA DO CASAMENTO.",
            "1. O imóvel adquirido onerosamente durante o casamento integra a meação. 2. "
            "Precedente desta Câmara (Apelação Cível nº 0001234-56.2099.8.16.9999, Rel. Des. "
            "Teobaldo Siqueira Lins). 3. Recurso desprovido.",
        ),
        destinatarios=(
            Pessoa("CREMILDA BARBOSA ZANINELLO", "A"),
            Pessoa("ARLINDO PEREIRA ZANINELLO"),
        ),
        advogados=(ADV_CIVEL,),
        rotulo_data="Data de Julgamento",
    ),
    Ementa(
        id=900018,
        sequencial=1018,
        orgao="4ª Câmara Criminal",
        id_orgao=70004,
        classe="Apelação Criminal",
        codigo_classe=417,
        relator="Desembargador Aristeu Prudente Valença",
        data_julgamento="08/10/2026",
        corpo=(
            "EMENTA: APELAÇÃO CRIMINAL. FURTO QUALIFICADO. PRINCÍPIO DA INSIGNIFICÂNCIA. "
            "INAPLICABILIDADE. REINCIDÊNCIA.",
            "1. Na sustentação oral, o advogado Leocádio Barrancos Vieira pediu a aplicação "
            "do princípio da insignificância. 2. A reincidência específica afasta o "
            "princípio. 3. Recurso desprovido.",
        ),
        destinatarios=(MP, Pessoa("CASIMIRO DUTRA FERRABRÁS")),
        advogados=(ADV_DEFESA,),
    ),
    Ementa(
        id=900019,
        sequencial=1019,
        orgao="13ª Câmara Cível",
        id_orgao=70113,
        classe="Apelação Cível",
        codigo_classe=198,
        relator="Desembargadora Celestina Moura Brandão",
        data_julgamento="21/09/2026",
        corpo=(
            "EMENTA: APELAÇÃO CÍVEL. LOCAÇÃO. DESPEJO POR FALTA DE PAGAMENTO.",
            "Apelante: ESTELITA MARCONDES FURQUIM. Contato informado nos autos: "
            "estelita.furquim@exemplo.invalid, telefone (41) 99999-0000.",
            "1. A purgação da mora fora do prazo legal não impede o despejo. 2. Recurso "
            "desprovido.",
        ),
        destinatarios=(
            Pessoa("ESTELITA MARCONDES FURQUIM", "A"),
            Pessoa("IMOBILIÁRIA FICTÍCIA PINHEIRAL LTDA"),
        ),
        advogados=(ADV_CIVEL,),
    ),
    Ementa(
        id=900020,
        sequencial=1020,
        orgao="2ª Câmara Criminal",
        id_orgao=70002,
        classe="Embargos de Declaração Criminal",
        codigo_classe=420,
        relator="Desembargadora Celestina Moura Brandão",
        data_julgamento="07/10/2026",
        corpo=(
            "EMENTA: EMBARGOS DE DECLARAÇÃO EM APELAÇÃO CRIMINAL. ESTUPRO DE VULNERÁVEL. "
            "ALEGADA CONTRADIÇÃO. INEXISTÊNCIA.",
            "1. O acórdão analisou o depoimento da testemunha Benedita Corrêa Saltimbanco e o "
            "relato da vítima, menor de idade, identificada pelas iniciais. 2. Embargos "
            "opostos por casimiro ferrabrás rejeitados.",
        ),
        destinatarios=(MP, Pessoa("CASIMIRO DUTRA FERRABRÁS")),
        advogados=(ADV_DEFESA,),
    ),
)

OUTRAS: tuple[Outra, ...] = (
    Outra(
        id=910001,
        sequencial=2001,
        tipo_documento="Intimação",
        tipo_comunicacao="Intimação",
        orgao="Vara Cível de Vila Imaginária",
        id_orgao=80001,
        classe="Procedimento Comum Cível",
        codigo_classe=7,
        texto="<p>Fica intimado XERXES DESCARTADONIO, CPF 123.456.789-09, para pagar as "
        "custas em 15 dias.</p>",
        destinatarios=(Pessoa("XERXES DESCARTADONIO"),),
        advogados=(Advogado("YOLANDA DESCARTADINA MOREIRA", "11111"),),
    ),
    Outra(
        id=910002,
        sequencial=2002,
        tipo_documento="Despacho",
        tipo_comunicacao="Intimação",
        orgao="Vara de Família de Vila Imaginária",
        id_orgao=80002,
        classe="Alimentos - Lei Especial Nº 5.478/68",
        codigo_classe=69,
        texto="<p>Designo audiência de conciliação. Intimem-se ZULEICA DESCARTADORA e "
        "TELÊMACO DESCARTADINHO.</p>",
        destinatarios=(Pessoa("ZULEICA DESCARTADORA", "A"), Pessoa("TELÊMACO DESCARTADINHO")),
    ),
    Outra(
        id=910003,
        sequencial=2003,
        tipo_documento="Sentença",
        tipo_comunicacao="Intimação",
        orgao="Vara Criminal de Vila Imaginária",
        id_orgao=80003,
        classe="Ação Penal - Procedimento Ordinário",
        codigo_classe=283,
        texto="<p>Julgo procedente a denúncia para condenar URBANO DESCARTADELLI. A vítima "
        "VIOLETA DESCARTANOVA será intimada.</p>",
        destinatarios=(MP, Pessoa("URBANO DESCARTADELLI")),
    ),
    Outra(
        id=910004,
        sequencial=2004,
        tipo_documento="Acórdão",
        tipo_comunicacao="Intimação",
        orgao="3ª Câmara Criminal",
        id_orgao=70003,
        classe="Apelação Criminal",
        codigo_classe=417,
        texto="<p>Acórdão (inteiro teor). Apelante: WENCESLAU DESCARTAMARO.</p>",
        destinatarios=(Pessoa("WENCESLAU DESCARTAMARO"),),
    ),
    Outra(
        id=910005,
        sequencial=2005,
        tipo_documento="Edital",
        tipo_comunicacao="Edital",
        orgao="Vara Cível de Vila Imaginária",
        id_orgao=80001,
        classe="Usucapião",
        codigo_classe=49,
        texto="<p>Edital de citação de ROSAURA DESCARTÁVEL PINTO e eventuais interessados.</p>",
        destinatarios=(Pessoa("ROSAURA DESCARTÁVEL PINTO"),),
    ),
    Outra(
        id=910006,
        sequencial=2006,
        tipo_documento="Certidão",
        tipo_comunicacao="Intimação",
        orgao="1ª Turma Recursal dos Juizados Especiais",
        id_orgao=70201,
        classe="Recurso Inominado Cível",
        codigo_classe=460,
        texto="<p>Certifico o trânsito em julgado. Parte: OTACÍLIA DESCARTADEIRA.</p>",
        destinatarios=(Pessoa("OTACÍLIA DESCARTADEIRA"),),
    ),
)

# Cadernos: o v1 tem tudo. O v2 (reprocessado por cancelamento) tira a ementa 900020 e
# marca a 900005 como cancelada. O caderno de DATA_SEM_EMENTAS só tem outras comunicações.
AUSENTE_NO_V2 = 900020
CANCELADA_NO_V2 = 900005

# --- Expectativas dos testes ---------------------------------------------------------

# Nomes (e formas parciais) de pessoas físicas que NÃO podem sobrar no texto gravado,
# em comparação sem acento e sem caixa. Camada 1: destinatários e advogados PF.
NOMES_CAMADA_1 = (
    "ANACLETO BORGONOVI QUINTELA",
    "JOAO PEDRO ESCARLATINO DE ANDRADE",
    "JOAO ESCARLATINO",
    "MARIA DAS DORES ZANFIRELLI",
    "HERMENEGILDA CASTANHEIRA",
    "OSVALDINO PRATES",
    "ROSALVO TEIXEIRINHA MENDONCA",
    "GUMERCINDO PALHARINI",
    "ADALGISA FONTOURA REBELO",
    "IRACEMA GUSMAO TREVISANUTO",
    "WALDEMAR CORTEZINI BRAGANCA",
    "GENOVEVA LISBOA",
    "SEVERINO ARCANJO TOLENTINI",
    "SEVERINO TOLENTINI",
    "LEOCADIO BARRANCOS VIEIRA",
    "ESTELITA MARCONDES FURQUIM",
    "CASIMIRO FERRABRAS",
)
# Pessoas que não são destinatárias (vítimas, testemunhas): só a camada 2 (NER) as pega.
NOMES_CAMADA_2 = (
    "CLOTILDE RAVANELLO",
    "FLORISBELA MANTOVANELLI",
    "BENEDITA CORREA SALTIMBANCO",
)
# Devem continuar no texto gravado.
PRESERVADOS = (
    "BANCO FICTÍCIO DO SUL S.A.",
    "TIBÚRCIO VALADARES COMÉRCIO DE MÓVEIS LTDA",
    "MASSA FALIDA DE CONSTRUTORA HORIZONTE IMAGINÁRIO LTDA",
    "CONDOMÍNIO EDIFÍCIO SOLAR DAS ACÁCIAS FICTÍCIAS",
    "ESTADO DO PARANÁ",
    "MUNICÍPIO DE VILA IMAGINÁRIA",
    "INSTITUTO NACIONAL DO SEGURO SOCIAL - INSS",
    "Rel. Min. Bonifácio Cardeal",
    "Rel. Des. Teobaldo Siqueira Lins",
    "Lei Maria da Penha",
)
RELATORES = (
    "Aristeu Prudente Valença",
    "Celestina Moura Brandão",
    "Teobaldo Siqueira Lins",
    "Evandro Pimentel Assunção",
    "Leonor Bittencourt Faria",
)
# CPFs que devem ser mascarados (formatados e sem formatação).
CPFS = ("529.982.247-25", "11144477735")
# Números de 11 dígitos que NÃO são CPF a mascarar (colados a outros dígitos ou DV inválido).
NAO_CPFS = ("52998224725209981699", "11144477735000", "12345678900")
# Prefixo comum a todos os nomes das comunicações descartadas: nunca pode aparecer em
# tabela, arquivo bruto ou log.
MARCADOR_DESCARTADO = "DESCART"
