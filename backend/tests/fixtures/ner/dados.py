"""Ementas sintéticas anotadas para o NER de pessoas (F1-36, F1-37).

Nenhum dado real. Os textos foram escritos do zero, no estilo das ementas do TJPR (DJEN) e do
TJDFT, e todas as pessoas são **nomes fictícios** (combinações de prenomes comuns com
sobrenomes inventados ou raros). Processos usam o ano 2099; CPFs e documentos são de exemplo.

Marcação em ``texto``:

- ``[[Nome]]``: pessoa física que **deve** ser anonimizada (parte, vítima, testemunha, corréu,
  menor, apelido…);
- ``{{Nome}}``: nome que **deve ficar** (relator, magistrado citado em precedente, epônimo).

O que não está marcado (lugares, empresas, órgãos, iniciais já aplicadas como "o menor J.")
pode ser trocado por iniciais sem contar como vazamento: anonimizar a mais é aceitável.

Os casos cobrem os contextos pedidos no F1-36: vítima, testemunha, corréu, "o menor J.",
nomes em caixa alta, nomes com partículas, apelidos entre aspas, nomes colados a pontuação,
além de exceções (relator, ``Rel.``, ``Min.``, ``Des.``, epônimos).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EmentaAnotada:
    estrato: str  # "criminal" | "familia" | "civel"
    relator: str | None  # protegido como na camada 2
    texto: str
    fonte: str = "djen"


EMENTAS: tuple[EmentaAnotada, ...] = (
    # --- Criminal: vítimas, testemunhas, corréus, menores, apelidos ---------------------------
    EmentaAnotada(
        "criminal",
        "Desembargador Teodoro Valquíria Brancalhão",
        "APELAÇÃO CRIMINAL. ROUBO MAJORADO. AUTORIA E MATERIALIDADE COMPROVADAS. Palavra da "
        "vítima [[Clotilde Ravanello]] corroborada pelo depoimento da testemunha "
        "[[Anselmo Peruzzolo]], que presenciou a abordagem. Reconhecimento pessoal válido. "
        "RECURSO DESPROVIDO.",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargadora Hortência Marcondes Vilaça",
        "APELAÇÃO CRIME. TRÁFICO DE DROGAS. O corréu [[Josué Ambrozetti da Silveira]] confessou "
        "a propriedade das substâncias; a defesa de [[Rogério Tasca]] alega mera presença no "
        "local. Prova suficiente para a condenação de ambos. Pena-base mantida.",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargador Ubirajara Fontes Lemes",
        "HABEAS CORPUS. ESTUPRO DE VULNERÁVEL. O menor J. relatou os fatos em depoimento "
        "especial. A genitora, [[Rosimeire Cantarelli]], confirmou a versão. Prisão preventiva "
        "fundamentada na gravidade concreta. ORDEM DENEGADA.",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargador Teodoro Valquíria Brancalhão",
        'APELAÇÃO CRIMINAL. HOMICÍDIO QUALIFICADO. O réu, conhecido como "[[Tonhão]]", '
        "teria agido por motivo torpe. A vítima [[Edivaldo Grützmann]] foi atingida pelas costas. "
        "Decisão dos jurados que encontra apoio na prova. Recurso não provido.",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargadora Hortência Marcondes Vilaça",
        "APELAÇÃO CRIMINAL. LESÃO CORPORAL NO ÂMBITO DOMÉSTICO. {{Lei Maria da Penha}}. "
        "A ofendida [[Lucimara Bortoletto]] narrou agressões reiteradas praticadas por "
        "[[Valdecir Zanchettin]]. Medidas protetivas mantidas. Recurso desprovido.",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargador Ubirajara Fontes Lemes",
        "REVISÃO CRIMINAL. FURTO QUALIFICADO. O requerente [[MARCOS ANTÔNIO FERRAREZI]] alega "
        "erro judiciário. Testemunha [[GENI APARECIDA TOLEDANO]] retratou-se em juízo, sem "
        "elementos novos. Pedido julgado improcedente.",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargador Teodoro Valquíria Brancalhão",
        "APELAÇÃO CRIMINAL. RECEPTAÇÃO. Dolo demonstrado. Precedente: STJ, AgRg no HC "
        "999.001/PR, Rel. Min. {{Bonifácio Cardeal}}, j. 10/03/2099. A apelante "
        "[[Sueli Dalcortivo]] adquiriu o veículo por preço vil. Condenação mantida.",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargadora Hortência Marcondes Vilaça",
        "APELAÇÃO. ROUBO. Depoimentos dos policiais [[Cleber Moschetta]] e "
        "[[Ademir Pavanello]], coerentes entre si (fls. 120/123). Vítima [[Iolanda Strapasson]], "
        "idosa, reconheceu o acusado na delegacia. Majorante do emprego de arma afastada.",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargador Ubirajara Fontes Lemes",
        "AGRAVO EM EXECUÇÃO PENAL. Progressão de regime. O apenado [[Wellington Kaminski]], "
        'vulgo "[[Alemão]]", cometeu falta grave. Reinício da contagem. Recurso desprovido.',
    ),
    EmentaAnotada(
        "criminal",
        "Desembargador Teodoro Valquíria Brancalhão",
        "APELAÇÃO CRIMINAL. ESTELIONATO. A vítima, Sra. [[Neusa Baggio Tremea]], transferiu "
        "valores ao acusado [[Diógenes Lanzarin]], que se apresentava como corretor. Prova "
        "documental e testemunhal robusta. Dosimetria ajustada de ofício.",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargadora Hortência Marcondes Vilaça",
        "HABEAS CORPUS. Excesso de prazo. Paciente [[Jeferson Luiz dos Santos Pellizzari]] "
        "preso há 300 dias. Complexidade do feito, com os corréus [[Marlon Busatto]], "
        "[[Kátia Regina Sbardelotto]] e [[Tiago Hoffelder]]. Ordem denegada.",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargador Ubirajara Fontes Lemes",
        "APELAÇÃO CRIMINAL. ESTUPRO. Palavra da vítima ([[Bruna Cristina Zortéa]]) com especial "
        "relevo nos crimes sexuais; laudo pericial positivo; testemunha ([[Odair Vendruscolo]]) "
        "confirmou ter visto a vítima em choque logo após os fatos.",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargador Teodoro Valquíria Brancalhão",
        "APELAÇÃO CRIMINAL. VIOLÊNCIA DOMÉSTICA. O adolescente [[Kauã Ferraretto]], filho do "
        "casal, presenciou as agressões. A ré [[Cristiane de Oliveira Mazzochi]] negou os fatos. "
        "Absolvição inviável. Recurso desprovido.",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargadora Hortência Marcondes Vilaça",
        "EMBARGOS DE DECLARAÇÃO EM APELAÇÃO CRIMINAL. Omissão inexistente quanto ao depoimento "
        "de [[Altair Benedetti]]. Pretensão de rediscutir a prova. EMBARGOS REJEITADOS.",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargador Ubirajara Fontes Lemes",
        "APELAÇÃO CRIMINAL. TRÁFICO. Interceptação telefônica em que o interlocutor "
        '"[[Magrão]]" ([[Douglas Ferreira Pagliosa]]) negocia a entrega. Associação para o '
        "tráfico configurada. Recurso parcialmente provido apenas para readequar a pena.",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargadora Hortência Marcondes Vilaça",
        "APELAÇÃO CRIMINAL. HOMICÍDIO CULPOSO NA DIREÇÃO DE VEÍCULO. O motorista "
        "[[EDSON LUIZ DE MORAES GRANDO]] trafegava acima da velocidade na rodovia PR-999, em "
        "Cascavel, quando atingiu o ciclista [[RAFAEL STEDILE]]. Culpa demonstrada.",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargador Teodoro Valquíria Brancalhão",
        "RECURSO EM SENTIDO ESTRITO. Pronúncia. Indícios de autoria contra [[Vanderlei Bonatto]]; "
        "a testemunha presencial, [[Marilene Fagundes Trevisol]], relatou a discussão anterior. "
        "In dubio pro societate. Recurso desprovido.",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargadora Hortência Marcondes Vilaça",
        "APELAÇÃO CRIMINAL. AMEAÇA. Retratação da representação após o recebimento da denúncia. "
        "Inadmissibilidade. Vítima: [[Daiane Prestes Lunardi]]; acusado: [[Gilmar Tonial]]. "
        "Recurso ministerial provido.",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargador Ubirajara Fontes Lemes",
        "APELAÇÃO CRIMINAL. LATROCÍNIO TENTADO. As vítimas [[Joana D'Arc Piccinin]] e "
        "[[Pedro Henrique de Lima Casagrande]] foram rendidas no comércio Mercearia Boa Vista "
        "Ltda. Reconhecimento firme. Pena mantida.",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargador Teodoro Valquíria Brancalhão",
        "HABEAS CORPUS. Prisão domiciliar. Paciente mãe de criança menor de 12 anos "
        "(a menor M.E.F., de 4 anos). Precedente do STF (HC 999.002, Rel. Min. "
        "{{Cassiano Lobato Ferraz}}). Ordem concedida.",
    ),
    EmentaAnotada(
        "criminal",
        "Juíza Valentina Pazzini Arruda",
        "APELAÇÃO CRIMINAL. Juizado Especial. Lesão corporal leve. A vítima, "
        "Sr. [[Ovídio Roncato]], "
        "apresentou laudo; o autor do fato, [[Ivanildo Sguarezi]], alegou legítima defesa, não "
        "comprovada. Sentença mantida por seus próprios fundamentos.",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargadora Hortência Marcondes Vilaça",
        "APELAÇÃO CRIMINAL. Conforme o voto do Des. {{Aristides Mattoso Quintela}} no "
        "precedente desta Câmara, a confissão qualificada também atenua a pena. O réu "
        "[[Leandro Fiorentin]] admitiu a subtração. Atenuante reconhecida.",
    ),
    # --- Família e sucessões ---------------------------------------------------------------------
    EmentaAnotada(
        "familia",
        "Desembargador Saturnino Rebouças Alcoforado",
        "APELAÇÃO CÍVEL. AÇÃO DE ALIMENTOS. Binômio necessidade-possibilidade. O alimentante "
        "[[Rodrigo Esteves Marcolino]] comprovou redução de renda; a alimentanda, "
        "[[Isadora Marcolino]], estuda em período integral. Alimentos fixados em 20%.",
    ),
    EmentaAnotada(
        "familia",
        "Desembargadora Celestina Albuquerque Penteado",
        "AGRAVO DE INSTRUMENTO. GUARDA COMPARTILHADA. Os genitores [[Fabiana Lemos Taglieber]] e "
        "[[Gustavo Taglieber]] residem em cidades distintas. Estudo psicossocial favorável à "
        "residência materna, com convivência ampla do pai.",
    ),
    EmentaAnotada(
        "familia",
        "Desembargador Saturnino Rebouças Alcoforado",
        "APELAÇÃO CÍVEL. INVENTÁRIO. Partilha de bens do espólio de [[Adelino Cordeiro Bazzo]]. "
        "Herdeiros [[Marta Bazzo Pilatti]], [[Sérgio Bazzo]] e [[Luzia Bazzo de Andrade]]. "
        "Colação de doação inoficiosa. Recurso parcialmente provido.",
    ),
    EmentaAnotada(
        "familia",
        "Desembargadora Celestina Albuquerque Penteado",
        "APELAÇÃO CÍVEL. INVESTIGAÇÃO DE PATERNIDADE. Exame de DNA positivo. O investigado "
        "[[ARLINDO JOSÉ DOS REIS FAVARETTO]] recusou-se a novo exame. Súmula 301 do STJ. "
        "Paternidade declarada em favor de [[LORENA FAVARETTO]].",
    ),
    EmentaAnotada(
        "familia",
        "Desembargador Saturnino Rebouças Alcoforado",
        "APELAÇÃO CÍVEL. DIVÓRCIO LITIGIOSO. Partilha do imóvel situado em Ponta Grossa. "
        "A ex-cônjuge, [[Simone Aparecida Dall'Agnol]], comprovou a contribuição. Imóvel "
        "partilhado à razão de 50%.",
    ),
    EmentaAnotada(
        "familia",
        "Desembargadora Celestina Albuquerque Penteado",
        "AGRAVO DE INSTRUMENTO. ECA. Acolhimento institucional das crianças "
        "[[Enzo Gabriel Rocha Tibola]] e [[Maria Eduarda Rocha Tibola]]. A tia materna, "
        "[[Claudete Rocha]], pleiteia a guarda. Estudo social pendente. Recurso provido.",
    ),
    EmentaAnotada(
        "familia",
        "Desembargador Saturnino Rebouças Alcoforado",
        "APELAÇÃO CÍVEL. UNIÃO ESTÁVEL POST MORTEM. A companheira [[Ivone Lúcia Gasparetto]] "
        "conviveu com o falecido [[Osvaldo Pierdoná]] por 18 anos, conforme as testemunhas "
        "[[Leonir Bettio]] e [[Celina Bettio]]. Reconhecimento mantido.",
    ),
    EmentaAnotada(
        "familia",
        "Desembargadora Celestina Albuquerque Penteado",
        "APELAÇÃO CÍVEL. ALIMENTOS AVOENGOS. Responsabilidade subsidiária dos avós "
        "[[Antenor Scheffer]] e [[Hilda Scheffer]]. Impossibilidade do genitor não demonstrada. "
        "Recurso desprovido. Precedente: REsp 999.003/SP, Rel. Min. {{Bonifácio Cardeal}}.",
    ),
    EmentaAnotada(
        "familia",
        "Desembargador Saturnino Rebouças Alcoforado",
        "APELAÇÃO CÍVEL. ADOÇÃO. Destituição do poder familiar de [[Jucelia Ramos Brizola]]. "
        "O menor J.R.B. está sob os cuidados do casal adotante há 3 anos. Laços afetivos "
        "consolidados. Sentença mantida.",
    ),
    EmentaAnotada(
        "familia",
        "Desembargadora Celestina Albuquerque Penteado",
        "APELAÇÃO CÍVEL. TESTAMENTO. Nulidade alegada pelos herdeiros de "
        "Dona [[Eulália Martins Schiavon]]. Testemunhas instrumentárias ([[Ary Fumagalli]], "
        "[[Nair Fumagalli]]) confirmaram a lucidez da testadora. Validade reconhecida.",
    ),
    EmentaAnotada(
        "familia",
        "Desembargador Saturnino Rebouças Alcoforado",
        "AGRAVO DE INSTRUMENTO. Regulamentação de visitas. Alienação parental atribuída a "
        "[[Patrícia van der Laan Moretto]]. Acompanhamento psicológico determinado.",
    ),
    EmentaAnotada(
        "familia",
        "Desembargadora Celestina Albuquerque Penteado",
        "APELAÇÃO CÍVEL. CURATELA. O interditando, Sr. [[Belmiro Zanatta]], apresenta quadro "
        "de demência. Nomeada curadora a filha, [[Rosana Zanatta Facchin]]. Recurso desprovido.",
    ),
    # --- Cível -----------------------------------------------------------------------------------
    EmentaAnotada(
        "civel",
        "Desembargador Florisvaldo Mendonça Tavares",
        "APELAÇÃO CÍVEL. AÇÃO INDENIZATÓRIA. Inscrição indevida. O autor "
        "[[Reinaldo Gonçalves Bottega]] demonstrou a quitação do débito junto ao Banco Exemplo "
        "S.A. Danos morais fixados em R$ 8.000,00. Recurso parcialmente provido.",
    ),
    EmentaAnotada(
        "civel",
        "Desembargadora Laudelina Saraiva Couto",
        "APELAÇÃO CÍVEL. ACIDENTE DE TRÂNSITO. Colisão traseira. O condutor [[Fábio Conterato]] "
        "não guardou distância de segurança. Lucros cessantes do taxista "
        "[[Nelson Caldart]] comprovados. Sentença mantida.",
    ),
    EmentaAnotada(
        "civel",
        "Desembargador Florisvaldo Mendonça Tavares",
        "APELAÇÃO CÍVEL. PLANO DE SAÚDE. Negativa de cobertura de cirurgia bariátrica à "
        "beneficiária [[Graziele Matiello]]. Abusividade. Súmula 608 do STJ. Dano moral "
        "configurado.",
    ),
    EmentaAnotada(
        "civel",
        "Desembargadora Laudelina Saraiva Couto",
        "APELAÇÃO CÍVEL. USUCAPIÃO EXTRAORDINÁRIA. Posse mansa e pacífica de [[ORLANDO PIVETTA]] "
        "e [[TEREZINHA PIVETTA]] por mais de 15 anos, atestada pelos vizinhos "
        "[[JOÃO BATISTA DE SOUZA LORENZON]] e [[AMÉLIA LORENZON]].",
    ),
    EmentaAnotada(
        "civel",
        "Desembargador Florisvaldo Mendonça Tavares",
        "AGRAVO DE INSTRUMENTO. CUMPRIMENTO DE SENTENÇA. Penhora de salário do executado "
        "[[Márcio Spagnol]]. Possibilidade excepcional, preservado o mínimo existencial. "
        "Tema repetitivo. Recurso provido em parte.",
    ),
    EmentaAnotada(
        "civel",
        "Desembargadora Laudelina Saraiva Couto",
        "APELAÇÃO CÍVEL. RESPONSABILIDADE CIVIL MÉDICA. Erro em parto. A paciente "
        "[[Aline Mascarello]] sofreu laceração. O médico Dr. [[Heitor Brambilla]] não seguiu o "
        "protocolo. Hospital Exemplo de Curitiba responde objetivamente.",
    ),
    EmentaAnotada(
        "civel",
        "Desembargador Florisvaldo Mendonça Tavares",
        "APELAÇÃO CÍVEL. LOCAÇÃO. Despejo por falta de pagamento. Fiadores [[Elton Barichello]] "
        "e [[Rosângela Barichello]]. Exoneração da fiança não comunicada. Responsabilidade "
        "até a entrega das chaves.",
    ),
    EmentaAnotada(
        "civel",
        "Desembargadora Laudelina Saraiva Couto",
        "APELAÇÃO CÍVEL. CONSUMIDOR. Vício do produto. A compradora, Srta. [[Bianca Zilli]], "
        "adquiriu o refrigerador na Loja Exemplo Eletro Ltda. Restituição do valor pago.",
    ),
    EmentaAnotada(
        "civel",
        "Desembargador Florisvaldo Mendonça Tavares",
        "APELAÇÃO CÍVEL. DIREITO DE VIZINHANÇA. Infiltração no imóvel de [[Wilson Pegoraro]], "
        "causada pela obra de [[Sandro Fachinello]]. Laudo pericial conclusivo. Obrigação de "
        "fazer e danos materiais.",
    ),
    EmentaAnotada(
        "civel",
        "Desembargadora Laudelina Saraiva Couto",
        "APELAÇÃO CÍVEL. SERVIDOR PÚBLICO. Município de Exemplópolis. Progressão funcional da "
        "professora [[Vera Lúcia Andreatta]]. Direito reconhecido. Juros e correção conforme "
        "o Tema 905 do STJ.",
    ),
    EmentaAnotada(
        "civel",
        "Desembargador Florisvaldo Mendonça Tavares",
        "APELAÇÃO CÍVEL. AÇÃO MONITÓRIA. Cheques emitidos por [[Leocádio Barrancos Vieira]] "
        "em favor de Comércio de Cereais Exemplo Ltda. Prescrição afastada. Embargos "
        "monitórios rejeitados.",
    ),
    EmentaAnotada(
        "civel",
        "Desembargadora Laudelina Saraiva Couto",
        "APELAÇÃO CÍVEL. SEGURO DE VIDA. Morte do segurado [[Hamilton Zago]]. Doença "
        "preexistente não comprovada pela seguradora. Beneficiária, a viúva "
        "[[Lurdes Zago]], faz jus à indenização. Recurso desprovido.",
    ),
    EmentaAnotada(
        "civel",
        "Desembargador Florisvaldo Mendonça Tavares",
        "APELAÇÃO CÍVEL. Conforme decidido no REsp 999.004/RS (Rel. Min. "
        "{{Cassiano Lobato Ferraz}}) e na {{Lei Carolina Dieckmann}}, a divulgação das fotos "
        "de [[Priscila Gomes Rotava]] gera dano moral in re ipsa.",
    ),
    EmentaAnotada(
        "civel",
        "Desembargadora Laudelina Saraiva Couto",
        "APELAÇÃO CÍVEL. AÇÃO DE COBRANÇA. Honorários do corretor [[Marcelo Dalla Costa]] "
        "pela venda da Fazenda Santa Rita, em Guarapuava. Aproximação útil comprovada.",
    ),
    EmentaAnotada(
        "civel",
        "Desembargador Florisvaldo Mendonça Tavares",
        "EMBARGOS DE DECLARAÇÃO. Contradição quanto ao nome da autora "
        "([[Kelly Cristine Pertile]]) e à data do acidente. Erro material corrigido. "
        "Embargos acolhidos sem efeitos infringentes.",
    ),
    # --- TJDFT (texto puro, relator em maiúsculas) ------------------------------------------------
    EmentaAnotada(
        "criminal",
        "LEOPOLDINA ARAGÃO FERNANDES",
        "PENAL E PROCESSO PENAL. APELAÇÃO. ROUBO CIRCUNSTANCIADO. RECONHECIMENTO. 1. A vítima "
        "[[Gerusa Pimentel Okamoto]] descreveu o autor com detalhes. 2. O corréu "
        "[[Railson Bezerra Quaresma]] confessou na fase policial. 3. Recurso conhecido e "
        "desprovido.",
        fonte="tjdft",
    ),
    EmentaAnotada(
        "criminal",
        "OTACÍLIO BRAGANÇA NEVES",
        "APELAÇÃO CRIMINAL. VIOLÊNCIA DOMÉSTICA E FAMILIAR CONTRA A MULHER. "
        "{{LEI MARIA DA PENHA}}. "
        "1. As declarações da ofendida, [[JÉSSICA NAYARA FROTA]], foram confirmadas pela "
        "vizinha, [[RAIMUNDA SOARES PIMENTA]]. 2. Recurso desprovido.",
        fonte="tjdft",
    ),
    EmentaAnotada(
        "civel",
        "LEOPOLDINA ARAGÃO FERNANDES",
        "DIREITO DO CONSUMIDOR. APELAÇÃO. TRANSPORTE AÉREO. Atraso de voo. A passageira "
        "[[Thaís Moura Esteves Bragança]] perdeu a conexão em Brasília. Dano moral de "
        "R$ 5.000,00. Recurso parcialmente provido.",
        fonte="tjdft",
    ),
    EmentaAnotada(
        "familia",
        "OTACÍLIO BRAGANÇA NEVES",
        "DIREITO DE FAMÍLIA. GUARDA. 1. O pai, [[Wanderson Lima Cavalcante]], e a mãe, "
        "[[Kelen Cristina Siqueira]], disputam a guarda do filho. 2. Estudo do SERAF "
        "recomenda a guarda compartilhada, com lar de referência materno.",
        fonte="tjdft",
    ),
    EmentaAnotada(
        "criminal",
        "LEOPOLDINA ARAGÃO FERNANDES",
        "HABEAS CORPUS. TRÁFICO. Prisão preventiva de [[Uelinton Ramos]], vulgo "
        '"[[Pezão]]", flagrado com 2 kg de maconha no Recanto das Emas. Garantia da ordem '
        "pública. Ordem denegada.",
        fonte="tjdft",
    ),
    EmentaAnotada(
        "civel",
        "OTACÍLIO BRAGANÇA NEVES",
        "JUIZADO ESPECIAL CÍVEL. Compra on-line não entregue. Recorrente: empresa Exemplo "
        "Comércio Digital Ltda. A consumidora [[Edilene Gomes]] comprovou o pagamento. "
        "Recurso conhecido e não provido.",
        fonte="tjdft",
    ),
    EmentaAnotada(
        "criminal",
        "OTACÍLIO BRAGANÇA NEVES",
        "PENAL. FURTO. PRINCÍPIO DA INSIGNIFICÂNCIA. Inaplicável ao réu reincidente "
        "[[Cícero dos Anjos Batista]]. Precedente do STJ (Rel. Ministro "
        "{{Aurélio Prudente Vasconcelos}}). Recurso desprovido.",
        fonte="tjdft",
    ),
    EmentaAnotada(
        "criminal",
        "LEOPOLDINA ARAGÃO FERNANDES",
        "APELAÇÃO CRIMINAL. ESTUPRO DE VULNERÁVEL. A vítima, à época com 11 anos, revelou os "
        "abusos à professora [[Sandra Regina Lacerda]]; o acusado, padrasto, "
        "[[Josivaldo Pereira Nunes]], negou. Prova suficiente. Recurso desprovido.",
        fonte="tjdft",
    ),
    # --- Casos difíceis ----------------------------------------------------------------------
    EmentaAnotada(
        "criminal",
        "Desembargador Ubirajara Fontes Lemes",
        "APELAÇÃO CRIMINAL. A vítima [[Rosa]] relatou que o réu [[Ferrarezi]] a ameaçou com uma "
        "faca; a filha, [[Vitória]], confirmou. Testemunha [[Jesus Cruz da Paz]] nada viu.",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargadora Hortência Marcondes Vilaça",
        "APELAÇÃO CRIMINAL. Vítima:[[Clarice Montenegro Wolff]];acusado:[[Ítalo Brunetta]]. "
        "Interrogatório de [[Brunetta]] contraditório (mov. 45.1).",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargador Teodoro Valquíria Brancalhão",
        "APELAÇÃO CRIMINAL. TRÁFICO TRANSNACIONAL. Os estrangeiros [[Yuki Tanaka]] e "
        "[[Mohammed Al-Rashid]] foram presos no Aeroporto Afonso Pena com a passageira "
        "[[Ana-Paula Kowalczyk]]. Transnacionalidade comprovada.",
    ),
    EmentaAnotada(
        "criminal",
        "OTACÍLIO BRAGANÇA NEVES",
        "PENAL. APELAÇÃO. ROUBO. A VÍTIMA [[MARIA DAS GRAÇAS FONSECA LIMA]] RECONHECEU O RÉU "
        '[[FRANCISCO DE ASSIS DO NASCIMENTO]], VULGO "[[CHICÃO]]", NA DELEGACIA. '
        "CONDENAÇÃO MANTIDA. RECURSO DESPROVIDO.",
        fonte="tjdft",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargador Ubirajara Fontes Lemes",
        "APELAÇÃO CRIMINAL. A testemunha [[Luz Marina Bettanin]], de 70 anos, e o vizinho "
        "[[Felício]] ouviram os disparos na Rua Marechal Deodoro, em frente à Escola Estadual "
        "Monteiro Lobato. Autoria comprovada.",
    ),
    EmentaAnotada(
        "familia",
        "Desembargador Saturnino Rebouças Alcoforado",
        "APELAÇÃO CÍVEL. Alimentos. A autora, [[Kelly]], representada pela mãe, "
        "Dra. [[Simone Grazziotin]] (advogada em causa própria), pede majoração. O réu, "
        "[[Paulo Sérgio]], é autônomo. Alimentos mantidos em 1,5 salário mínimo.",
    ),
    EmentaAnotada(
        "familia",
        "Desembargadora Celestina Albuquerque Penteado",
        "APELAÇÃO CÍVEL. Sucessões. Segundo leciona Pontes de Miranda, a colação é dever dos "
        "descendentes. A herdeira [[Antônia]] (filha de [[Benedito Piovesan]]) recebeu doação "
        "em vida. Colação determinada.",
    ),
    EmentaAnotada(
        "civel",
        "Desembargador Florisvaldo Mendonça Tavares",
        "APELAÇÃO CÍVEL. Seguro. O veículo de [[José Carlos]], estacionado na Avenida Getúlio "
        "Vargas, foi furtado. A seguradora alegou agravamento do risco porque o filho, "
        "[[Matheus]], de 17 anos, usava o carro. Indenização devida.",
    ),
    EmentaAnotada(
        "civel",
        "Desembargadora Laudelina Saraiva Couto",
        "APELAÇÃO CÍVEL. Dano moral. Ofensas publicadas por perfil anônimo não "
        "identificado; o provedor deve fornecer os dados do usuário. A ofendida, "
        "[[Grasiela Pitol]], comprovou a repercussão.",
    ),
    EmentaAnotada(
        "civel",
        "Desembargador Florisvaldo Mendonça Tavares",
        "APELAÇÃO CÍVEL. Contrato. [[Leonardo Taborda]] e sua esposa, [[Mariana]], firmaram "
        "promessa de compra e venda com Construtora Exemplo Ltda. Atraso na entrega. "
        "Lucros cessantes presumidos.",
    ),
    EmentaAnotada(
        "criminal",
        "Desembargador Teodoro Valquíria Brancalhão",
        "HABEAS CORPUS. O paciente ([[Rodrigo]]), primário, foi preso com o comparsa [[Juninho]]. "
        "O pai, seu [[Arlindo]], é idoso e depende dele. Liberdade provisória com cautelares.",
    ),
    EmentaAnotada(
        "criminal",
        "LEOPOLDINA ARAGÃO FERNANDES",
        "PENAL. VIOLÊNCIA DOMÉSTICA. 1. A ofendida J.S. (iniciais) e a irmã, "
        "[[Damiana Sousa Ribeiro]], relataram as agressões de [[Elisvaldo]]. 2. Recurso "
        "desprovido.",
        fonte="tjdft",
    ),
)


def _ementa_longa() -> EmentaAnotada:
    """Mais de 512 tokens: nomes no começo, no meio e no fim (janelas com sobreposição)."""
    paragrafo = (
        "A prova oral produzida em juízo, sob o crivo do contraditório, é harmônica com os "
        "elementos colhidos na fase inquisitorial, não havendo razão para desconsiderá-la. "
    )
    return EmentaAnotada(
        "criminal",
        "Desembargador Ubirajara Fontes Lemes",
        "APELAÇÃO CRIMINAL. A vítima [[Odete Marangoni]] reconheceu o acusado. "
        + paragrafo * 8
        + "A testemunha [[Honório Zambiasi]] confirmou a versão. "
        + paragrafo * 8
        + "Por fim, o corréu [[Wagner Tessaro]] também foi condenado. Recurso desprovido.",
    )


EMENTAS += (_ementa_longa(),)
