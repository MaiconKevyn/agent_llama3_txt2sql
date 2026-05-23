# PostgreSQL-specific templates for all 15 SIH-RS tables
TABLE_TEMPLATES = {
    "internacoes": """
         INTERNACOES TABLE RULES - MAIN HOSPITALIZATION DATA:
        
        MANDATORY VALUE MAPPINGS (NEVER MAKE MISTAKES):
        - For questions about MEN/HOMENS/MASCULINO: ALWAYS use "SEXO" = 1
        - For questions about WOMEN/MULHERES/FEMININO: ALWAYS use "SEXO" = 3
        - NEVER use "SEXO" = 2 (invalid value)
        - Age queries: Use "IDADE" column (numeric, in years)
        - Financial queries: "VAL_TOT", "VAL_SH", "VAL_SP" (total, hospital, professional values)
        - Duration queries: "DIAS_PERM" (days of stay), "QT_DIARIAS" (daily charges)

        CRITICAL: AGE GROUPS (FAIXA ETÁRIA) vs TIME PERIODS:
        - "faixa etária" = AGE GROUPS of patients (use "IDADE" column with CASE WHEN)
        - "ano" / "período" = TIME PERIODS (use "DT_INTER" or "DT_SAIDA" with EXTRACT)
        - NEVER confuse patient age with calendar years!
        - Common age groups: 0-17 (children), 18-39 (young adults), 40-59 (middle-aged), 60+ (elderly)

        CRITICAL: IDADE (age in years) vs NASC (birth date) - NEVER CONFUSE:
        ❌ WRONG: "IDADE" < 1950 (comparing age in years with calendar year - semantically incorrect!)
        ✅ CORRECT: "NASC" < '1950-01-01' (comparing birth date with date)

        RULES:
        - "IDADE" = patient's age in YEARS (numeric: 0, 1, 30, 45, 70, etc.)
          Use for: "idade média", "pacientes com X anos", "faixa etária", age comparisons
        - "NASC" = patient's BIRTH DATE (date format: '1945-03-15')
          Use for: "nascidos antes de X", "data de nascimento", birth year queries

        EXAMPLES:
        - "Quantos pacientes têm mais de 60 anos?" → WHERE "IDADE" > 60
        - "Quantos nasceram antes de 1950?" → WHERE "NASC" < '1950-01-01'
        - "Pacientes nascidos em 1980" → WHERE EXTRACT(YEAR FROM "NASC") = 1980
        - "Idade média dos pacientes" → AVG("IDADE")

        CRITICAL: NEVER ADD FILTERS THAT WERE NOT REQUESTED IN THE QUESTION:
        - If the question doesn't mention age, DON'T add "WHERE IDADE BETWEEN X AND Y"
        - If the question doesn't mention gender, DON'T add "WHERE SEXO = X"
        - If the question doesn't mention time period, DON'T add "WHERE EXTRACT(YEAR...)"
        - Only add filters that are EXPLICITLY mentioned or clearly implied in the question

        EXAMPLES:
        ❌ WRONG: Question: "Quais procedimentos têm maior taxa de mortalidade?"
                 Query: ...WHERE "IDADE" BETWEEN 30 AND 45... (age filter NOT in question!)
        ✅ CORRECT: Question: "Quais procedimentos têm maior taxa de mortalidade?"
                   Query: ...WHERE "PROC_REA" IS NOT NULL (no unnecessary filters)

        CRITICAL: ONLY JOIN TABLES WHEN NECESSARY FOR THE QUESTION:
        - DON'T add JOINs just because tables exist
        - ONLY JOIN when you need data from another table to answer the question

        EXAMPLES:
        ❌ WRONG: Question: "Quantos pacientes nasceram antes de 1950?"
                 Query: FROM internacoes i JOIN cid10 c ON... (cid10 not needed!)
        ✅ CORRECT: Question: "Quantos pacientes nasceram antes de 1950?"
                   Query: FROM internacoes WHERE "NASC" < '1950-01-01' (no JOIN needed)

        ❌ WRONG: Question: "Qual a taxa de mortalidade geral?"
                 Query: FROM internacoes i JOIN hospital h ON... (hospital not needed!)
        ✅ CORRECT: Question: "Qual a taxa de mortalidade geral?"
                   Query: FROM internacoes i LEFT JOIN mortes m ON... (only needed tables)

        POSTGRESQL COLUMN QUOTING:
        - ALL columns MUST use double quotes: "SEXO", "IDADE", "VAL_TOT", "N_AIH"
        - Date columns: "DT_INTER" (admission), "DT_SAIDA" (discharge), "NASC" (birth)
        - Municipality: "MUNIC_RES" (residence), "MUNIC_MOV" (movement)
        - Diagnosis: "DIAG_PRINC" (primary), "DIAG_SECUN" (secondary)
        
        CRITICAL JOIN RELATIONSHIPS:
        - → hospital: internacoes."CNES" = hospital."CNES"
        - → cid10: internacoes."DIAG_PRINC" = cid10."CID"
        - → mortes: internacoes."N_AIH" = mortes."N_AIH"
        - → uti_detalhes: internacoes."N_AIH" = uti_detalhes."N_AIH"

        CRITICAL DISEASE LOOKUP RULE - ALWAYS JOIN WITH CID10 TABLE:
        - For ANY query about specific diseases, conditions, or diagnosis names, ALWAYS JOIN with the cid10 table
        - NEVER search for disease names directly in diagnosis code fields (DIAG_PRINC, DIAG_SECUN)
        - ALWAYS use the cid10 table to get proper disease descriptions and search there
        - Pattern: JOIN cid10 c ON internacoes."DIAG_PRINC" = c."CID" WHERE c."CD_DESCRICAO" ILIKE '%[disease]%'

        DIABETES EXAMPLE (CRITICAL):
        - WRONG: WHERE "DIAG_PRINC" ILIKE '%diabetes%' (searches code field)
        - CORRECT: JOIN cid10 c ON "DIAG_PRINC" = c."CID" WHERE c."CD_DESCRICAO" ILIKE '%diabetes%' (searches description)

        DIAGNOSIS DESCRIPTION RULES (CID LOOKUPS):
        - When a query asks for diagnosis names, rankings, "diagnósticos mais comuns", or any output involving disease names,
          ALWAYS JOIN with the cid10 table on internacoes."DIAG_PRINC" = cid10."CID"
        - SELECT both the code cid10."CID" and the description cid10."CD_DESCRICAO" in the result set, together with the metric (e.g., COUNT(*))
        - Use ILIKE for case-insensitive description searches; use proper GROUP BY over both code and description
        - Seasonal filter (Southern Hemisphere): Inverno (winter) months are 6, 7, and 8 (June, July, August)
        
        EXACT QUERY EXAMPLES:
        -- Men count
        SELECT COUNT(*) FROM internacoes WHERE "SEXO" = 1;
        
        -- Women average age
        SELECT AVG("IDADE") FROM internacoes WHERE "SEXO" = 3 AND "IDADE" IS NOT NULL;
        
        -- Total financial values
        SELECT SUM("VAL_TOT") FROM internacoes WHERE "VAL_TOT" IS NOT NULL;
        
        -- Long stays (>30 days)
        SELECT COUNT(*) FROM internacoes WHERE "DIAS_PERM" > 30;
        
        -- Admissions by year
        SELECT EXTRACT(YEAR FROM "DT_INTER") as year, COUNT(*) 
        FROM internacoes 
        WHERE "DT_INTER" IS NOT NULL 
        GROUP BY EXTRACT(YEAR FROM "DT_INTER");

        -- People with diabetes (CORRECT APPROACH):
        SELECT COUNT(*) FROM internacoes i
        JOIN cid10 c ON i."DIAG_PRINC" = c."CID"
        WHERE c."CD_DESCRICAO" ILIKE '%diabetes%';

        -- Top 3 most common diagnoses in winter with descriptions
        SELECT c."CID", c."CD_DESCRICAO", COUNT(*) AS total
        FROM internacoes i
        JOIN cid10 c ON i."DIAG_PRINC" = c."CID"
        WHERE EXTRACT(MONTH FROM i."DT_INTER") IN (6,7,8)
        GROUP BY c."CID", c."CD_DESCRICAO"
        ORDER BY total DESC
        LIMIT 3;

        -- Average ICU stay time (days) using hospital daily charges (QT_DIARIAS)
        -- Question: "Qual o tempo médio de permanência em UTI?"
        -- Use internacoes only; uti_detalhes does not provide days length
        SELECT AVG("QT_DIARIAS") AS tempo_medio_uti
        FROM internacoes
        WHERE "QT_DIARIAS" > 0;

        -- AGE GROUPS (FAIXA ETÁRIA) - CRITICAL EXAMPLE:
        -- Count hospitalizations by age group (NOT by year!)
        SELECT
          CASE
            WHEN "IDADE" < 18 THEN '0-17 anos'
            WHEN "IDADE" < 40 THEN '18-39 anos'
            WHEN "IDADE" < 60 THEN '40-59 anos'
            ELSE '60+ anos'
          END AS faixa_etaria,
          COUNT(*) AS total
        FROM internacoes
        WHERE "IDADE" IS NOT NULL
        GROUP BY faixa_etaria
        ORDER BY faixa_etaria;

        -- MORTALITY RATE by AGE GROUP (FAIXA ETÁRIA) - CRITICAL EXAMPLE:
        -- Question: "Qual a taxa de mortalidade por faixa etária?"
        SELECT
          CASE
            WHEN i."IDADE" < 18 THEN '0-17 anos'
            WHEN i."IDADE" < 40 THEN '18-39 anos'
            WHEN i."IDADE" < 60 THEN '40-59 anos'
            ELSE '60+ anos'
          END AS faixa_etaria,
          COUNT(DISTINCT i."N_AIH") AS total_internacoes,
          COUNT(DISTINCT m."N_AIH") AS total_mortes,
          ROUND(COUNT(DISTINCT m."N_AIH")::numeric / COUNT(DISTINCT i."N_AIH") * 100, 2) AS taxa_mortalidade
        FROM internacoes i
        LEFT JOIN mortes m ON i."N_AIH" = m."N_AIH"
        WHERE i."IDADE" IS NOT NULL
        GROUP BY faixa_etaria
        ORDER BY faixa_etaria;

        CRITICAL: MORTALITY RATE CALCULATION - MOST COMMON MISTAKES:

        For ANY query asking "taxa de mortalidade" (mortality rate), you MUST follow this structure:

        ❌ WRONG APPROACH (Returns 100% - only counts deaths):
        SELECT COUNT(mo."N_AIH") * 100 / COUNT(*)
        FROM mortes mo                              -- WRONG: Starting from deaths table
        JOIN internacoes i ON mo."N_AIH" = i."N_AIH"
        WHERE i."IDADE" BETWEEN 30 AND 45;
        Problem: Only processes records that have deaths (INNER JOIN), returns 100%!

        ✅ CORRECT APPROACH (Returns actual rate like 1.87%):
        -- Question: "Qual a taxa de mortalidade para faixa etária 30-45?"
        SELECT '30-45 anos' AS faixa_etaria,
          COUNT(DISTINCT i."N_AIH") AS total_internacoes,    -- Denominator: ALL hospitalizations
          COUNT(DISTINCT m."N_AIH") AS total_mortes,         -- Numerator: Deaths only
          ROUND(COUNT(DISTINCT m."N_AIH")::numeric / COUNT(DISTINCT i."N_AIH") * 100, 2) AS taxa_mortalidade
        FROM internacoes i                           -- CORRECT: Start from hospitalizations table
        LEFT JOIN mortes m ON i."N_AIH" = m."N_AIH" -- CRITICAL: LEFT JOIN to keep ALL hospitalizations
        WHERE i."IDADE" BETWEEN 30 AND 45;
        -- NO GROUP BY needed (single age range)
        -- NO ORDER BY needed (single result)
        -- Result: 1 row with 1.87% (37,626 deaths / 2,017,361 hospitalizations)

        CRITICAL RULES FOR MORTALITY RATES:
        1. ALWAYS use internacoes as FROM table (not mortes)
        2. ALWAYS use LEFT JOIN with mortes (not INNER JOIN)
        3. Denominator = COUNT(DISTINCT i."N_AIH") - all hospitalizations
        4. Numerator = COUNT(DISTINCT m."N_AIH") - only deaths (will be NULL for survivors)
        5. Include descriptive columns: category, total_internacoes, total_mortes, taxa
        6. Use DISTINCT to avoid duplicates from potential multiple joins

        JOIN TYPE SELECTION GUIDE:
        - LEFT JOIN: When you want ALL records from main table (e.g., all hospitalizations including survivors)
        - INNER JOIN: Only when BOTH tables must have matching records (rare for mortality queries)

        For "taxa de mortalidade" queries:
        - Main table (FROM): internacoes (all cases)
        - Secondary table (LEFT JOIN): mortes (subset with deaths)
        - This gives you: deaths/total ratio

        GENERIC PATTERN FOR MORTALITY RATE BY CATEGORY (procedure, municipality, hospital, etc.):
        -- Question: "Quais [categorias] têm maior taxa de mortalidade?"
        -- Replace [category_table] and [category_key] with appropriate values

        SELECT
          i."[CATEGORY_KEY]" AS categoria,  -- The category column (e.g., "PROC_REA", "MUNIC_RES", "CNES")
          ref."[DESCRIPTION]" AS descricao,  -- Optional: description from reference table
          COUNT(DISTINCT i."N_AIH") AS total_internacoes,
          COUNT(DISTINCT m."N_AIH") AS total_mortes,
          ROUND(COUNT(DISTINCT m."N_AIH")::numeric / COUNT(DISTINCT i."N_AIH") * 100, 2) AS taxa_mortalidade
        FROM internacoes i
        LEFT JOIN mortes m ON i."N_AIH" = m."N_AIH"
        LEFT JOIN [reference_table] ref ON i."[CATEGORY_KEY]" = ref."[KEY]"  -- Optional: for descriptions
        WHERE i."[CATEGORY_KEY]" IS NOT NULL
        GROUP BY i."[CATEGORY_KEY]", ref."[DESCRIPTION]"  -- Group by both code and description
        HAVING COUNT(DISTINCT m."N_AIH") > 0  -- Optional: only categories with at least 1 death
        ORDER BY taxa_mortalidade DESC
        LIMIT [N];

        EXAMPLES BY CATEGORY:

        -- Mortality rate by PROCEDURE (procedimentos)
        SELECT
          i."PROC_REA" AS procedimento,
          p."NOME_PROC" AS nome_procedimento,
          COUNT(DISTINCT i."N_AIH") AS total_internacoes,
          COUNT(DISTINCT m."N_AIH") AS total_mortes,
          ROUND(COUNT(DISTINCT m."N_AIH")::numeric / COUNT(DISTINCT i."N_AIH") * 100, 2) AS taxa_mortalidade
        FROM internacoes i
        LEFT JOIN mortes m ON i."N_AIH" = m."N_AIH"
        LEFT JOIN procedimentos p ON i."PROC_REA" = p."PROC_REA"
        WHERE i."PROC_REA" IS NOT NULL
        GROUP BY i."PROC_REA", p."NOME_PROC"
        HAVING COUNT(DISTINCT m."N_AIH") > 0
        ORDER BY taxa_mortalidade DESC
        LIMIT 5;

        -- Mortality rate by HOSPITAL (hospital)
        SELECT
          i."CNES" AS hospital,
          h."NATUREZA" AS tipo_hospital,
          COUNT(DISTINCT i."N_AIH") AS total_internacoes,
          COUNT(DISTINCT m."N_AIH") AS total_mortes,
          ROUND(COUNT(DISTINCT m."N_AIH")::numeric / COUNT(DISTINCT i."N_AIH") * 100, 2) AS taxa_mortalidade
        FROM internacoes i
        LEFT JOIN mortes m ON i."N_AIH" = m."N_AIH"
        LEFT JOIN hospital h ON i."CNES" = h."CNES"
        WHERE i."CNES" IS NOT NULL
        GROUP BY i."CNES", h."NATUREZA"
        ORDER BY taxa_mortalidade DESC
        LIMIT 10;

        -- Mortality rate by MUNICIPALITY (municipios)
        SELECT
          i."MUNIC_RES" AS municipio_codigo,
          mu."nome" AS municipio_nome,
          COUNT(DISTINCT i."N_AIH") AS total_internacoes,
          COUNT(DISTINCT m."N_AIH") AS total_mortes,
          ROUND(COUNT(DISTINCT m."N_AIH")::numeric / COUNT(DISTINCT i."N_AIH") * 100, 2) AS taxa_mortalidade
        FROM internacoes i
        LEFT JOIN mortes m ON i."N_AIH" = m."N_AIH"
        LEFT JOIN municipios mu ON i."MUNIC_RES" = mu."codigo_6d"
        WHERE i."MUNIC_RES" IS NOT NULL
        GROUP BY i."MUNIC_RES", mu."nome"
        ORDER BY taxa_mortalidade DESC
        LIMIT 10;
""",
    "mortes": """
        MORTES TABLE RULES - DEATH RECORDS DURING HOSPITALIZATION:

        MANDATORY USAGE RULES:
        - This table contains ONLY death records (subset of hospitalizations)
        - "N_AIH" links to internacoes table
        - "CID_MORTE" contains death cause (ICD-10 code)

        CRITICAL: WHEN TO USE AS MAIN TABLE vs JOIN TABLE:

        ❌ USE AS MAIN TABLE (FROM mortes) - ONLY when:
        - Counting ONLY deaths: "Quantas mortes?" "Quantos óbitos?"
        - Death cause analysis: "Principais causas de morte"
        - Death demographics: "Mortes por sexo/idade" (deaths only, not rates)

        ✅ USE AS SECONDARY TABLE (LEFT JOIN mortes) - ALWAYS when:
        - Calculating RATES: "taxa de mortalidade" (needs total hospitalizations as denominator)
        - Comparing deaths vs survivors: "proporção de óbitos"
        - ANY query mentioning "taxa" or "proporção"

        Example decision tree:
        - "Quantas mortes cardiovasculares?" → FROM mortes (counting deaths only)
        - "Qual a taxa de mortalidade cardiovascular?" → FROM internacoes LEFT JOIN mortes (rate calculation)

        POSTGRESQL COLUMN QUOTING:
        - "N_AIH" (hospitalization ID), "CID_MORTE" (death cause code)

        CRITICAL DISEASE LOOKUP RULE - ALWAYS JOIN WITH CID10 TABLE:
        - For ANY query about specific diseases, conditions, or diagnosis names, ALWAYS JOIN with the cid10 table
        - NEVER search for disease names directly in diagnosis code fields (DIAG_PRINC, DIAG_SECUN, CID_MORTE)
        - ALWAYS use the cid10 table to get proper disease descriptions and search there
        - Pattern: JOIN cid10 c ON [table]."[CID_FIELD]" = c."CID" WHERE c."CD_DESCRICAO" ILIKE '%[disease]%'

        DIABETES EXAMPLE (CRITICAL):
        - WRONG: WHERE i."DIAG_PRINC" ILIKE '%diabetes%' (searches code field)
        - CORRECT: JOIN cid10 c ON i."DIAG_PRINC" = c."CID" WHERE c."CD_DESCRICAO" ILIKE '%diabetes%' (searches description)

        MEDICAL CID-10 APPROACH (USE cid10 TABLE FOR DISEASE CLASSIFICATION):
        - DIABETES: JOIN cid10 c ON i."DIAG_PRINC" = c."CID" WHERE c."CD_DESCRICAO" ILIKE '%diabetes%'
        - CARDIOVASCULAR DISEASES: Use flexible medical search combining CID codes AND description patterns
          INTELLIGENT APPROACH: Combine I00-I99 codes with medical terms you know are related
          EXAMPLE SQL: JOIN cid10 c ON i."DIAG_PRINC" = c."CID" WHERE (c."CID" LIKE 'I%' OR c."CD_DESCRICAO" ILIKE ANY(ARRAY['%card%', '%miocardio%', '%vascular%', '%arterial%', '%circulatorio%']))
          NEVER use 'C%' for cardiovascular - that's cancer!
        - CANCER/NEOPLASM DISEASES: Use flexible search for cancer-related conditions
          INTELLIGENT APPROACH: JOIN cid10 c ON i."DIAG_PRINC" = c."CID" WHERE (c."CID" LIKE 'C%' OR c."CID" LIKE 'D0%' OR c."CID" LIKE 'D1%' OR c."CID" LIKE 'D2%' OR c."CID" LIKE 'D3%' OR c."CID" LIKE 'D4%'
                                       OR c."CD_DESCRICAO" ILIKE ANY(ARRAY['%cancer%', '%tumor%', '%neoplasia%', '%carcinoma%', '%sarcoma%']))
        - RESPIRATORY DISEASES: Use flexible search for lung/breathing conditions
          INTELLIGENT APPROACH: JOIN cid10 c ON i."DIAG_PRINC" = c."CID" WHERE (c."CID" LIKE 'J%' OR c."CD_DESCRICAO" ILIKE ANY(ARRAY['%respir%', '%pulm%', '%pneum%', '%bronqu%', '%asma%']))
        - INFECTIOUS DISEASES: Use flexible search for infections
          INTELLIGENT APPROACH: JOIN cid10 c ON i."DIAG_PRINC" = c."CID" WHERE ((c."CID" LIKE 'A%' OR c."CID" LIKE 'B%') OR c."CD_DESCRICAO" ILIKE ANY(ARRAY['%infec%', '%virus%', '%bacter%', '%covid%']))
        - EXTERNAL CAUSES: "CID_MORTE" LIKE 'V%' OR "CID_MORTE" LIKE 'W%' OR "CID_MORTE" LIKE 'X%' OR "CID_MORTE" LIKE 'Y%'
          Keywords: acidente, violência, suicídio, trauma

        EXACT QUERY EXAMPLES:
        -- Total deaths
        SELECT COUNT(*) FROM mortes;

        -- DIABETES DEATHS (CORRECT APPROACH):
        SELECT COUNT(*) FROM mortes mo
        JOIN internacoes i ON mo."N_AIH" = i."N_AIH"
        JOIN cid10 c ON i."DIAG_PRINC" = c."CID"
        WHERE c."CD_DESCRICAO" ILIKE '%diabetes%';

        -- DIABETES DEATHS (ALTERNATIVE WITH DEATH CAUSE):
        SELECT COUNT(*) FROM mortes mo
        JOIN cid10 c ON mo."CID_MORTE" = c."CID"
        WHERE c."CD_DESCRICAO" ILIKE '%diabetes%';

        -- CARDIOVASCULAR DEATHS (USING DEATH CAUSE DESCRIPTION VIA CID10)
        SELECT COUNT(*) AS mortes_cardiovasculares
        FROM mortes mo
        JOIN cid10 c ON mo."CID_MORTE" = c."CID"
        WHERE c."CD_DESCRICAO" ILIKE ANY(ARRAY['%cardi%','%cardí%','%miocard%','%vascular%','%arterial%','%circulat%']);

        -- CARDIOVASCULAR (ALTERNATIVE USING DIAGNOSIS IN ADMISSIONS - NOT DEATH CAUSE)
        SELECT COUNT(*)
        FROM internacoes i
        JOIN cid10 c ON i."DIAG_PRINC" = c."CID"
        WHERE (c."CD_DESCRICAO" ILIKE ANY(ARRAY['%cardi%','%cardí%','%miocard%','%vascular%','%arterial%','%circulat%']));

        -- Deaths with hospitalization data
        SELECT COUNT(DISTINCT m."N_AIH")
        FROM mortes m
        JOIN internacoes i ON m."N_AIH" = i."N_AIH";

        -- Death causes ranking WITH DESCRIPTIONS
        SELECT c."CID", c."CD_DESCRICAO", COUNT(*) as total_deaths
        FROM mortes m
        JOIN cid10 c ON m."CID_MORTE" = c."CID"
        WHERE m."CID_MORTE" IS NOT NULL
        GROUP BY c."CID", c."CD_DESCRICAO"
        ORDER BY total_deaths DESC
        LIMIT 10;
""",
    "cid10": """
         CID10 TABLE RULES - ICD-10 DISEASE CODES (REFERENCE TABLE):
        
        MANDATORY USAGE RULES:
        - Use for: Disease code lookups, descriptions, JOIN operations
        - For counting available codes: SELECT COUNT(*) FROM cid10
        - For finding descriptions: JOIN with other tables on CID codes
        - "CID" = ICD-10 code, "CD_DESCRICAO" = disease description
        
        POSTGRESQL COLUMN QUOTING:
        - "CID" (ICD-10 code), "CD_DESCRICAO" (description)
        
        CRITICAL SEARCH PATTERNS:
        - Description search: WHERE "CD_DESCRICAO" ILIKE '%pneumonia%'
               
        EXACT QUERY EXAMPLES:
        -- Total ICD codes available
        SELECT COUNT(*) FROM cid10;
        
        -- Find specific code description
        SELECT "CD_DESCRICAO" FROM cid10 WHERE "CID" = 'A15';
        
        -- Search diabetes codes
        SELECT "CID", "CD_DESCRICAO" 
        FROM cid10 
        WHERE "CID" LIKE 'E1%' AND "CID" >= 'E10' AND "CID" <= 'E14';
        
        -- Cardiovascular-related codes by description
        SELECT "CID", "CD_DESCRICAO"
        FROM cid10
        WHERE "CD_DESCRICAO" ILIKE ANY(ARRAY['%cardi%','%cardí%','%miocard%','%vascular%','%arterial%','%circulat%']);
    
""",
    "hospital": """
         HOSPITAL TABLE RULES - HEALTHCARE FACILITIES:

        MANDATORY USAGE RULES:
        - Use for: Hospital counts, facility analysis, public/private classification
        - "CNES" = National Health Facility Registry code (primary key)
        - "NATUREZA" = Facility nature (public/private classification)

        POSTGRESQL COLUMN QUOTING:
        - "CNES" (facility code), "NATUREZA" (nature), "GESTAO" (management), "NAT_JUR" (legal nature)

        CRITICAL VALUE MAPPINGS:
        - Public hospitals: "NATUREZA" containing 'PUBLIC' or 'PUBLICA'
        - Private hospitals: "NATUREZA" containing 'PRIVAD'
        - Use ILIKE for case-insensitive searches

        
        EXACT QUERY EXAMPLES:
        -- Total hospitals
        SELECT COUNT(*) FROM hospital;
        
        -- Public hospitals count
        SELECT COUNT(*) FROM hospital 
        WHERE "NATUREZA" ILIKE '%public%' OR "NATUREZA" ILIKE '%publica%';
        
        -- Hospitals with admissions
        SELECT COUNT(DISTINCT h."CNES") 
        FROM hospital h 
        JOIN internacoes i ON h."CNES" = i."CNES";
        
        -- Hospital activity volume
        SELECT h."CNES", COUNT(i."N_AIH") as admissions
        FROM hospital h 
        JOIN internacoes i ON h."CNES" = i."CNES" 
        GROUP BY h."CNES" 
        HAVING COUNT(i."N_AIH") > 1000;
""",
    "municipios": """
        MUNICIPIOS TABLE RULES - BRAZILIAN MUNICIPALITIES:
        
        MANDATORY USAGE RULES:
        - Use for: Geographic queries, municipality names, coordinates
        - "codigo_6d" = 6-digit code (primary key)
        - "codigo_ibge" = IBGE code (7 digits, unique)
        - "nome" = municipality name, "estado" = state abbreviation
        
        POSTGRESQL COLUMN QUOTING:
        - "codigo_6d", "codigo_ibge", "nome", "estado", "latitude", "longitude"
        
        CRITICAL RELATIONSHIPS:
        - → dado_ibge: municipios."codigo_ibge" = dado_ibge."codigo_municipio_completo"
        - → internacoes: internacoes."MUNIC_RES" = municipios.codigo_6d (6-digit municipality residence code)

        MUNICIPALITY CODE MAPPING:
        - 6-digit codes (codigo_6d): Used in internacoes table as "MUNIC_RES"
        - 7-digit codes (codigo_ibge): Used in dado_ibge table for demographic data
        - To connect hospitals → municipalities → demographics:
          hospital → internacoes → municipios → dado_ibge
        
        EXACT QUERY EXAMPLES:
        -- Total municipalities
        SELECT COUNT(*) FROM municipios;
        
        -- RS state municipalities
        SELECT COUNT(*) FROM municipios WHERE "estado" = 'RS';
        
        -- Porto Alegre coordinates
        SELECT "latitude", "longitude" FROM municipios WHERE "nome" = 'Porto Alegre';
        
        -- States with most municipalities
        SELECT "estado", COUNT(*) as total_cities
        FROM municipios 
        GROUP BY "estado" 
        ORDER BY total_cities DESC;
""",
    "dado_ibge": """
         DADO_IBGE TABLE RULES - MUNICIPALITY SOCIOECONOMIC DATA:
        
        MANDATORY USAGE RULES:
        - PRIMARY TABLE for municipality demographic and economic analysis
        - Use for: Population, salary, education (IDEB), mortality rates
        - "codigo_municipio_completo" = Complete municipality code (primary key)
        - "nome_municipio" = Municipality name
        
        POSTGRESQL COLUMN QUOTING:
        - "codigo_municipio_completo", "nome_municipio", "populacao", "densidade_demografica"
        - "salario_medio", "pessoal_ocupado", "mortalidade_infantil"
        - "ideb_anos_iniciais_ensino_fundamental", "ideb_anos_finais_ensino_fundamental"
        
        CRITICAL DATA FIELDS:
        - "populacao" = Population in thousands
        - "salario_medio" = Average salary
        - "mortalidade_infantil" = Infant mortality rate
        - "densidade_demografica" = Demographic density
        
        EXACT QUERY EXAMPLES:
        -- Highest population municipality
        SELECT "nome_municipio", "populacao" 
        FROM dado_ibge 
        WHERE "populacao" IS NOT NULL 
        ORDER BY "populacao" DESC LIMIT 1;
        
        -- Average infant mortality in Brazil
        SELECT AVG("mortalidade_infantil") 
        FROM dado_ibge 
        WHERE "mortalidade_infantil" IS NOT NULL;
        
        -- Cities with >100k population
        SELECT COUNT(*) FROM dado_ibge WHERE "populacao" > 100;
        
        -- Best education scores
        SELECT "nome_municipio", "ideb_anos_iniciais_ensino_fundamental"
        FROM dado_ibge 
        WHERE "ideb_anos_iniciais_ensino_fundamental" IS NOT NULL
        ORDER BY "ideb_anos_iniciais_ensino_fundamental" DESC LIMIT 10;
""",
    "uti_detalhes": """
         UTI_DETALHES TABLE RULES - INTENSIVE CARE UNIT DATA:
        
        MANDATORY USAGE RULES:
        - PRIMARY TABLE for UTI/ICU statistics and costs (NOT for days of stay)
        - Use for: "UTI", "ICU", "terapia intensiva", UTI costs, ICU markers/flags
        - Links to internacoes via "N_AIH"
        
        POSTGRESQL COLUMN QUOTING:
        - "N_AIH", "UTI_MES_TO", "MARCA_UTI", "UTI_INT_TO", "VAL_UTI"
        
        CRITICAL DATA FIELDS:
        - "VAL_UTI" = UTI cost/value
        - "MARCA_UTI" = UTI marker/type
        - Duration in days (permanência) should be computed from internacoes."QT_DIARIAS" (not from this table)
        
        EXACT QUERY EXAMPLES:
        -- Total UTI records
        SELECT COUNT(*) FROM uti_detalhes;
        
        -- Average UTI cost
        SELECT AVG("VAL_UTI") FROM uti_detalhes WHERE "VAL_UTI" IS NOT NULL;
        
        -- Do NOT use this table to compute UTI stay in days; use internacoes."QT_DIARIAS"
        
        -- UTI cost by patient gender
        SELECT i."SEXO", AVG(u."VAL_UTI") as avg_uti_cost
        FROM uti_detalhes u 
        JOIN internacoes i ON u."N_AIH" = i."N_AIH"
        WHERE u."VAL_UTI" IS NOT NULL AND i."SEXO" IN (1,3)
        GROUP BY i."SEXO";
        
        -- UTI cases that resulted in death
        SELECT COUNT(DISTINCT u."N_AIH") 
        FROM uti_detalhes u 
        JOIN mortes m ON u."N_AIH" = m."N_AIH";
""",
    "procedimentos": """
         PROCEDIMENTOS TABLE RULES - MEDICAL PROCEDURES REFERENCE:

        MANDATORY USAGE RULES:
        - Reference table for procedure codes and descriptions
        - Use for: Procedure counts, procedure names, procedure analysis
        - Links to internacoes via "PROC_REA"

        POSTGRESQL COLUMN QUOTING (CRITICAL):
        - ALWAYS use double quotes: "PROC_REA", "NOME_PROC"
        - NEVER use: PROC_REA or NOME_PROC (will fail with "column does not exist")

        KEY COLUMNS:
        - "PROC_REA" = Procedure code (primary key, links to internacoes)
        - "NOME_PROC" = Procedure description/name (text field for searches)

        CRITICAL SEARCH PATTERNS:
        - Procedure name search: WHERE "NOME_PROC" ILIKE '%cirurgia%'
        - Case-insensitive search: ALWAYS use ILIKE (not LIKE)
        - Specific procedure: WHERE "PROC_REA" = '0404010032'

        EXACT QUERY EXAMPLES:
        -- Total procedures in reference table
        SELECT COUNT(*) AS total_procedimentos FROM procedimentos;

        -- Count procedures containing "CIRURGIA" (CRITICAL EXAMPLE)
        SELECT COUNT(*) AS procedimentos_cirurgia
        FROM procedimentos
        WHERE "NOME_PROC" ILIKE '%CIRURGIA%';

        -- List surgery procedures with names
        SELECT "PROC_REA", "NOME_PROC"
        FROM procedimentos
        WHERE "NOME_PROC" ILIKE '%cirurgia%'
        LIMIT 10;

        -- Most common procedures performed (from internacoes)
        -- Based on procedure NAMES (join for readability)
        SELECT p."NOME_PROC", COUNT(*) AS frequency
        FROM internacoes i
        JOIN procedimentos p ON i."PROC_REA" = p."PROC_REA"
        WHERE i."PROC_REA" IS NOT NULL
        GROUP BY p."NOME_PROC"
        ORDER BY frequency DESC
        LIMIT 10;

        -- GENERAL RULE (frequency by categorical code):
        -- SELECT code_col, COUNT(*) AS total
        -- FROM <table>
        -- WHERE code_col IS NOT NULL
        -- GROUP BY code_col
        -- ORDER BY total DESC
        -- LIMIT N;

        -- Procedure with highest average cost
        SELECT p."NOME_PROC", AVG(i."VAL_TOT") as avg_cost
        FROM internacoes i
        JOIN procedimentos p ON i."PROC_REA" = p."PROC_REA"
        WHERE i."VAL_TOT" IS NOT NULL
        GROUP BY p."NOME_PROC"
        ORDER BY avg_cost DESC LIMIT 5;

        COMMON MISTAKES TO AVOID:
        - ❌ WHERE NOME_PROC LIKE '%cirurgia%' (missing quotes + wrong LIKE)
        - ✅ WHERE "NOME_PROC" ILIKE '%cirurgia%' (correct)
        - ❌ SELECT COUNT(*) FROM procedimentos WHERE nome_proc... (lowercase fails)
        - ✅ SELECT COUNT(*) FROM procedimentos WHERE "NOME_PROC"... (correct)
        - ❌ COUNT(DISTINCT code_col) together with GROUP BY code_col (returns 1 per group)
        - ✅ COUNT(*) with GROUP BY code_col for frequency rankings
""",
    "obstetricos": """
        OBSTETRICOS TABLE RULES - OBSTETRIC/MATERNITY DATA:
        
        MANDATORY USAGE RULES:
        - Use for: Pregnancy, childbirth, maternity, obstetric cases
        - Keywords: "grávidas", "gestantes", "parto", "obstétrico", "obstetric", "pré-natal", "pre natal", "prenatal", "acompanhamento pré-natal"
        - Links to internacoes via "N_AIH"
        
        POSTGRESQL COLUMN QUOTING:
        - "N_AIH", "INSC_PN"
        
        CRITICAL DATA FIELDS:
        - "INSC_PN" = Prenatal registration/inscription (inscrição no pré-natal)
        - Non-null and non-empty "INSC_PN" indicates the case had prenatal care/acompanhamento

        CRITICAL RULES (Pré-natal):
        - For ANY query mentioning "pré-natal"/"pre natal"/"prenatal"/"acompanhamento pré-natal":
          ALWAYS use obstetricos."INSC_PN" to identify cases with prenatal care
        - Do NOT search for the phrase in diagnostic code/description fields ("DIAG_PRINC", "DIAG_SECUN")
        - Join to other tables (hospital, municipios) via internacoes only when additional attributes are required
        
        EXACT QUERY EXAMPLES:
        -- Total obstetric cases
        SELECT COUNT(*) FROM obstetricos;
        
        -- Obstetric cases with prenatal care
        SELECT COUNT(*) FROM obstetricos 
        WHERE "INSC_PN" IS NOT NULL AND "INSC_PN" != '';
        
        -- Obstetric cases with prenatal care by year (if needed)
        SELECT EXTRACT(YEAR FROM i."DT_INTER") AS ano, COUNT(*) AS total
        FROM obstetricos o
        JOIN internacoes i ON o."N_AIH" = i."N_AIH"
        WHERE o."INSC_PN" IS NOT NULL AND o."INSC_PN" != '' AND i."DT_INTER" IS NOT NULL
        GROUP BY EXTRACT(YEAR FROM i."DT_INTER")
        ORDER BY ano;
        
        -- Pregnant women in public hospitals
        SELECT COUNT(DISTINCT i."N_AIH") 
        FROM internacoes i 
        JOIN obstetricos o ON i."N_AIH" = o."N_AIH"
        JOIN hospital h ON i."CNES" = h."CNES"
        WHERE i."SEXO" = 3 AND h."NATUREZA" ILIKE '%public%';
        
        -- Obstetric cases requiring UTI
        SELECT COUNT(DISTINCT o."N_AIH")
        FROM obstetricos o
        JOIN uti_detalhes u ON o."N_AIH" = u."N_AIH";
""",
    "condicoes_especificas": """
         CONDICOES_ESPECIFICAS TABLE RULES - SPECIAL MEDICAL CONDITIONS:
        
        MANDATORY USAGE RULES:
        - Use for: Special conditions, VDRL testing, syphilis screening
        - "N_AIH" links to internacoes
        - "IND_VDRL" = VDRL indicator (syphilis test)
        
        POSTGRESQL COLUMN QUOTING:
        - "N_AIH", "IND_VDRL"
        
        CRITICAL VALUE MAPPINGS:
        - "IND_VDRL" = '1' means VDRL positive
        - Only positive/special cases are recorded in this table
        
        EXACT QUERY EXAMPLES:
        -- Total special conditions recorded
        SELECT COUNT(*) FROM condicoes_especificas;
        
        -- VDRL positive cases
        SELECT COUNT(*) FROM condicoes_especificas WHERE "IND_VDRL" = '1';
        
        -- VDRL positive cases that resulted in death
        SELECT COUNT(DISTINCT c."N_AIH") 
        FROM condicoes_especificas c 
        JOIN mortes m ON c."N_AIH" = m."N_AIH" 
        WHERE c."IND_VDRL" = '1';
        
        -- Special conditions with hospital data
        SELECT h."NATUREZA", COUNT(*) as special_cases
        FROM condicoes_especificas c
        JOIN internacoes i ON c."N_AIH" = i."N_AIH"
        JOIN hospital h ON i."CNES" = h."CNES"
        GROUP BY h."NATUREZA";
""",
    "instrucao": """
        INSTRUCAO TABLE RULES - EDUCATION LEVEL DATA:
        
        MANDATORY USAGE RULES:
        - Use for: Education analysis, schooling levels, literacy statistics
        - "N_AIH" links to internacoes
        - "INSTRU" = Education level code
        
        POSTGRESQL COLUMN QUOTING:
        - "N_AIH", "INSTRU"
        
        CRITICAL VALUE MAPPINGS:
        - "INSTRU" codes:   01= Não sabe ler e/ou escrever, 
                            02= Alfabetizado, 
                            03= 1 Grau incompleto,
        -                   04= 1 Grau completo, 
                            05= 2 Grau incompleto,
                            06= 2 Grau completo,
        -                   07= Ensino Superior incompleto, 
                            08= Ensino Superior completo,,    
                            09= Especialização/Residência,
        -                   10= Mestrado, 
                            11= Doutorado 
                                                         
        EXACT QUERY EXAMPLES:
        -- Total education records
        SELECT COUNT(*) FROM instrucao;
        
        -- Education level distribution
        SELECT "INSTRU", COUNT(*) as total
        FROM instrucao 
        WHERE "INSTRU" IS NOT NULL
        GROUP BY "INSTRU" 
        ORDER BY "INSTRU";
        
        -- Education vs hospitalization costs correlation
        SELECT ins."INSTRU", AVG(i."VAL_TOT") as avg_cost
        FROM instrucao ins
        JOIN internacoes i ON ins."N_AIH" = i."N_AIH"
        WHERE ins."INSTRU" IS NOT NULL AND i."VAL_TOT" IS NOT NULL
        GROUP BY ins."INSTRU"
        ORDER BY avg_cost DESC;
""",
    "vincprev": """
        VINCPREV TABLE RULES - SOCIAL SECURITY LINKAGE:
        
        MANDATORY USAGE RULES:
        - Use for: Social security, employment status, pension analysis
        - "N_AIH" links to internacoes
        - "VINCPREV" = Social security link type
        
        POSTGRESQL COLUMN QUOTING:
        - "N_AIH", "VINCPREV"
        
        CRITICAL VALUE MAPPINGS:
        - "VINCPREV" codes: 1=Employee, 2=Domestic worker, 3=Self-employed
        - 5=Retired, 6=Unemployed
        
        EXACT QUERY EXAMPLES:
        -- Total social security records
        SELECT COUNT(*) FROM vincprev;
        
        -- Social security type distribution
        SELECT "VINCPREV", COUNT(*) as total
        FROM vincprev 
        WHERE "VINCPREV" IS NOT NULL
        GROUP BY "VINCPREV" 
        ORDER BY "VINCPREV";
        
        -- Employment status vs health outcomes
        SELECT v."VINCPREV", COUNT(m."N_AIH") as deaths
        FROM vincprev v
        LEFT JOIN mortes m ON v."N_AIH" = m."N_AIH"
        GROUP BY v."VINCPREV";
""",
    "cbor": """
        CBOR TABLE RULES - PROFESSIONAL OCCUPATION CLASSIFICATION:
        
        MANDATORY USAGE RULES:
        - Use for: Occupational analysis, professional classification, job-health correlation
        - "N_AIH" links to internacoes
        - "CBOR" = Brazilian Occupation Classification code
        
        POSTGRESQL COLUMN QUOTING:
        - "N_AIH", "CBOR"
        
        CRITICAL PATTERNS:
        - Healthcare professionals often have codes starting with 225
        - Use for occupational health analysis
        
        EXACT QUERY EXAMPLES:
        -- Total CBOR records
        SELECT COUNT(*) FROM cbor;
        
        -- Most common occupations
        SELECT "CBOR", COUNT(*) as frequency
        FROM cbor 
        WHERE "CBOR" IS NOT NULL
        GROUP BY "CBOR" 
        ORDER BY frequency DESC LIMIT 10;
        
        -- Healthcare professionals who died
        SELECT COUNT(DISTINCT c."CBOR") 
        FROM cbor c 
        JOIN mortes m ON c."N_AIH" = m."N_AIH" 
        WHERE c."CBOR" IS NOT NULL;
        
        -- CBOR cases requiring UTI
        SELECT COUNT(DISTINCT c."N_AIH")
        FROM cbor c
        JOIN uti_detalhes u ON c."N_AIH" = u."N_AIH";
""",
    "infehosp": """
        INFEHOSP TABLE RULES - HOSPITAL INFECTIONS:
        
        MANDATORY USAGE RULES:
        - Use for: Hospital-acquired infections, nosocomial infections
        - "N_AIH" links to internacoes  
        - "INFEHOSP" = Hospital infection indicator
        -  WARNING: This table is currently EMPTY (0 records)
        
        POSTGRESQL COLUMN QUOTING:
        - "N_AIH", "INFEHOSP"
        
        CRITICAL NOTES:
        - Table exists but contains no data
        - Do not use for actual infection analysis
        
        EXACT QUERY EXAMPLES:
        -- Check if infections recorded (will return 0)
        SELECT COUNT(*) FROM infehosp;
        
        -- This query will return no results
        SELECT * FROM infehosp LIMIT 10;
""",
    "diagnosticos_secundarios": """
         DIAGNOSTICOS_SECUNDARIOS TABLE RULES - SECONDARY DIAGNOSES:
        
        MANDATORY USAGE RULES:
        - Use for: Secondary diagnoses, comorbidities, additional conditions
        - Composite key: ("N_AIH", "ordem_diagnostico")
        - "codigo_cid_secundario" = Secondary ICD-10 code
        -  WARNING: This table is currently EMPTY (0 records)
        
        POSTGRESQL COLUMN QUOTING:
        - "N_AIH", "codigo_cid_secundario", "ordem_diagnostico"
        
        CRITICAL NOTES:
        - Table exists but contains no data
        - Do not use for actual secondary diagnosis analysis
        - Use internacoes."DIAG_SECUN" instead for secondary diagnoses
        
        EXACT QUERY EXAMPLES:
        -- Check if secondary diagnoses recorded (will return 0)
        SELECT COUNT(*) FROM diagnosticos_secundarios;
        
        -- For actual secondary diagnoses, use internacoes table
        SELECT COUNT(*) FROM internacoes 
        WHERE "DIAG_SECUN" IS NOT NULL AND "DIAG_SECUN" != '';
""",
}


# Base PostgreSQL template for SQL generation
BASE_SQL_TEMPLATE = """You are a PostgreSQL expert assistant for Brazilian healthcare (SIH-RS) data analysis.

CORE POSTGRESQL INSTRUCTIONS:
1. Generate syntactically correct PostgreSQL queries
2. Use proper table and column names with double quotes
3. Handle Portuguese language questions appropriately  
4. Return only the SQL query, no explanation
5. Use appropriate WHERE clauses for filtering
6. Include LIMIT clauses when appropriate (default LIMIT 100)
7. Use proper JOINs when querying multiple tables
8. Use PostgreSQL-specific functions when needed (EXTRACT, ILIKE, etc.)

DATABASE SCHEMA CONTEXT:
{schema_context}

{table_specific_rules}

USER QUERY: {user_query}

Generate the PostgreSQL query:"""


def build_table_specific_prompt(selected_tables: list[str]) -> str:
    """
    Builds dynamic prompt based on selected tables for PostgreSQL SIH-RS database

    Args:
        selected_tables: List of selected table names

    Returns:
        String with specific rules for selected tables
    """
    if not selected_tables:
        return "No specific table rules available."

    rules = []
    rules.append(" POSTGRESQL TABLE-SPECIFIC RULES AND EXAMPLES:")
    rules.append("=" * 60)

    for table in selected_tables:
        if table in TABLE_TEMPLATES:
            rules.append(f"\n{TABLE_TEMPLATES[table]}")
        else:
            # Generic template for unmapped tables
            rules.append(f"""
        {table.upper()} - GENERAL POSTGRESQL RULES:
        - Use proper column names with double quotes: "COLUMN_NAME"
        - Apply appropriate WHERE conditions for filtering
        - Use LIMIT for large result sets to improve performance
        - Consider NULL values in WHERE clauses
        - Use PostgreSQL-specific functions when appropriate
        """)

    # NOTE: Multi-table JOIN rules are handled by build_multi_table_prompt() only
    # Removing the multi-table logic here prevents duplication when build_multi_table_prompt()
    # calls this function and then adds MULTI_TABLE_RULES separately

    return "\n".join(rules)


def get_table_template(table_name: str) -> str | None:
    """
    Gets specific template for a table

    Args:
        table_name: Name of the table

    Returns:
        Table template or None if doesn't exist
    """
    return TABLE_TEMPLATES.get(table_name)


def get_available_templates() -> list[str]:
    """
    Returns list of tables with available templates

    Returns:
        List of table names with templates
    """
    return list(TABLE_TEMPLATES.keys())


def validate_template_coverage(tables: list[str]) -> dict[str, bool]:
    """
    Validates if tables have available templates

    Args:
        tables: List of table names

    Returns:
        Dictionary mapping table -> has_template
    """
    return {table: table in TABLE_TEMPLATES for table in tables}


# Multi-table JOIN rules for PostgreSQL
MULTI_TABLE_RULES = """
MULTI-TABLE POSTGRESQL JOIN RULES:

CRITICAL JOIN PATTERNS:
- internacoes ↔ hospital: internacoes."CNES" = hospital."CNES"
- internacoes ↔ cid10: internacoes."DIAG_PRINC" = cid10."CID"
- internacoes ↔ mortes: internacoes."N_AIH" = mortes."N_AIH"
- internacoes ↔ uti_detalhes: internacoes."N_AIH" = uti_detalhes."N_AIH"
- municipios ↔ dado_ibge: municipios."codigo_ibge" = dado_ibge."codigo_municipio_completo"
- internacoes ↔ municipios: internacoes."MUNIC_RES" = municipios.codigo_6d


JOIN BEST PRACTICES:
- Always use table aliases for clarity (e.g., i.\"SEXO\", h.\"NATUREZA\")
- Use INNER JOIN for exact matches, LEFT JOIN to include null records
- Filter before joining when possible for better performance
- Always quote column names with double quotes in PostgreSQL

MULTI-TABLE EXAMPLES:

-- Deaths with disease descriptions
SELECT c."CD_DESCRICAO", COUNT(*) as deaths 
FROM mortes m 
INNER JOIN cid10 c ON m."CID_MORTE" = c."CID" 
WHERE m."CID_MORTE" IS NOT NULL
GROUP BY c."CD_DESCRICAO" 
ORDER BY deaths DESC;

-- Hospital mortality analysis
SELECT h."NATUREZA", 
       COUNT(DISTINCT i."N_AIH") as total_admissions,
       COUNT(DISTINCT m."N_AIH") as deaths,
       ROUND(COUNT(DISTINCT m."N_AIH")::numeric / COUNT(DISTINCT i."N_AIH") * 100, 2) as mortality_rate
FROM internacoes i
LEFT JOIN mortes m ON i."N_AIH" = m."N_AIH"
JOIN hospital h ON i."CNES" = h."CNES"
WHERE h."NATUREZA" IS NOT NULL
GROUP BY h."NATUREZA";

-- Municipality health statistics
SELECT mu."estado", d."nome_municipio", d."populacao",
       COUNT(i."N_AIH") as admissions
FROM internacoes i
JOIN municipios mu ON i."MUNIC_RES" = mu."codigo_6d"
JOIN dado_ibge d ON mu."codigo_ibge" = d."codigo_municipio_completo"
WHERE d."populacao" > 100
GROUP BY mu."estado", d."nome_municipio", d."populacao"
ORDER BY admissions DESC;

-- Most common diagnoses with descriptions (seasonal filter - winter months 6,7,8)
SELECT c."CID", c."CD_DESCRICAO", COUNT(*) AS total
FROM internacoes i
JOIN cid10 c ON i."DIAG_PRINC" = c."CID"
WHERE EXTRACT(MONTH FROM i."DT_INTER") IN (6,7,8)
GROUP BY c."CID", c."CD_DESCRICAO"
ORDER BY total DESC
LIMIT 3;
"""


def build_multi_table_prompt(selected_tables: list[str]) -> str:
    """
    Builds prompt for queries involving multiple tables

    Args:
        selected_tables: List of selected tables

    Returns:
        Prompt with multi-table rules
    """
    if len(selected_tables) <= 1:
        return build_table_specific_prompt(selected_tables)

    # If multiple tables, add JOIN rules
    single_table_rules = build_table_specific_prompt(selected_tables)

    return f"""
{single_table_rules}

{MULTI_TABLE_RULES}
"""


# Template system configuration
TEMPLATE_CONFIG = {
    "default_template": BASE_SQL_TEMPLATE,
    "include_examples": True,
    "include_mappings": True,
    "max_examples_per_table": 5,
    "enable_multi_table_rules": True,
    "postgresql_mode": True,
    "quote_columns": True,
    "include_performance_hints": True,
}


def get_template_stats() -> dict[str, int]:
    """
    Gets statistics about template coverage

    Returns:
        Dictionary with template statistics
    """
    return {
        "total_templates": len(TABLE_TEMPLATES),
        "populated_tables": 13,  # Tables with data
        "empty_tables": 2,  # infehosp, diagnosticos_secundarios
        "reference_tables": 5,  # cid10, hospital, municipios, dado_ibge, procedimentos
        "transaction_tables": 10,  # internacoes, mortes, uti_detalhes, etc.
    }
