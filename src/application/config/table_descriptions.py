TABLE_DESCRIPTIONS = {
    "internacoes": {
        "title": "Internações SIH-RD (TABELA PRINCIPAL)",
        "description": "Tabela central do banco sihrd5. Cada registro corresponde a uma AIH (Autorização de Internação Hospitalar). Contém dados do hospital (CNES), datas, diagnósticos principal e secundário, indicadores de óbito (MORTE boolean + CID_MORTE), dados clínicos (ESPEC, IND_VDRL, GESTRISCO, INSC_PN), valores financeiros (VAL_SH, VAL_SP, VAL_UTI, VAL_TOT), dias de permanência (DIAS_PERM) e dados demográficos completos do paciente (SEXO, IDADE, RACA_COR, ETNIA, NACIONAL, INSTRU, VINCPREV, MUNIC_RES). Para listar procedimentos use JOIN com internacao_procedimento+procedimentos.",
        "purpose": "Análises de internações, mortalidade, diagnósticos, custos, permanência e perfil demográfico dos pacientes",
        "use_cases": [
            'Contar mortes: WHERE "MORTE" = true',
            'Tempo de permanência: "DIAS_PERM"',
            "Custos de internação: VAL_TOT, VAL_SH, VAL_SP, VAL_UTI",
            'VDRL/sífilis: WHERE "IND_VDRL" = true',
            'Internações obstétricas: "GESTRISCO", "INSC_PN", "CONTRACEP1", "CONTRACEP2"',
        ],
        "key_columns": [
            '"N_AIH"',
            '"CNES"',
            '"SEXO"',
            '"IDADE"',
            '"MUNIC_RES"',
            '"DIAG_PRINC"',
            '"DIAG_SECUN"',
            '"CID_MORTE"',
            '"MORTE"',
            '"IND_VDRL"',
            '"DIAS_PERM"',
            '"VAL_TOT"',
            '"VAL_SH"',
            '"VAL_SP"',
            '"VAL_UTI"',
            '"DT_INTER"',
            '"DT_SAIDA"',
            '"ESPEC"',
            '"RACA_COR"',
            '"ETNIA"',
            '"NACIONAL"',
            '"INSTRU"',
            '"VINCPREV"',
            '"GESTRISCO"',
            '"INSC_PN"',
            '"CONTRACEP1"',
            '"CONTRACEP2"',
            '"NUM_FILHOS"',
        ],
        "value_mappings": {
            '"SEXO"': "1=MASCULINO, 3=FEMININO (NUNCA usar 2!)",
            '"MORTE"': "true=óbito durante internação, false=alta",
            '"IND_VDRL"': "true=VDRL positivo (sífilis), false=negativo",
            '"IDADE"': "Idade em anos completos",
            '"MUNIC_RES"': "FK → municipios.CO_MUNICIPIO_6D (código 6 dígitos do município de residência)",
            '"DIAG_PRINC"': "FK → cid.CID (código CID-10 do diagnóstico principal)",
            '"DIAG_SECUN"': "FK → cid.CID (código CID-10 do diagnóstico secundário)",
            '"CID_MORTE"': "Código CID-10 da causa da morte (preenchido quando MORTE = true)",
            '"CNES"': "FK → hospital.CNES",
            '"ESPEC"': "FK → especialidade.ESPEC (especialidade do leito)",
            '"RACA_COR"': "FK → raca_cor.RACA_COR for identified categories 1..5; internacoes may contain 99=Sem informação",
            '"ETNIA"': "FK → etnia.ETNIA",
            '"NACIONAL"': "FK → nacionalidade.NACIONAL",
            '"INSTRU"': "FK → instrucao.INSTRU (0=Sem info, 1=Não sabe ler, 2=Alfabetizado, 3=1°grau incompleto...)",
            '"VINCPREV"': "FK → vincprev.VINCPREV (0=Sem info, 1=Autônomo, 2=Desempregado, 3=Aposentado, 4=Não segurado, 5=Empregado, 6=Empregador)",
            '"GESTRISCO"': "Gestação de risco (quando preenchido)",
            '"INSC_PN"': "Inscrição de pré-natal (quando preenchido indica acompanhamento pré-natal)",
        },
        "critical_notes": [
            '"N_AIH" é chave primária',
            'MORTE é boolean — use WHERE "MORTE" = true para contar óbitos (NÃO existe tabela mortes separada)',
            'IND_VDRL é boolean — use WHERE "IND_VDRL" = true para VDRL positivo',
            "DIAS_PERM substitui QT_DIARIAS do banco anterior",
            'Para "por idade" ou "distribuição por idade": agrupar por "IDADE" bruto; só criar faixas quando a pergunta disser "faixa etária"/"grupo etário"',
            'Para procedimentos: JOIN com internacao_procedimento via "N_AIH" e depois JOIN procedimentos via "PROC_REA"',
            'JOIN com cid via "DIAG_PRINC" para descrição de diagnóstico',
            'JOIN com hospital via "CNES" para dados do estabelecimento',
            'JOIN com municipios via "MUNIC_RES" = municipios."CO_MUNICIPIO_6D"',
        ],
        "relationships": [
            '→ hospital("CNES")',
            '→ cid("DIAG_PRINC")',
            '→ cid("DIAG_SECUN")',
            '→ municipios("MUNIC_RES" = CO_MUNICIPIO_6D)',
            '→ sexo("SEXO")',
            '→ raca_cor("RACA_COR")',
            '→ etnia("ETNIA")',
            '→ nacionalidade("NACIONAL")',
            '→ instrucao("INSTRU")',
            '→ vincprev("VINCPREV")',
            '→ especialidade("ESPEC")',
            '→ contraceptivos("CONTRACEP1", "CONTRACEP2")',
            '← internacao_procedimento("N_AIH")',
        ],
    },
    "internacao_procedimento": {
        "title": "Internação-Procedimento — Procedimentos por Internação (JUNCTION TABLE)",
        "description": "Tabela de ligação entre internacoes e procedimentos. Cada registro representa um procedimento realizado durante uma internação. Uma internação pode ter múltiplos procedimentos (37M+ registros). Use esta tabela sempre que precisar relacionar internações com procedimentos.",
        "purpose": "Ligar internações a procedimentos médicos realizados",
        "use_cases": [
            "Quais procedimentos foram realizados em uma internação",
            "Quantas vezes um procedimento foi realizado no total",
            "Procedimentos mais comuns: GROUP BY PROC_REA + JOIN procedimentos",
            "Análises de volume de procedimentos por hospital/período",
        ],
        "key_columns": ['"id_atendimento"', '"N_AIH"', '"PROC_REA"'],
        "value_mappings": {
            '"N_AIH"': "FK → internacoes.N_AIH",
            '"PROC_REA"': "FK → procedimentos.PROC_REA (código do procedimento realizado)",
        },
        "critical_notes": [
            '"id_atendimento" é chave primária (auto-increment)',
            'Para listar procedimentos de uma internação: JOIN internacoes ON "N_AIH" e JOIN procedimentos ON "PROC_REA"',
            "Uma internação pode ter vários procedimentos (relação 1:N)",
            "NUNCA use internacoes.PROC_REA — essa coluna não existe mais; use internacao_procedimento",
        ],
        "relationships": ['→ internacoes("N_AIH")', '→ procedimentos("PROC_REA")'],
    },
    "cid": {
        "title": "Códigos CID-10 (TABELA DE REFERÊNCIA)",
        "description": "Tabela de referência com os códigos da Classificação Internacional de Doenças (CID-10) e suas descrições. Use para JOINs/lookups de descrição e para cardinalidade do catálogo quando a pergunta pedir quantos códigos CID existem, estão cadastrados, disponíveis ou distintos. Para contar internações por diagnóstico observado, use internacoes.",
        "purpose": "REFERÊNCIA — catálogo de códigos CID-10 e lookup de nomes de doenças",
        "use_cases": [
            "JOIN com internacoes para obter descrição do diagnóstico",
            "Lookup de nome de doença a partir do código CID",
            "Contar códigos CID-10 existentes/cadastrados/disponíveis no catálogo",
        ],
        "key_columns": ['"CID"', '"DESCRICAO"'],
        "value_mappings": {
            '"CID"': "Código CID-10 (ex: F190, J44, I25)",
            '"DESCRICAO"': "Descrição completa da doença/condição",
        },
        "critical_notes": [
            "Para 'quantos códigos CID existem/cadastrados/disponíveis/distintos', conte cid.\"CID\" nesta tabela.",
            "Para 'CIDs registrados/observados/usados em internações', conte os códigos nas colunas de internacoes.",
            '"CID" é chave primária',
            'JOINs: internacoes."DIAG_PRINC" = cid."CID" ou internacoes."DIAG_SECUN" = cid."CID" ou internacoes."CID_MORTE" = cid."CID"',
            "Tabela anteriormente chamada cid10 — agora se chama cid",
        ],
        "relationships": [
            '← internacoes("DIAG_PRINC")',
            '← internacoes("DIAG_SECUN")',
            '← internacoes("CID_MORTE")',
        ],
    },
    "municipios": {
        "title": "Municípios Brasileiros",
        "description": "Tabela de referência com os municípios do Brasil. Contém código 6 dígitos (chave primária), código IBGE 7 dígitos, nome, estado (UF) e coordenadas geográficas. Use como fonte de cobertura geográfica quando a pergunta pedir quantos municípios/estados existem, estão cadastrados ou estão cobertos pelo banco de dados.",
        "purpose": "Dimensão geográfica, cobertura de municípios/estados e localização de pacientes e hospitais",
        "use_cases": [
            "Contar municípios cadastrados ou municípios por estado",
            "Contar estados/UFs cobertos pela base de referência geográfica",
            "Análises por estado/cidade",
            "JOIN com internacoes para nome do município de residência do paciente",
            "JOIN com hospital via MUNIC_MOV para município do hospital",
            "Dados de localização geográfica (lat/long)",
        ],
        "key_columns": [
            '"CO_MUNICIPIO_6D"',
            '"CO_MUNICIPIO_7D"',
            '"NO_MUNICIPIO"',
            '"SG_UF"',
            '"latitude"',
            '"longitude"',
        ],
        "value_mappings": {
            '"CO_MUNICIPIO_6D"': "Código 6 dígitos (chave primária — usado em FKs)",
            '"CO_MUNICIPIO_7D"': "Código IBGE 7 dígitos",
            '"SG_UF"': "Sigla do estado (RS, SP, RJ...)",
            '"NO_MUNICIPIO"': "Nome completo do município",
        },
        "critical_notes": [
            '"CO_MUNICIPIO_6D" é chave primária',
            "Para 'quantos municípios/estados existem/cobertos/cadastrados no banco', conte diretamente municipios.",
            "Para 'estados/municípios com internações observadas', junte com internacoes.",
            'JOIN com internacoes: internacoes."MUNIC_RES" = municipios."CO_MUNICIPIO_6D"',
            'JOIN com hospital: hospital."MUNIC_MOV" = municipios."CO_MUNICIPIO_6D"',
            'JOIN com socioeconomico: socioeconomico."CO_MUNICIPIO_6D" = municipios."CO_MUNICIPIO_6D"',
        ],
        "relationships": [
            '← internacoes("MUNIC_RES")',
            '← hospital("MUNIC_MOV")',
            '← socioeconomico("CO_MUNICIPIO_6D")',
        ],
    },
    "hospital": {
        "title": "Estabelecimentos de Saúde",
        "description": "Tabela de referência dos estabelecimentos de saúde. Contém o código CNES, município onde o hospital está localizado (MUNIC_MOV), tipo de gestão e natureza jurídica.",
        "purpose": "Informações sobre hospitais e estabelecimentos de saúde",
        "use_cases": [
            "Análises por tipo de hospital (público vs privado)",
            "Gestão pública vs privada",
            "Município do hospital",
        ],
        "key_columns": ['"CNES"', '"MUNIC_MOV"', '"NATUREZA"', '"GESTAO"', '"NAT_JUR"'],
        "value_mappings": {
            '"CNES"': "Código Nacional Estabelecimento Saúde (chave primária)",
            '"MUNIC_MOV"': "FK → municipios.CO_MUNICIPIO_6D (município onde o hospital está)",
            '"NATUREZA"': "0=Público federal, 20/22=Público municipal/estadual, 30=Filantrópico, 40=Sem fins lucrativos, 50=Privado lucrativo, 60/61=Privado filantrópico",
            '"GESTAO"': "1=Estadual, 2=Municipal",
            '"NAT_JUR"': "Natureza jurídica (código numérico)",
        },
        "critical_notes": [
            '"CNES" é chave primária',
            'JOIN com internacoes: internacoes."CNES" = hospital."CNES"',
            'JOIN com municipios: hospital."MUNIC_MOV" = municipios."CO_MUNICIPIO_6D"',
        ],
        "relationships": ['← internacoes("CNES")', '→ municipios("MUNIC_MOV")'],
    },
    "procedimentos": {
        "title": "Procedimentos Médicos",
        "description": "Tabela de referência com códigos e nomes dos procedimentos médicos (SIGTAP). Para contar procedimentos realizados em internações, use internacao_procedimento como junction table.",
        "purpose": "Lookup de nomes e códigos de procedimentos",
        "use_cases": [
            "Lookup do nome de um procedimento a partir do código",
            "JOIN com internacao_procedimento para listar procedimentos por internação",
            "Ranking dos procedimentos mais realizados",
        ],
        "key_columns": ['"PROC_REA"', '"NOME_PROC"'],
        "value_mappings": {
            '"PROC_REA"': "Código do procedimento (chave primária)",
            '"NOME_PROC"': "Nome/descrição oficial do procedimento",
        },
        "critical_notes": [
            '"PROC_REA" é chave primária',
            'Para contar procedimentos por internação: JOIN internacao_procedimento ON "PROC_REA" e JOIN internacoes ON "N_AIH"',
            "Não existe mais PROC_REA direto em internacoes — use internacao_procedimento como intermediário",
        ],
        "relationships": ['← internacao_procedimento("PROC_REA")'],
    },
    "instrucao": {
        "title": "Nível de Instrução (LOOKUP TABLE)",
        "description": "Tabela de referência com os códigos e descrições dos níveis de instrução/escolaridade dos pacientes. Os valores de INSTRU estão diretamente em internacoes.",
        "purpose": "Lookup dos códigos de escolaridade",
        "use_cases": [
            "JOIN com internacoes para obter descrição do nível de instrução",
            "Análise de internações por escolaridade",
        ],
        "key_columns": ['"INSTRU"', '"DESCRICAO"'],
        "value_mappings": {
            '"INSTRU"': "0=Sem informação, 1=Não sabe ler/escrever, 2=Alfabetizado, 3=1°grau incompleto, 4=1°grau completo, 5=2°grau incompleto, 6=2°grau completo, 7=Superior incompleto, 8=Superior completo, 9=Especialização/Residência, 10=Mestrado, 11=Doutorado"
        },
        "critical_notes": [
            '"INSTRU" é chave primária',
            'JOIN com internacoes: internacoes."INSTRU" = instrucao."INSTRU"',
        ],
        "relationships": ['← internacoes("INSTRU")'],
    },
    "vincprev": {
        "title": "Vínculo Previdenciário (LOOKUP TABLE)",
        "description": "Tabela de referência com os códigos e descrições dos tipos de vínculo previdenciário dos pacientes. Os valores observados por internação estão em internacoes.VINCPREV. Use vincprev para cardinalidade do catálogo quando a pergunta pedir quantos tipos de vínculo existem/cadastrados.",
        "purpose": "Lookup e catálogo dos códigos de vínculo previdenciário",
        "use_cases": [
            "Contar tipos de vínculo previdenciário existentes/cadastrados",
            "JOIN com internacoes para obter descrição do vínculo previdenciário",
            "Análise de internações por situação previdenciária",
        ],
        "key_columns": ['"VINCPREV"', '"DESCRICAO"'],
        "value_mappings": {
            '"VINCPREV"': "0=Sem informação, 1=Autônomo, 2=Desempregado, 3=Aposentado, 4=Não segurado, 5=Empregado, 6=Empregador"
        },
        "critical_notes": [
            '"VINCPREV" é chave primária',
            "Para 'quantos tipos de vínculo previdenciário existem', conte a tabela vincprev.",
            "Para 'pacientes/internações com vínculo previdenciário informado/observado', use internacoes.VINCPREV e aplique os filtros de domínio.",
            'JOIN com internacoes: internacoes."VINCPREV" = vincprev."VINCPREV"',
        ],
        "relationships": ['← internacoes("VINCPREV")'],
    },
    "sexo": {
        "title": "Sexo (LOOKUP TABLE)",
        "description": "Tabela de referência com os códigos de sexo. 1=MASCULINO, 3=FEMININO.",
        "purpose": "Lookup do código de sexo",
        "use_cases": ["JOIN com internacoes para obter descrição de sexo"],
        "key_columns": ['"SEXO"', '"DESCRICAO"'],
        "value_mappings": {'"SEXO"': "1=MASCULINO, 3=FEMININO (NUNCA usar 2!)"},
        "critical_notes": [
            '"SEXO" é chave primária',
            'JOIN com internacoes: internacoes."SEXO" = sexo."SEXO"',
            "NUNCA filtrar SEXO = 2",
        ],
        "relationships": ['← internacoes("SEXO")'],
    },
    "raca_cor": {
        "title": "Raça/Cor (LOOKUP TABLE)",
        "description": "Tabela de referência com os códigos de raça/cor dos pacientes.",
        "purpose": "Lookup dos códigos de raça/cor",
        "use_cases": ["JOIN com internacoes para obter descrição de raça/cor"],
        "key_columns": ['"RACA_COR"', '"DESCRICAO"'],
        "value_mappings": {
            '"RACA_COR"': "1=Branca, 2=Preta, 3=Parda, 4=Amarela, 5=Indígena; 99=Sem informação can appear in internacoes but is not in this lookup"
        },
        "critical_notes": [
            '"RACA_COR" é chave primária',
            'JOIN com internacoes: internacoes."RACA_COR" = raca_cor."RACA_COR" keeps identified categories 1..5',
        ],
        "relationships": ['← internacoes("RACA_COR")'],
    },
    "etnia": {
        "title": "Etnia (LOOKUP TABLE)",
        "description": "Tabela de referência com os códigos de etnia dos pacientes (256 etnias indígenas registradas).",
        "purpose": "Lookup dos códigos de etnia",
        "use_cases": ["JOIN com internacoes para obter descrição da etnia"],
        "key_columns": ['"ETNIA"', '"DESCRICAO"'],
        "value_mappings": {
            '"ETNIA"': "Código numérico da etnia — JOIN com internacoes.ETNIA para obter descrição"
        },
        "critical_notes": [
            '"ETNIA" é chave primária',
            'JOIN com internacoes: internacoes."ETNIA" = etnia."ETNIA"',
        ],
        "relationships": ['← internacoes("ETNIA")'],
    },
    "especialidade": {
        "title": "Especialidade do Leito (LOOKUP TABLE)",
        "description": "Tabela de referência com as especialidades dos leitos hospitalares. Inclui especialidades clínicas, cirúrgicas, obstétricas e UTI.",
        "purpose": "Lookup dos códigos de especialidade de leito",
        "use_cases": [
            "JOIN com internacoes para obter descrição da especialidade",
            "Análise de internações por tipo de leito/UTI",
        ],
        "key_columns": ['"ESPEC"', '"DESCRICAO"'],
        "value_mappings": {
            '"ESPEC"': "0=Sem info, 1=Cirúrgico, 2=Obstétrico, 3=Clínico, 4=Crônico, 5=Psiquiatria, 7=Pediátrico, 74-83=Vários tipos de UTI (adulto/infantil/neonatal/queimados), etc."
        },
        "critical_notes": [
            '"ESPEC" é chave primária',
            'JOIN com internacoes: internacoes."ESPEC" = especialidade."ESPEC"',
            'Para filtrar internações em UTI: "ESPEC" BETWEEN 74 AND 83',
        ],
        "relationships": ['← internacoes("ESPEC")'],
    },
    "nacionalidade": {
        "title": "Nacionalidade (LOOKUP TABLE)",
        "description": "Tabela de referência com os códigos e descrições de nacionalidade dos pacientes (333 nacionalidades).",
        "purpose": "Lookup dos códigos de nacionalidade",
        "use_cases": ["JOIN com internacoes para obter descrição da nacionalidade"],
        "key_columns": ['"NACIONAL"', '"DESCRICAO"'],
        "value_mappings": {
            '"NACIONAL"': "Código numérico de nacionalidade — JOIN com internacoes.NACIONAL"
        },
        "critical_notes": [
            '"NACIONAL" é chave primária',
            'JOIN com internacoes: internacoes."NACIONAL" = nacionalidade."NACIONAL"',
        ],
        "relationships": ['← internacoes("NACIONAL")'],
    },
    "contraceptivos": {
        "title": "Métodos Contraceptivos (LOOKUP TABLE)",
        "description": "Tabela de referência com os métodos contraceptivos usados em internações obstétricas. Referenciado por CONTRACEP1 e CONTRACEP2 em internacoes.",
        "purpose": "Lookup dos métodos contraceptivos",
        "use_cases": ["JOIN com internacoes para obter descrição do método contraceptivo"],
        "key_columns": ['"CONTRACEPTIVO"', '"DESCRICAO"'],
        "value_mappings": {
            '"CONTRACEPTIVO"': "0=Sem info, 1=LAM, 6=DIU, 7=Diafragma, 8=Preservativo, 10=Hormônio oral, 11=Hormônio injetável, 12=Coito interrompido..."
        },
        "critical_notes": [
            '"CONTRACEPTIVO" é chave primária',
            'JOIN com internacoes via "CONTRACEP1" ou "CONTRACEP2"',
        ],
        "relationships": ['← internacoes("CONTRACEP1")', '← internacoes("CONTRACEP2")'],
    },
    "tempo": {
        "title": "Dimensão de Datas",
        "description": "Tabela de dimensão temporal com decomposição de datas. Contém todas as datas relevantes com ano, mês, trimestre e dia da semana.",
        "purpose": "Análises temporais e filtragem por período",
        "use_cases": [
            "JOIN com internacoes para filtrar por ano/mês/trimestre",
            "Análises de sazonalidade",
            "Agrupamentos por período",
        ],
        "key_columns": ['"data"', '"ano"', '"mes"', '"trimestre"', '"dia_semana"'],
        "value_mappings": {
            '"data"': "Chave primária (tipo date)",
            '"ano"': "Ano (ex: 2020)",
            '"mes"': "Mês (1-12)",
            '"trimestre"': "Trimestre (1-4)",
            '"dia_semana"': "Dia da semana (0=domingo...6=sábado)",
        },
        "critical_notes": [
            '"data" é chave primária',
            'JOIN com internacoes: tempo."data" = internacoes."DT_INTER" (ou "DT_SAIDA")',
            'Alternativa: usar EXTRACT(YEAR FROM "DT_INTER") direto em internacoes sem JOIN',
        ],
        "relationships": ['← internacoes("DT_INTER")', '← internacoes("DT_SAIDA")'],
    },
    "socioeconomico": {
        "title": "Indicadores Socioeconômicos por Município (PRIMARY FOR MUNICIPALITY SOCIOECONOMIC DATA)",
        "description": "Tabela com indicadores socioeconômicos dos municípios brasileiros por ano. Formato largo: cada linha representa um município em um ano com colunas explícitas para população, PIB per capita, mortalidade infantil, leitos SUS e médicos.",
        "purpose": "Dados socioeconômicos de municípios para análises correlacionadas com internações",
        "use_cases": [
            "População do município: usar QT_POPULACAO",
            "Mortalidade infantil: usar VL_MORT_INFANTIL",
            "Leitos SUS: usar QT_LEITOS_SUS ou VL_LEITOS_SUS_1000",
            "Médicos: usar QT_MEDICOS ou VL_MEDICOS_1000",
            "JOIN com municipios via CO_MUNICIPIO_6D para nome/UF",
        ],
        "key_columns": [
            '"CO_MUNICIPIO_6D"',
            '"NU_ANO"',
            '"QT_POPULACAO"',
            '"VL_PIB_PERCAPITA"',
            '"QT_OBITOS_INFANTIS"',
            '"QT_NASCIDOS_VIVOS"',
            '"VL_MORT_INFANTIL"',
            '"QT_LEITOS_SUS"',
            '"VL_LEITOS_SUS_1000"',
            '"QT_MEDICOS"',
            '"VL_MEDICOS_1000"',
        ],
        "value_mappings": {
            '"CO_MUNICIPIO_6D"': "FK → municipios.CO_MUNICIPIO_6D (PK composta com NU_ANO)",
            '"NU_ANO"': "Ano de referência do indicador",
            '"QT_POPULACAO"': "População municipal",
            '"VL_MORT_INFANTIL"': "Taxa de mortalidade infantil",
            '"QT_LEITOS_SUS"': "Quantidade de leitos SUS",
            '"QT_MEDICOS"': "Quantidade de médicos",
        },
        "critical_notes": [
            'Chave primária composta: ("CO_MUNICIPIO_6D", "NU_ANO")',
            "Não use metrica/valor; essas colunas não existem no schema atual",
            'JOIN com municipios: socioeconomico."CO_MUNICIPIO_6D" = municipios."CO_MUNICIPIO_6D"',
            "Substitui a antiga tabela dado_ibge",
        ],
        "relationships": ['→ municipios("CO_MUNICIPIO_6D")'],
    },
}

# Configuração para PostgreSQL
TOOL_CONFIGURATION = {
    "include_samples": True,
    "include_mappings": True,
    "include_selection_guide": False,
    "max_use_cases_shown": 2,
    "max_sample_queries_shown": 0,
    "max_sample_length": 0,
    "concise_mode": False,
    "postgresql_mode": True,
}

# Guias de seleção para PostgreSQL — banco sihrd5
SELECTION_GUIDES = {
    "concise_guide": """
POSTGRESQL TABLE SELECTION GUIDE (banco sihrd5):
• internacoes = Tabela principal (pacientes, internações, óbitos, VDRL, obstétrico, custos)
• internacao_procedimento = Junction table internacoes ↔ procedimentos (N:M)
• cid = Códigos CID-10 e descrições (anteriormente chamada cid10)
• hospital = Estabelecimentos de saúde (CNES)
• procedimentos = Códigos e nomes de procedimentos
• municipios = Municípios brasileiros (CO_MUNICIPIO_6D como FK)
• socioeconomico = Indicadores socioeconômicos por município/ano (formato largo)
• tempo = Dimensão de datas
• Lookups: sexo, raca_cor, etnia, especialidade, instrucao, vincprev, contraceptivos, nacionalidade
• Always use "COLUMN_NAME" (double quotes) for PostgreSQL columns
""",
    "full_guide": """
COMPREHENSIVE POSTGRESQL TABLE RELATIONSHIPS (banco sihrd5):

FLUXO PRINCIPAL DE DADOS:
internacoes (tabela central, 18.5M registros)
├── hospital (via "CNES") — Estabelecimento de saúde
├── cid (via "DIAG_PRINC", "DIAG_SECUN", "CID_MORTE") — Diagnósticos CID-10
├── municipios (via "MUNIC_RES" = CO_MUNICIPIO_6D) — Município de residência
├── sexo (via "SEXO") — Lookup de sexo
├── raca_cor (via "RACA_COR") — Lookup de raça/cor
├── etnia (via "ETNIA") — Lookup de etnia
├── nacionalidade (via "NACIONAL") — Lookup de nacionalidade
├── instrucao (via "INSTRU") — Lookup de escolaridade
├── vincprev (via "VINCPREV") — Lookup de vínculo previdenciário
├── especialidade (via "ESPEC") — Lookup de especialidade do leito
├── contraceptivos (via "CONTRACEP1", "CONTRACEP2") — Lookup de contraceptivos
└── internacao_procedimento (via "N_AIH") → procedimentos (via "PROC_REA")

hospital → municipios (via "MUNIC_MOV" = CO_MUNICIPIO_6D)
municipios ← socioeconomico (via CO_MUNICIPIO_6D)

REGRAS CRÍTICAS DE SQL POSTGRESQL:
- Nomes de colunas DEVEM usar aspas duplas: "SEXO", "IDADE", "DESCRICAO"
- MORTE É BOOLEAN: WHERE "MORTE" = true (não existe tabela mortes separada)
- IND_VDRL É BOOLEAN: WHERE "IND_VDRL" = true
- SEXO: 1=Masculino, 3=Feminino (NUNCA usar 2!)
- DIAS_PERM substitui QT_DIARIAS do banco anterior
- Para procedimentos: internacoes → internacao_procedimento → procedimentos (dois JOINs necessários)
- Tabela cid (não cid10)
- Socioeconomico: formato largo por município/ano; usar colunas explícitas como "QT_POPULACAO" e "VL_MORT_INFANTIL"
""",
}
