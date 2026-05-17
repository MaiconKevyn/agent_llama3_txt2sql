# DuckDB-specific templates for all sihrd5 tables
TABLE_TEMPLATES = {
    "internacoes": """
         INTERNACOES TABLE RULES - MAIN HOSPITALIZATION DATA (sihrd5):

        ⚠️ CRITICAL SCHEMA CHANGES FROM PREVIOUS VERSION ⚠️

        2. IND_VDRL IS A BOOLEAN COLUMN — there is NO separate "condicoes_especificas" table:
           ✅ WHERE "IND_VDRL" = true        (correct — VDRL positive)
           ❌ JOIN condicoes_especificas     (table does not exist!)
           CRITICAL: For ANY VDRL query → ONLY use WHERE "IND_VDRL" = true.
           NEVER join the cid table for VDRL — VDRL has no CID code category!

        3. DIAG_SECUN IS DIRECTLY IN internacoes — there is NO separate "diagnosticos_secundarios" table:
           ✅ WHERE "DIAG_SECUN" IS NOT NULL (correct)
           ❌ JOIN diagnosticos_secundarios  (table does not exist!)

        4. PROCEDURES require a JUNCTION TABLE — there is NO PROC_REA column in internacoes:
           ✅ JOIN internacao_procedimento ip ON i."N_AIH" = ip."N_AIH" JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"
           ❌ i."PROC_REA"                   (column does not exist in internacoes!)

        5. DIAS_PERM substitutes QT_DIARIAS:
           ✅ "DIAS_PERM"   (days of stay — use this)
           ❌ "QT_DIARIAS"  (does not exist in sihrd5!)

        6. IDADE vs NASC — REGRA CRÍTICA DE IDADE:
           "IDADE" é coluna INTEGER pré-calculada (0-130). USE SEMPRE para filtros de idade.
           "NASC" é data de nascimento. USE SOMENTE quando a pergunta for sobre ANO DE NASCIMENTO.
           ✅ WHERE "IDADE" > 60                          ← filtro de idade → use IDADE
           ✅ GROUP BY "IDADE"                             ← agrupar por idade → use IDADE
           ✅ CASE WHEN "IDADE" < 18 THEN 'Menor'          ← faixa etária → use IDADE
           ✅ WHERE EXTRACT(YEAR FROM "NASC") < 1950        ← "nascidos antes de 1950" → use NASC
           ❌ EXTRACT(YEAR FROM AGE("NASC")) > 60           ← ERRADO! use IDADE diretamente!
           ❌ (CURRENT_DATE - "NASC") / 365 > 60           ← ERRADO! use IDADE diretamente!

        ─────────────────────────────────────────────────────────────────

        MANDATORY VALUE MAPPINGS (NEVER MAKE MISTAKES):
        - SEXO: 1=Masculino, 3=Feminino (NEVER use 2! — use inline value, no JOIN needed)
        - RACA_COR: 1=Branca, 2=Preta, 3=Parda, 4=Amarela, 5=Indígena; 99=Sem info em internacoes
          · Para FILTRAR: WHERE "RACA_COR" = 5  (sem JOIN)
          · Para DESCRIÇÃO: JOIN raca_cor r ON i."RACA_COR" = r."RACA_COR" → SELECT r."DESCRICAO"
        - MORTE: true=death, false=discharge (boolean)
        - IND_VDRL: true=positive, false=negative (boolean)
          ✅ SELECT COUNT(*) FROM internacoes WHERE "IND_VDRL" = true;
          ❌ JOIN cid c ON ... WHERE c."DESCRICAO" ILIKE '%vdrl%'  (no CID code for VDRL!)
        - DIAS_PERM: days of stay (integer)
        - Financial: "VAL_TOT" (total cost), "VAL_SH" (serviço hospitalar), "VAL_SP" (professional), "VAL_UTI" (ICU cost)
          · "valor do serviço hospitalar" → "VAL_SH"  (NÃO VAL_TOT!)
          · "valor total da internação" / "valor médio" (sem especificar) → "VAL_TOT"
        - Dates: "DT_INTER" (admission), "DT_SAIDA" (discharge/death), "NASC" (birth date — see rule 6)
        - IDADE: integer age (0-130) — SEMPRE usar para filtros/grupos de idade (ver regra 6)

        CRITICAL UTI VALUE QUERIES — always include VAL_UTI > 0 filter:
        - "valor médio de UTI" / "custo médio UTI" → AVG("VAL_UTI") WHERE "VAL_UTI" > 0
        - "total gasto em UTI" / "total UTI" / "gasto UTI" → SUM("VAL_UTI") WHERE "VAL_UTI" > 0
          ❌ NEVER use SUM("VAL_TOT") WHERE "VAL_UTI" > 0 for "gasto em UTI":
             VAL_TOT = total cost of the entire hospitalization (UTI + all other services)
             VAL_UTI = cost of UTI care specifically — use this for any UTI cost question
        - Without VAL_UTI > 0, the aggregate includes all hospitalizations (most with VAL_UTI = 0)
          ✅ SELECT AVG("VAL_UTI") FROM internacoes WHERE "SEXO" = 1 AND "VAL_UTI" > 0
          ❌ SELECT AVG("VAL_UTI") FROM internacoes WHERE "SEXO" = 1  ← includes zeros!

        CRITICAL JOIN RELATIONSHIPS:
        - → hospital: internacoes."CNES" = hospital."CNES"
        - → cid: internacoes."DIAG_PRINC" = cid."CID"  (diagnóstico principal)
        - → cid: internacoes."DIAG_PRINC" = cid."CID" + i."MORTE" = true (causa/motivo de morte analítico)
        - → cid: internacoes."CID_MORTE" = cid."CID"   (campo bruto/auditável; use só se o usuário pedir CID_MORTE)
        - → municipios (residência paciente): internacoes."MUNIC_RES" = municipios."CO_MUNICIPIO_6D"
        - → municipios (localização hospital): JOIN hospital h ON i."CNES" = h."CNES"
                                               JOIN municipios m ON h."MUNIC_MOV" = m."CO_MUNICIPIO_6D"
        - → internacao_procedimento (for procedures): internacoes."N_AIH" = internacao_procedimento."N_AIH"
        - → especialidade: internacoes."ESPEC" = especialidade."ESPEC" (para obter nome da especialidade)
        - → raca_cor: internacoes."RACA_COR" = raca_cor."RACA_COR" (para obter descrição da raça)
        - → instrucao: internacoes."INSTRU" = instrucao."INSTRU" (para obter nome do nível de instrução)

        MUNIC_RES vs MUNIC_MOV — QUANDO USAR CADA UM:
        - "municípios de RESIDÊNCIA dos pacientes" / "onde os pacientes moram" → i."MUNIC_RES" → municipios
        - "municípios que ATENDEM mais pacientes" / "por localização do hospital" / "médias por município (hospital)" →
          JOIN hospital h ON i."CNES" = h."CNES"
          JOIN municipios m ON h."MUNIC_MOV" = m."CO_MUNICIPIO_6D"  ← usa hospital.MUNIC_MOV!

        === FEW-SHOT EXAMPLES ===

        --- EASY EXAMPLES ---

        -- Q: "Qual o volume de internações que geraram custo de UTI?"
        SELECT COUNT(*) AS total_uti FROM internacoes WHERE "VAL_UTI" > 0;

        -- Q: "Qual o valor médio de UTI nas internações que resultaram em óbito vs alta?"
        -- NOTE: teaching pattern: VAL_UTI > 0 selects UTI patients; CASE differentiates outcomes
        SELECT CASE WHEN "MORTE" = true THEN 'Óbito' ELSE 'Alta' END AS desfecho,
               COUNT(*) AS total,
               ROUND(AVG("VAL_UTI"), 2) AS valor_medio_uti
        FROM internacoes
        WHERE "VAL_UTI" > 0
        GROUP BY "MORTE"
        ORDER BY desfecho;

        -- Q: "Qual o tempo médio de permanência em internações obstétricas?"
        -- NOTE: ESPEC = 2 identifies obstetric cases. NEVER use CID codes to detect obstetric!
        SELECT AVG("DIAS_PERM") AS media_dias_obstetrico
        FROM internacoes
        WHERE "ESPEC" = 2;

        --- MEDIUM EXAMPLES ---

        -- Q: "Quantas internações por doenças cardiovasculares ocorreram no verão (dezembro a fevereiro)?"
        -- NOTE: "cardiovascular" = CID chapter I → use LIKE 'I%' on DIAG_PRINC (no JOIN needed for category)
        -- NOTE: do NOT use ILIKE '%cardiovascular%' — that term doesn't exist in DESCRICAO!
        SELECT COUNT(*) FROM internacoes
        WHERE "DIAG_PRINC" LIKE 'I%'
          AND EXTRACT(MONTH FROM "DT_INTER") IN (12, 1, 2);

        -- Q: "Qual o principal diagnóstico de entrada nas internações masculinas?"
        -- NOTE: SINGULAR "qual o X mais Y" → LIMIT 1 (not LIMIT 5 or no LIMIT!)
        -- NOTE: include c."CID" ONLY when question says "com código" — default: only description
        SELECT c."DESCRICAO" AS diagnostico, COUNT(*) AS total
        FROM internacoes i
        JOIN cid c ON i."DIAG_PRINC" = c."CID"
        WHERE i."DIAG_PRINC" IS NOT NULL AND i."SEXO" = 1
        GROUP BY c."DESCRICAO"
        ORDER BY total DESC
        LIMIT 1;

        -- Q: "Como se distribui o volume de internações por mês do ano?"
        SELECT EXTRACT(MONTH FROM "DT_INTER") AS mes, COUNT(*) AS total
        FROM internacoes
        WHERE "DT_INTER" IS NOT NULL
        GROUP BY EXTRACT(MONTH FROM "DT_INTER")
        ORDER BY mes;

        --- HARD EXAMPLES ---

        -- Q: "Quais doenças mais frequentemente causam óbito em internações hospitalares?"
        -- RULE: (1) use DIAG_PRINC with MORTE=true; (2) include c."CID" ONLY when question says "com código";
        --       (3) GROUP BY c."DESCRICAO" by default; (4) always filter MORTE = true
        SELECT c."DESCRICAO" AS causa_morte, COUNT(*) AS total_mortes
        FROM internacoes i
        JOIN cid c ON i."DIAG_PRINC" = c."CID"
        WHERE i."MORTE" = true AND i."DIAG_PRINC" IS NOT NULL
        GROUP BY c."DESCRICAO"
        ORDER BY total_mortes DESC
        LIMIT 10;

        -- Q: "Internações por [doença] que ocasionaram morte (óbito)?"
        -- NOTE: doença + óbito → JOIN via DIAG_PRINC e filtro MORTE=true
        -- TWO filter strategies:
        --   (A) Search by disease NAME → ILIKE '%nome%' on c."DESCRICAO"
        --   (B) Search by CID chapter prefix → c."CID" LIKE 'X%'
        -- Example A: sepse (pesquisa por nome na descrição):
        SELECT COUNT(*) AS total_obitos_sepse
        FROM internacoes i
        JOIN cid c ON i."DIAG_PRINC" = c."CID"
        WHERE c."DESCRICAO" ILIKE '%sepse%'  -- pesquisa por nome, NÃO por código!
          AND i."MORTE" = true;
        -- Example B: neoplasias (pesquisa por capítulo CID):
        SELECT COUNT(*) AS total_obitos_neoplasia
        FROM internacoes i
        JOIN cid c ON i."DIAG_PRINC" = c."CID"
        WHERE c."CID" LIKE 'C%'  -- neoplasias malignas (capítulo C do CID-10)
          AND i."MORTE" = true;

        -- Q: "Qual a especialidade médica com maior custo médio de internação?"
        -- NOTE: for specialty NAME join especialidade; for UTI specifically use VAL_UTI > 0 not ESPEC
        SELECT e."DESCRICAO" AS especialidade,
               ROUND(AVG(i."VAL_TOT"), 2) AS custo_medio,
               COUNT(*) AS total_internacoes
        FROM internacoes i
        JOIN especialidade e ON i."ESPEC" = e."ESPEC"
        WHERE i."VAL_TOT" IS NOT NULL
        GROUP BY e."DESCRICAO"
        ORDER BY custo_medio DESC;

        -- Q: "Qual a distribuição por idade nas internações?"
        -- NOTE: "por idade" means exact numeric IDADE, not age bands.
        SELECT "IDADE", COUNT(*) AS total_internacoes
        FROM internacoes
        GROUP BY "IDADE"
        ORDER BY total_internacoes DESC;

        -- Q: "Qual o tempo médio de permanência em UTI por faixa etária?"
        -- NOTE: "faixa etária" always means CASE WHEN age bands (NOT GROUP BY exact IDADE)
        -- NOTE: always include VAL_UTI > 0 for UTI queries to filter only UTI patients
        SELECT CASE WHEN "IDADE" < 18 THEN 'Menor' WHEN "IDADE" < 60 THEN 'Adulto' ELSE 'Idoso' END AS faixa_etaria,
               AVG("DIAS_PERM") AS media_dias_permanencia
        FROM internacoes
        WHERE "IDADE" IS NOT NULL AND "VAL_UTI" > 0
        GROUP BY CASE WHEN "IDADE" < 18 THEN 'Menor' WHEN "IDADE" < 60 THEN 'Adulto' ELSE 'Idoso' END;

        -- Q: "Qual a taxa de mortalidade entre pacientes idosos acima de 65 anos?"
        -- NOTE: taxa de mortalidade = SUM(CASE WHEN MORTE THEN 1 ELSE 0 END) * 100.0 / COUNT(*)
        -- NOTE: always ROUND(..., 2) and include total_internacoes + total_mortes for context
        SELECT 'Acima de 65 anos' AS faixa_etaria,
               COUNT(*) AS total_internacoes,
               SUM(CASE WHEN "MORTE" = true THEN 1 ELSE 0 END) AS total_mortes,
               ROUND(SUM(CASE WHEN "MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS taxa_mortalidade
        FROM internacoes
        WHERE "IDADE" > 65;

        -- Q: "Quais os 10 municípios com maior custo médio de internação hospitalar?"
        -- NOTE: HAVING COUNT(*) > 100 to exclude low-volume municipalities
        SELECT mu."NO_MUNICIPIO" AS municipio,
               COUNT(*) AS total_internacoes,
               ROUND(AVG(i."VAL_TOT"), 2) AS custo_medio
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"
        GROUP BY mu."NO_MUNICIPIO"
        HAVING COUNT(*) > 100
        ORDER BY custo_medio DESC
        LIMIT 10;

        -- Q: "Qual o volume de internações por estado de residência em Goiás e Mato Grosso?"
        -- NOTE: "nos estados do X e Y" or "por estado" → GROUP BY estado to return per-state breakdown (NOT total)
        SELECT mu."SG_UF" AS estado, COUNT(*) AS total_internacoes
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"
        WHERE mu."SG_UF" IN ('GO', 'MT')
        GROUP BY mu."SG_UF"
        ORDER BY total_internacoes DESC;

        -- Q: "Quantas mortes foram registradas no estado do RS?"
        -- NOTE: death by patient residence state → JOIN municipios via MUNIC_RES and filter MORTE = true
        -- NOTE: single state requested → return total count, NOT GROUP BY estado
        SELECT COUNT(*) AS total_mortes
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"
        WHERE i."MORTE" = true
          AND mu."SG_UF" = 'RS';

        -- Q: "Como se distribui o vínculo previdenciário dos pacientes internados?"
        -- NOTE: bare distribution query → use raw numeric column (NOT JOIN lookup table)
        -- Only JOIN vincprev when question asks for human-readable DESCRIPTIONS
        SELECT "VINCPREV", COUNT(*) AS total
        FROM internacoes
        GROUP BY "VINCPREV"
        ORDER BY total DESC;

        -- Q: "Qual o custo médio de internação por hospital?"
        SELECT h."CNES", h."NATUREZA", AVG(i."VAL_TOT") AS custo_medio
        FROM internacoes i
        JOIN hospital h ON i."CNES" = h."CNES"
        WHERE i."VAL_TOT" IS NOT NULL
        GROUP BY h."CNES", h."NATUREZA"
        ORDER BY custo_medio DESC
        LIMIT 10;

        -- Q: "Qual o procedimento com maior volume de execuções registradas em internações masculinas?"
        SELECT p."NOME_PROC", COUNT(*) AS total
        FROM internacoes i
        JOIN internacao_procedimento ip ON i."N_AIH" = ip."N_AIH"
        JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"
        WHERE i."SEXO" = 1
        GROUP BY p."NOME_PROC"
        ORDER BY total DESC
        LIMIT 10;

        -- Q: "Quais os 3 diagnósticos mais comuns por especialidade médica?"
        -- PATTERN: top-N per named dimension → ROW_NUMBER PARTITION BY dimension, never LIMIT global
        SELECT especialidade, diagnostico, total_internacoes
        FROM (
            SELECT e."DESCRICAO" AS especialidade, c."DESCRICAO" AS diagnostico,
                   COUNT(*) AS total_internacoes,
                   ROW_NUMBER() OVER (PARTITION BY e."DESCRICAO" ORDER BY COUNT(*) DESC, c."DESCRICAO" ASC) AS rn
            FROM internacoes i
            JOIN especialidade e ON i."ESPEC" = e."ESPEC"
            JOIN cid c ON i."DIAG_PRINC" = c."CID"
            GROUP BY e."DESCRICAO", c."DESCRICAO"
        ) sub
        WHERE rn <= 3
        ORDER BY especialidade, rn;

        -- Q: "Quais hospitais com mais de 500 internações nunca registraram óbito?"
        -- PATTERN: absence/anti-join → NOT EXISTS (safer than NOT IN)
        -- PATTERN: aggregate on fact table first, then filter — do NOT join hospital first
        SELECT "CNES", COUNT(*) AS total_internacoes
        FROM internacoes
        GROUP BY "CNES"
        HAVING COUNT(*) > 500
          AND NOT EXISTS (
              SELECT 1 FROM internacoes d WHERE d."CNES" = internacoes."CNES" AND d."MORTE" = true
          )
        ORDER BY total_internacoes DESC;

        -- Q: "Qual a média de dias de internação comparando os pacientes do estado A vs estado B?"
        -- PATTERN: side-by-side comparison → CASE WHEN pivot (wide format), not long format
        SELECT e."DESCRICAO" AS especialidade,
               ROUND(AVG(CASE WHEN mu."SG_UF" = 'SC' THEN i."DIAS_PERM" END), 2) AS media_SC,
               ROUND(AVG(CASE WHEN mu."SG_UF" = 'PR' THEN i."DIAS_PERM" END), 2) AS media_PR,
               COUNT(CASE WHEN mu."SG_UF" = 'SC' THEN 1 END) AS total_SC,
               COUNT(CASE WHEN mu."SG_UF" = 'PR' THEN 1 END) AS total_PR
        FROM internacoes i
        JOIN especialidade e ON i."ESPEC" = e."ESPEC"
        JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"
        WHERE mu."SG_UF" IN ('SC', 'PR')
        GROUP BY e."DESCRICAO"
        HAVING COUNT(CASE WHEN mu."SG_UF" = 'SC' THEN 1 END) > 100
           AND COUNT(CASE WHEN mu."SG_UF" = 'PR' THEN 1 END) > 100
        ORDER BY especialidade;

        -- Q: "Quais municípios têm taxa de mortalidade acima da média estadual (mínimo 500 internações)?"
        -- PATTERN: global reference CTE + compare local rate vs reference rate
        WITH media_estado AS (
            SELECT SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa_ref
            FROM internacoes i JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"
            WHERE mu."SG_UF" = 'SP'
        ),
        por_municipio AS (
            SELECT mu."NO_MUNICIPIO" AS nome, COUNT(*) AS total, SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa
            FROM internacoes i JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"
            WHERE mu."SG_UF" = 'SP'
            GROUP BY mu."NO_MUNICIPIO" HAVING COUNT(*) > 500
        )
        SELECT pm.nome, pm.total, ROUND(pm.taxa, 2) AS taxa_mortalidade
        FROM por_municipio pm, media_estado me
        WHERE pm.taxa > me.taxa_ref
        ORDER BY pm.taxa DESC LIMIT 10;

        -- Q: "Qual o nível de instrução com maior taxa de mortalidade no estado do PA?"
        -- PATTERN: JOIN lookup table for description (not raw code), compute rate in SELECT
        SELECT ins."DESCRICAO", COUNT(*) AS total_internacoes,
               SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) AS total_mortes,
               ROUND(SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS taxa_mortalidade
        FROM internacoes i
        JOIN instrucao ins ON i."INSTRU" = ins."INSTRU"
        JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"
        WHERE mu."SG_UF" = 'PA' AND i."INSTRU" IS NOT NULL AND i."INSTRU" != 0
        GROUP BY ins."DESCRICAO"
        HAVING COUNT(*) > 1000
        ORDER BY taxa_mortalidade DESC;
""",
    "internacao_procedimento": """
        PROCEDURE JUNCTION TABLE RULES - PROCEDURES PER HOSPITALIZATION:

        MANDATORY USAGE RULES:
        - This is the JUNCTION TABLE between internacoes and procedimentos
        - Each row = one procedure performed during one hospitalization
        - A single hospitalization can have MANY procedure records (1:N)
        - 37M+ records in this table

        CRITICAL: TO GET PROCEDURE DATA you MUST use a TWO-JOIN pattern:
        internacoes → internacao_procedimento → procedimentos

        ❌ WRONG (PROC_REA does not exist in internacoes):
        SELECT i."PROC_REA" FROM internacoes i

        ✅ CORRECT:
        SELECT p."NOME_PROC", COUNT(*) AS total
        FROM internacao_procedimento ip
        JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"
        GROUP BY p."NOME_PROC"
        ORDER BY total DESC;

        POSTGRESQL COLUMN QUOTING:
        - "id_atendimento" (PK), "N_AIH" (FK → internacoes), "PROC_REA" (FK → procedimentos)

        === FEW-SHOT EXAMPLES ===

        -- Q: "Qual o procedimento médico mais executado nos registros de atendimento?"
        SELECT p."NOME_PROC", COUNT(*) AS total
        FROM internacao_procedimento ip
        JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"
        GROUP BY p."NOME_PROC"
        ORDER BY total DESC
        LIMIT 10;

        -- Q: "Quantos procedimentos por internação em média?"
        SELECT AVG(proc_count) AS media_procedimentos
        FROM (
          SELECT "N_AIH", COUNT(*) AS proc_count
          FROM internacao_procedimento
          GROUP BY "N_AIH"
        ) t;

        -- Q: "Quantos procedimentos cirúrgicos foram realizados?"
        SELECT COUNT(*) AS total
        FROM internacao_procedimento ip
        JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"
        WHERE p."NOME_PROC" ILIKE '%cirurgia%';

        -- Q: "Procedimentos realizados em internações de mulheres"
        SELECT p."NOME_PROC", COUNT(*) AS total
        FROM internacoes i
        JOIN internacao_procedimento ip ON i."N_AIH" = ip."N_AIH"
        JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"
        WHERE i."SEXO" = 3
        GROUP BY p."NOME_PROC"
        ORDER BY total DESC
        LIMIT 10;

        -- Q: "Qual o custo total de internações por tipo de procedimento em hospitais de MG?" (filtro por ESTADO via hospital)
        -- PATTERN: filter by HOSPITAL state → join internacoes + internacao_procedimento + procedimentos + hospital + municipios
        -- CRITICAL: hospital.MUNIC_MOV = city where HOSPITAL is located (NOT patient residence!)
        SELECT p."NOME_PROC" AS procedimento, SUM(i."VAL_TOT") AS custo_total
        FROM internacao_procedimento ip
        JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"
        JOIN internacoes i ON ip."N_AIH" = i."N_AIH"
        JOIN hospital h ON i."CNES" = h."CNES"
        JOIN municipios m ON h."MUNIC_MOV" = m."CO_MUNICIPIO_6D"
        WHERE m."SG_UF" = 'MG'
        GROUP BY p."NOME_PROC"
        ORDER BY custo_total DESC
        LIMIT 10;
""",
    "cid": """
         CID TABLE RULES - ICD-10 DISEASE CODES (REFERENCE TABLE):

        MANDATORY USAGE RULES:
        - Use for: Disease code lookups, descriptions, JOIN operations
        - "CID" = ICD-10 code column (contains codes like 'J18', 'I21', 'C50')
        - "DESCRICAO" = TEXT description column (contains 'Pneumonia', 'Infarto', 'Cancer mama')
        - TABLE NAME IS "cid" (NOT "cid10" — name changed in sihrd5!)

        ⚠️ CRITICAL COLUMN QUOTING — ALL COLUMNS REQUIRE DOUBLE QUOTES:
        ✅ c."CID"           (correct)   ❌ c.cid   (WRONG — will cause DB error!)
        ✅ c."DESCRICAO"  (correct)   ❌ c.cd_descricao  (WRONG — will cause DB error!)
        ✅ c."DESCRICAO"  (correct)   ❌ c.DESCRICAO  (WRONG — must have quotes!)

        POSTGRESQL COLUMN QUOTING:
        - "CID" (ICD-10 code), "DESCRICAO" (description)

        CRITICAL SEARCH PATTERNS:
        - Description search (disease name): WHERE "DESCRICAO" ILIKE '%pneumonia%'
        - Code range search (disease category): WHERE "CID" LIKE 'I%'
        - NEVER: WHERE "DESCRICAO" LIKE 'I%' (codes are in CID, not in DESCRICAO!)

        JOIN PATTERNS WITH internacoes:
        - Primary diagnosis: JOIN cid c ON i."DIAG_PRINC" = c."CID"
        - Secondary diagnosis: JOIN cid c ON i."DIAG_SECUN" = c."CID"
        - Analytical death cause: JOIN cid c ON i."DIAG_PRINC" = c."CID" WHERE i."MORTE" = true
        - Raw CID_MORTE audit only: JOIN cid c ON i."CID_MORTE" = c."CID"

        EXACT QUERY EXAMPLES:
        -- Find specific code description
        SELECT "DESCRICAO" FROM cid WHERE "CID" = 'A15';

        -- Search diabetes codes
        SELECT "CID", "DESCRICAO"
        FROM cid
        WHERE "CID" LIKE 'E1%';

        -- Top diagnoses with descriptions (CID explicitly asked = include c."CID")
        SELECT c."CID", c."DESCRICAO", COUNT(*) AS total
        FROM internacoes i
        JOIN cid c ON i."DIAG_PRINC" = c."CID"
        WHERE i."DIAG_PRINC" IS NOT NULL
        GROUP BY c."CID", c."DESCRICAO"
        ORDER BY total DESC
        LIMIT 10;

        -- Q: "Qual o principal diagnóstico de entrada para cada vínculo previdenciário?"
        -- PATTERN "principal X por cada Y" → ROW_NUMBER() OVER (PARTITION BY Y ORDER BY count DESC) = 1
        SELECT "VINCPREV", "DIAG_PRINC", total_internacoes
        FROM (
            SELECT i."VINCPREV", i."DIAG_PRINC", COUNT(i."N_AIH") AS total_internacoes,
                   ROW_NUMBER() OVER (PARTITION BY i."VINCPREV" ORDER BY COUNT(i."N_AIH") DESC) AS rn
            FROM internacoes i
            GROUP BY i."VINCPREV", i."DIAG_PRINC"
        ) ranked
        WHERE rn = 1
        ORDER BY total_internacoes DESC
        LIMIT 10;

        -- Q: "Qual o diagnóstico mais frequente para cada especialidade médica?"
        -- PATTERN: top-1 per group → ROW_NUMBER() OVER (PARTITION BY group ORDER BY count DESC) = 1
        SELECT e."DESCRICAO" AS especialidade, c."DESCRICAO" AS diagnostico_principal, total_internacoes
        FROM (
            SELECT i."ESPEC", i."DIAG_PRINC", c."DESCRICAO",
                   COUNT(i."N_AIH") AS total_internacoes,
                   ROW_NUMBER() OVER (PARTITION BY i."ESPEC" ORDER BY COUNT(i."N_AIH") DESC) AS rn
            FROM internacoes i
            JOIN cid c ON i."DIAG_PRINC" = c."CID"
            JOIN especialidade e ON i."ESPEC" = e."ESPEC"
            GROUP BY i."ESPEC", i."DIAG_PRINC", c."DESCRICAO"
        ) ranked
        WHERE rn = 1
        ORDER BY especialidade;
""",
    "hospital": """
         HOSPITAL TABLE RULES - HEALTHCARE FACILITIES:

        MANDATORY USAGE RULES:
        - Use for: Hospital counts, facility analysis, public/private classification
        - "CNES" = National Health Facility Registry code (primary key)
        - "MUNIC_MOV" = FK → municipios.CO_MUNICIPIO_6D (municipality where hospital is located)
        - "NATUREZA" = Facility nature (public/private classification)

        CRITICAL COUNTING RULES:
        - To count hospitals: COUNT(DISTINCT h."CNES")
        - Do NOT count by admissions (admissions are in internacoes)

        MUNICIPALITY RESOLUTION FOR HOSPITAL:
        ✅ CORRECT (hospital has MUNIC_MOV → municipios directly):
           JOIN municipios mu ON h."MUNIC_MOV" = mu."CO_MUNICIPIO_6D"

        ❌ WRONG (old pattern with dado_ibge — table does not exist):
           JOIN dado_ibge d ON mu."CO_MUNICIPIO_7D" = d."codigo_municipio_completo"

        ✅ For socioeconomic data of hospital's municipality:
           JOIN municipios mu ON h."MUNIC_MOV" = mu."CO_MUNICIPIO_6D"
           JOIN socioeconomico s ON s."CO_MUNICIPIO_6D" = mu."CO_MUNICIPIO_6D"
           -- then select the explicit indicator column, e.g. s."QT_POPULACAO"

        POSTGRESQL COLUMN QUOTING:
        - "CNES", "MUNIC_MOV", "NATUREZA", "GESTAO", "NAT_JUR"

        NATUREZA VALUES (approximate):
        - 0 = Público federal, 20/22 = Público municipal/estadual
        - 30/40 = Filantrópico/Sem fins lucrativos
        - 50 = Privado lucrativo, 60/61 = Privado filantrópico

        EXACT QUERY EXAMPLES:
        -- Total hospitals
        SELECT COUNT(*) FROM hospital;

        -- Hospitals with admissions
        SELECT COUNT(DISTINCT h."CNES")
        FROM hospital h
        JOIN internacoes i ON h."CNES" = i."CNES";

        -- Hospital activity volume
        SELECT h."CNES", h."NATUREZA", COUNT(i."N_AIH") AS internacoes
        FROM hospital h
        JOIN internacoes i ON h."CNES" = i."CNES"
        GROUP BY h."CNES", h."NATUREZA"
        ORDER BY internacoes DESC
        LIMIT 10;

        -- Hospital by municipality name
        SELECT h."CNES", mu."NO_MUNICIPIO", mu."SG_UF", h."NATUREZA"
        FROM hospital h
        JOIN municipios mu ON h."MUNIC_MOV" = mu."CO_MUNICIPIO_6D"
        WHERE mu."SG_UF" = 'RS';
""",
    "municipios": """
        MUNICIPIOS TABLE RULES - BRAZILIAN MUNICIPALITIES:

        MANDATORY USAGE RULES:
        - Use for: Geographic queries, municipality names, state, coordinates
        - "CO_MUNICIPIO_6D" = 6-digit code (primary key — used in FKs from internacoes and hospital)
        - "CO_MUNICIPIO_7D" = IBGE code (7 digits)
        - "NO_MUNICIPIO" = municipality name, "SG_UF" = state abbreviation (RS, SP, RJ...)

        POSTGRESQL COLUMN QUOTING:
        - "CO_MUNICIPIO_6D", "CO_MUNICIPIO_7D", "NO_MUNICIPIO", "SG_UF", "latitude", "longitude"

        CRITICAL RELATIONSHIPS:
        - internacoes → municipios: internacoes."MUNIC_RES" = municipios."CO_MUNICIPIO_6D"
        - hospital → municipios: hospital."MUNIC_MOV" = municipios."CO_MUNICIPIO_6D"
        - socioeconomico → municipios: socioeconomico."CO_MUNICIPIO_6D" = municipios."CO_MUNICIPIO_6D"

        ❌ WRONG (dado_ibge does not exist in sihrd5):
           JOIN dado_ibge d ON mu."CO_MUNICIPIO_7D" = d."codigo_municipio_completo"

        ✅ CORRECT for socioeconomic data:
           JOIN socioeconomico s ON s."CO_MUNICIPIO_6D" = mu."CO_MUNICIPIO_6D"
           -- then select the explicit indicator column, e.g. s."QT_POPULACAO"

        EXACT QUERY EXAMPLES:
        -- Total municipalities
        SELECT COUNT(*) FROM municipios;

        -- RS state municipalities
        SELECT COUNT(*) FROM municipios WHERE "SG_UF" = 'RS';

        -- Distinct states covered by the database geography reference
        SELECT COUNT(DISTINCT "SG_UF") FROM municipios;

        -- Municipalities by state
        SELECT "SG_UF", COUNT(*) AS total_municipios
        FROM municipios
        GROUP BY "SG_UF"
        ORDER BY total_municipios DESC;

        -- Internações by state (via municipality of patient's residence)
        SELECT mu."SG_UF" AS estado, COUNT(*) AS total_internacoes
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"
        GROUP BY mu."SG_UF"
        ORDER BY total_internacoes DESC;

        -- Q: "Quantas internações ocorreram nos estados da região Norte?" → GROUP BY estado (per-state breakdown!)
        -- PATTERN "nos estados do X e Y" → always GROUP BY estado to return one row per state
        SELECT mu."SG_UF" AS estado, COUNT(*) AS total_internacoes
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"
        WHERE mu."SG_UF" IN ('AM', 'PA', 'AC', 'RO', 'RR', 'AP', 'TO')
        GROUP BY mu."SG_UF"
        ORDER BY total_internacoes DESC;
""",
    "procedimentos": """
         PROCEDIMENTOS TABLE RULES - MEDICAL PROCEDURES REFERENCE:

        MANDATORY USAGE RULES:
        - Reference table for procedure codes and descriptions
        - To count PROCEDURES PERFORMED, MUST use internacao_procedimento as junction table:
          internacoes → internacao_procedimento → procedimentos
        - "PROC_REA" = Procedure code (primary key)
        - "NOME_PROC" = Procedure description/name

        CRITICAL: There is NO PROC_REA column in internacoes — always use internacao_procedimento!

        ⚠️ CRITICAL: For "quais procedimentos"/"nomes dos procedimentos" queries:
        - ALWAYS SELECT p."NOME_PROC" (the human-readable name), NEVER p."PROC_REA" (the code)!
          ✅ SELECT p."NOME_PROC", COUNT(*) AS total  → "Cirurgia Cardíaca", "Parto Normal", etc.
          ❌ SELECT p."PROC_REA", COUNT(*) AS total   → "0301060096", "0310010039" (codes, not names!)

        POSTGRESQL COLUMN QUOTING:
        - ALWAYS use double quotes: "PROC_REA", "NOME_PROC"

        EXACT QUERY EXAMPLES:
        -- Total procedure types in reference table
        SELECT COUNT(*) AS total_procedimentos FROM procedimentos;

        -- Count procedures containing "CIRURGIA"
        SELECT COUNT(*) AS procedimentos_cirurgia
        FROM procedimentos
        WHERE "NOME_PROC" ILIKE '%CIRURGIA%';

        -- Most common procedures performed (via internacao_procedimento junction)
        SELECT p."NOME_PROC", COUNT(*) AS frequency
        FROM internacao_procedimento ip
        JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"
        GROUP BY p."NOME_PROC"
        ORDER BY frequency DESC
        LIMIT 10;

        -- Procedures per hospitalization
        SELECT p."NOME_PROC", COUNT(DISTINCT ip."N_AIH") AS internacoes_count
        FROM internacao_procedimento ip
        JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"
        GROUP BY p."NOME_PROC"
        ORDER BY internacoes_count DESC
        LIMIT 10;
""",
    "instrucao": """
        INSTRUCAO TABLE RULES - EDUCATION LEVEL LOOKUP:

        MANDATORY USAGE RULES:
        - This is a LOOKUP TABLE with INSTRU code + DESCRICAO
        - Education level is stored in internacoes."INSTRU" as a FK
        - Use for: JOIN with internacoes to get education level description

        POSTGRESQL COLUMN QUOTING:
        - "INSTRU" (PK), "DESCRICAO"

        INSTRU VALUE MAPPINGS:
        0=Sem informação, 1=Não sabe ler/escrever, 2=Alfabetizado,
        3=1°grau incompleto, 4=1°grau completo, 5=2°grau incompleto,
        6=2°grau completo, 7=Superior incompleto, 8=Superior completo,
        9=Especialização/Residência, 10=Mestrado, 11=Doutorado

        ⚠️ CRITICAL: INSTRU=0 means "Sem informação" (not recorded) — ALWAYS exclude it when
        grouping by education level, regardless of how the question is phrased:
        - CORRECT: WHERE "INSTRU" IS NOT NULL AND "INSTRU" != 0  → only real education data
        - WRONG:   no filter or JOIN instrucao alone  → includes code 0 (18M rows of unknowns!)
          Without "!= 0", virtually ALL patients appear under "Sem informação", distorting every
          count, average, and rate computed per education group.

        EXACT QUERY EXAMPLES:
        -- NOTE: count WITH education data → use internacoes directly (NOT instrucao lookup table!)
        -- instrucao table has only 12 rows (codes); patient records are in internacoes."INSTRU"
        -- "Quantos pacientes têm nível de instrução superior completo ou acima?"
        SELECT COUNT(*) FROM internacoes WHERE "INSTRU" >= 8 AND "INSTRU" IS NOT NULL;

        -- Education level distribution of hospitalizations
        SELECT ins."DESCRICAO", COUNT(*) AS total
        FROM internacoes i
        JOIN instrucao ins ON i."INSTRU" = ins."INSTRU"
        WHERE i."INSTRU" IS NOT NULL AND i."INSTRU" != 0
        GROUP BY ins."INSTRU", ins."DESCRICAO"
        ORDER BY total DESC;

        -- Average cost by education level
        SELECT ins."DESCRICAO", AVG(i."VAL_TOT") AS avg_cost
        FROM internacoes i
        JOIN instrucao ins ON i."INSTRU" = ins."INSTRU"
        WHERE i."INSTRU" IS NOT NULL AND i."INSTRU" != 0
        GROUP BY ins."INSTRU", ins."DESCRICAO"
        ORDER BY avg_cost DESC;
""",
    "vincprev": """
        VINCPREV TABLE RULES - SOCIAL SECURITY LINKAGE LOOKUP:

        MANDATORY USAGE RULES:
        - This is a LOOKUP TABLE with VINCPREV code + DESCRICAO
        - Social security type is stored in internacoes."VINCPREV" as a FK
        - Use for: JOIN with internacoes to get social security description

        POSTGRESQL COLUMN QUOTING:
        - "VINCPREV" (PK), "DESCRICAO"

        VINCPREV VALUE MAPPINGS:
        0=Sem informação, 1=Autônomo, 2=Desempregado, 3=Aposentado,
        4=Não segurado, 5=Empregado, 6=Empregador

        ⚠️ CRITICAL: "informado" / "registrado" / "tem vínculo previdenciário" means code != 0:
        - CORRECT: WHERE "VINCPREV" IS NOT NULL AND "VINCPREV" != 0  → only real social security data
        - WRONG:   JOIN vincprev WHERE "DESCRICAO" IS NOT NULL  → includes code 0 (18M rows!)
          Code 0 = "Sem informação" — almost ALL patients have this default code.
          Without "!= 0", the JOIN returns virtually the entire internacoes table.

        EXACT QUERY EXAMPLES:
        -- Count registered social security linkage types in the lookup catalog
        SELECT COUNT(*) FROM vincprev;

        -- NOTE: count WITH social security data → use internacoes directly (NOT vincprev lookup table!)
        -- vincprev table has only 7 rows (codes); patient records are in internacoes."VINCPREV"
        -- "Quantos pacientes aposentados foram internados?"
        SELECT COUNT(*) FROM internacoes WHERE "VINCPREV" = 3;  -- 3 = Aposentado

        -- Social security distribution of hospitalizations
        SELECT v."DESCRICAO", COUNT(*) AS total
        FROM internacoes i
        JOIN vincprev v ON i."VINCPREV" = v."VINCPREV"
        WHERE i."VINCPREV" IS NOT NULL AND i."VINCPREV" != 0
        GROUP BY v."VINCPREV", v."DESCRICAO"
        ORDER BY total DESC;

        -- Mortality by social security type
        SELECT v."DESCRICAO",
               COUNT(*) AS total,
               SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) AS mortes,
               ROUND(SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END)::numeric / COUNT(*) * 100, 2) AS taxa_mortalidade
        FROM internacoes i
        JOIN vincprev v ON i."VINCPREV" = v."VINCPREV"
        GROUP BY v."VINCPREV", v."DESCRICAO"
        ORDER BY taxa_mortalidade DESC;
""",
    "sexo": """
        SEXO TABLE RULES - SEX LOOKUP:

        ⚠️ DO NOT JOIN this table — use inline mapping directly in the query.

        SEXO VALUES (memorize — only 2 valid values):
        - 1 = Masculino (male)
        - 3 = Feminino (female)
        - NEVER use SEXO = 2 (does not exist)

        ✅ CORRECT PATTERNS (no JOIN needed):
        -- Filter:
        SELECT COUNT(*) FROM internacoes WHERE "SEXO" = 1;  -- men
        SELECT COUNT(*) FROM internacoes WHERE "SEXO" = 3;  -- women

        -- Group with readable labels:
        SELECT
          CASE WHEN "SEXO" = 1 THEN 'Masculino' WHEN "SEXO" = 3 THEN 'Feminino' END AS sexo,
          COUNT(*) AS total
        FROM internacoes
        WHERE "SEXO" IN (1, 3)
        GROUP BY "SEXO";

        ❌ WRONG (unnecessary JOIN):
        SELECT s."DESCRICAO", COUNT(*) FROM internacoes i JOIN sexo s ON i."SEXO" = s."SEXO" ...
""",
    "raca_cor": """
        RACA_COR TABLE RULES - RACE/COLOR LOOKUP:

        RACA_COR VALUE MAPPINGS:
        Lookup raca_cor has identified categories 1..5.
        internacoes."RACA_COR" can also contain unknown code 99.
        stg/source data may contain 0 for SEM INFORMACAO.
        1  = BRANCA
        2  = PRETA
        3  = PARDA
        4  = AMARELA
        5  = INDIGENA
        99 = SEM INFORMACAO
        (0 and 99 both mean "not recorded")

        ⚠️ INCLUDE or EXCLUDE SEM INFORMACAO? Depends on the question:
        • DISTRIBUIÇÃO / COMPOSIÇÃO total → INCLUDE (no filter): shows all patients including unknowns
          "distribuição por raça", "composição racial", "quantas internações por raça"
          → use CASE/COALESCE with LEFT JOIN to keep SEM INFORMACAO rows
        • ANÁLISE por raça (taxa, média, correlação) → EXCLUDE unknowns: WHERE "RACA_COR" NOT IN (0, 99)
          "taxa de mortalidade por raça", "custo médio por raça"

        THREE USAGE PATTERNS:
        1. FILTRAR por raça específica → use internacoes."RACA_COR" inline (no JOIN needed):
           WHERE "RACA_COR" = 5  — use the code directly

        2. MOSTRAR DESCRIÇÃO/NOME → JOIN raca_cor table (it has the DESCRICAO column):
           JOIN raca_cor r ON i."RACA_COR" = r."RACA_COR" → SELECT r."DESCRICAO"
           This inner join keeps identified categories 1..5 and excludes SEM INFORMACAO.
           Alternativa para análise (exclui unknowns): CASE WHEN "RACA_COR" = 1 THEN 'Branca' ... END

        3. CONTAR CATEGORIAS cadastradas → use the raca_cor lookup table (not internacoes):
           The raca_cor table has 5 identified categories; querying it gives the catalogue count.
           Do NOT use COUNT(DISTINCT "RACA_COR") FROM internacoes — that counts only codes
           actually present in patient records, which may differ from the registered catalogue.

        ⚠️ CRITICAL: distinguish populated field from identified race/color:
          "campo RACA_COR preenchido" → WHERE "RACA_COR" IS NOT NULL (includes 99=SEM INFORMACAO)
          "raça/cor registrada, informada ou identificada" → WHERE "RACA_COR" IN (1, 2, 3, 4, 5)
          This is DIFFERENT from counting categories (5) — do not confuse the two.

        ✅ CORRECT PATTERNS:
        -- ANÁLISE por raça (exclui unknowns — CASE WHEN inline):
        SELECT
          CASE
            WHEN "RACA_COR" = 1 THEN 'Branca'
            WHEN "RACA_COR" = 2 THEN 'Preta'
            WHEN "RACA_COR" = 3 THEN 'Parda'
            WHEN "RACA_COR" = 4 THEN 'Amarela'
            WHEN "RACA_COR" = 5 THEN 'Indígena'
          END AS raca_cor,
          COUNT(*) AS total
        FROM internacoes
        WHERE "RACA_COR" NOT IN (0, 99)   -- exclude unknowns for analysis
        GROUP BY "RACA_COR"
        ORDER BY total DESC;

        -- Filter by specific race:
        SELECT COUNT(*) FROM internacoes WHERE "RACA_COR" = 5;  -- indigenous

        -- DISTRIBUIÇÃO completa (inclui SEM INFORMACAO — use JOIN, sem filtro):
        SELECT r."DESCRICAO", COUNT(*) AS total
        FROM internacoes i
        JOIN raca_cor r ON i."RACA_COR" = r."RACA_COR"
        -- NO WHERE filter: codes 0 and 99 both map to 'SEM INFORMACAO' in the lookup
        GROUP BY r."DESCRICAO"
        ORDER BY total DESC;
""",
    "etnia": """
        ETNIA TABLE RULES - INDIGENOUS ETHNICITY LOOKUP:

        MANDATORY USAGE RULES:
        - Lookup table with 256 indigenous ethnicity codes
        - Ethnicity is stored in internacoes."ETNIA" as a FK
        - Only relevant for indigenous patients (internacoes."RACA_COR" = 5)
        - Use for: JOIN with internacoes to get ethnicity description

        POSTGRESQL COLUMN QUOTING:
        - "ETNIA" (PK), "DESCRICAO"

        JOIN PATTERN:
        - internacoes → etnia: internacoes."ETNIA" = etnia."ETNIA"

        EXACT QUERY EXAMPLES:
        -- Hospitalizations by indigenous ethnicity
        SELECT e."DESCRICAO", COUNT(*) AS total
        FROM internacoes i
        JOIN etnia e ON i."ETNIA" = e."ETNIA"
        WHERE i."RACA_COR" = 5
        GROUP BY e."ETNIA", e."DESCRICAO"
        ORDER BY total DESC
        LIMIT 10;

        -- Mortality by ethnicity
        SELECT e."DESCRICAO",
               COUNT(*) AS total,
               SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) AS mortes
        FROM internacoes i
        JOIN etnia e ON i."ETNIA" = e."ETNIA"
        WHERE i."RACA_COR" = 5
        GROUP BY e."ETNIA", e."DESCRICAO"
        ORDER BY mortes DESC;
""",
    "nacionalidade": """
        NACIONALIDADE TABLE RULES - NATIONALITY LOOKUP:

        MANDATORY USAGE RULES:
        - Lookup table with 333 nationality codes
        - Nationality is stored in internacoes."NACIONAL" as a FK
        - Use for: JOIN with internacoes to get nationality description

        POSTGRESQL COLUMN QUOTING:
        - "NACIONAL" (PK), "DESCRICAO"

        JOIN PATTERN:
        - internacoes → nacionalidade: internacoes."NACIONAL" = nacionalidade."NACIONAL"

        EXACT QUERY EXAMPLES:
        -- Hospitalizations by nationality
        SELECT n."DESCRICAO", COUNT(*) AS total
        FROM internacoes i
        JOIN nacionalidade n ON i."NACIONAL" = n."NACIONAL"
        WHERE i."NACIONAL" IS NOT NULL
        GROUP BY n."NACIONAL", n."DESCRICAO"
        ORDER BY total DESC
        LIMIT 10;

        -- Foreign nationals hospitalized
        SELECT n."DESCRICAO", COUNT(*) AS total
        FROM internacoes i
        JOIN nacionalidade n ON i."NACIONAL" = n."NACIONAL"
        WHERE i."NACIONAL" != 10  -- 10 = Brazil
        GROUP BY n."NACIONAL", n."DESCRICAO"
        ORDER BY total DESC;

        -- ⚠️ TOP-1 per group with ROW_NUMBER (generic per-group pattern):
        -- When question asks "principal X de cada Y" use ROW_NUMBER, NOT LIMIT
        SELECT n."DESCRICAO" AS nacionalidade, COUNT(*) AS total
        FROM internacoes i
        JOIN nacionalidade n ON i."NACIONAL" = n."NACIONAL"
        GROUP BY n."DESCRICAO"
        ORDER BY total DESC;
        -- For per-group top-N, apply RULE J: ROW_NUMBER() OVER (PARTITION BY group_col ORDER BY COUNT(*) DESC, tiebreaker ASC)
        -- outer SELECT must reference the subquery alias, NOT the inner table alias (i.)
""",
    "contraceptivos": """
        CONTRACEPTIVOS TABLE RULES - CONTRACEPTIVE METHOD LOOKUP:

        MANDATORY USAGE RULES:
        - Lookup table with 13 contraceptive method codes (0=Sem informação, 1=LAM, ..., 12=Coito interrompido)
        - Used ONLY for obstetric hospitalizations (internacoes."ESPEC" = 2)
        - TWO FK columns in internacoes: "CONTRACEP1" and "CONTRACEP2" (both reference CONTRACEPTIVO)

        POSTGRESQL COLUMN QUOTING:
        - "CONTRACEPTIVO" (PK), "DESCRICAO"

        CONTRACEPTIVO VALUES:
        0=Sem informação, 1=LAM, 2=Ogino-Knaus, 3=Temp. basal,
        4=Billings, 5=Cinto térmico, 6=DIU, 7=Diafragma,
        8=Preservativo, 9=Espermicida, 10=Hormônio oral,
        11=Hormônio injetável, 12=Coito interrompido

        JOIN PATTERNS:
        - Primary contraceptive: JOIN contraceptivos c1 ON i."CONTRACEP1" = c1."CONTRACEPTIVO"
        - Secondary contraceptive: JOIN contraceptivos c2 ON i."CONTRACEP2" = c2."CONTRACEPTIVO"

        EXACT QUERY EXAMPLES:
        -- Most used contraceptive methods in obstetric admissions
        SELECT c."DESCRICAO", COUNT(*) AS total
        FROM internacoes i
        JOIN contraceptivos c ON i."CONTRACEP1" = c."CONTRACEPTIVO"
        WHERE i."ESPEC" = 2 AND i."CONTRACEP1" != 0
        GROUP BY c."CONTRACEPTIVO", c."DESCRICAO"
        ORDER BY total DESC;

        -- Primary + secondary contraceptive combinations
        SELECT c1."DESCRICAO" AS metodo_1, c2."DESCRICAO" AS metodo_2, COUNT(*) AS total
        FROM internacoes i
        JOIN contraceptivos c1 ON i."CONTRACEP1" = c1."CONTRACEPTIVO"
        JOIN contraceptivos c2 ON i."CONTRACEP2" = c2."CONTRACEPTIVO"
        WHERE i."ESPEC" = 2 AND i."CONTRACEP1" != 0 AND i."CONTRACEP2" != 0
        GROUP BY c1."DESCRICAO", c2."DESCRICAO"
        ORDER BY total DESC
        LIMIT 10;
""",
    "especialidade": """
        ESPECIALIDADE TABLE RULES - MEDICAL SPECIALTY LOOKUP:

        MANDATORY USAGE RULES:
        - Lookup table: ESPEC code + DESCRICAO
        - Use for: JOIN with internacoes to get specialty description in human-readable form
        - CRITICAL: For UTI/ICU admissions, do NOT use ESPEC. Use VAL_UTI > 0 instead:
          ✅ WHERE "VAL_UTI" > 0          (correct UTI detection)
          ❌ WHERE "ESPEC" BETWEEN 74 AND 83  (unreliable for UTI detection — do not use)

        ESPEC RANGES:
        - 1=Cirúrgico, 2=Obstétrico, 3=Clínico, 4=Crônico, 5=Psiquiatria
        - 7=Pediátrico

        CRITICAL COUNTING RULES:
        ⚠️ "Quantas especialidades estão cadastradas?" → COUNT rows in especialidade table DIRECTLY
        ✅ SELECT COUNT(*) AS total_especialidades FROM especialidade;
        ❌ SELECT COUNT(DISTINCT "ESPEC") FROM internacoes;  ← WRONG! Counts ESPEC codes used in
           internacoes (≠ total specialties registered). Some specialties may have zero admissions.

        EXACT QUERY EXAMPLES:

        -- Count registered specialties (DIRECT TABLE COUNT — NOT from internacoes!)
        SELECT COUNT(*) AS total_especialidades FROM especialidade;

        -- Hospitalizations by specialty
        SELECT e."DESCRICAO" AS especialidade, COUNT(*) AS total_consultas
        FROM internacoes i
        JOIN especialidade e ON i."ESPEC" = e."ESPEC"
        GROUP BY e."DESCRICAO"
        ORDER BY total_consultas DESC;

        -- Average cost by specialty type
        SELECT e."DESCRICAO", AVG(i."VAL_TOT") AS avg_cost
        FROM internacoes i
        JOIN especialidade e ON i."ESPEC" = e."ESPEC"
        WHERE i."VAL_TOT" IS NOT NULL
        GROUP BY e."DESCRICAO"
        ORDER BY avg_cost DESC;
""",
    "socioeconomico": """
        SOCIOECONOMICO TABLE RULES - MUNICIPALITY SOCIOECONOMIC DATA:

        MANDATORY USAGE RULES:
        - PRIMARY TABLE for municipality demographic/economic analysis
        - FORMAT: Wide format — each row = one municipality in one year
        - PK is composite: ("CO_MUNICIPIO_6D", "NU_ANO")
        - CRITICAL: "taxa de mortalidade infantil" / "mortalidade infantil" data lives HERE,
          NOT in internacoes. Use "VL_MORT_INFANTIL".
        - CRITICAL: population / "população" data lives HERE:
          Use "QT_POPULACAO".

        ⚠️ ANTI-PATTERNS TO NEVER USE:
        ❌ WHERE s.metrica = 'populacao_total' or SELECT s.valor
           (metrica/valor do not exist in the active schema)
        ✅ SELECT mu."NO_MUNICIPIO" AS municipio
           FROM socioeconomico s
           JOIN municipios mu ON s."CO_MUNICIPIO_6D" = mu."CO_MUNICIPIO_6D"
           ORDER BY s."QT_POPULACAO" DESC

        CRITICAL: When looking for "maior X" in socioeconomico:
        - ALWAYS start FROM socioeconomico
        - JOIN municipios for the name
        - Use the explicit metric column in ORDER BY

        AVAILABLE COLUMNS:
        - "QT_POPULACAO"        — total population
        - "VL_PIB_PERCAPITA"    — GDP per capita
        - "QT_OBITOS_INFANTIS"  — infant deaths
        - "QT_NASCIDOS_VIVOS"   — live births
        - "VL_MORT_INFANTIL"    — infant mortality rate
        - "QT_LEITOS_SUS"       — SUS beds
        - "VL_LEITOS_SUS_1000"  — SUS beds per 1000 residents
        - "QT_MEDICOS"          — physicians
        - "VL_MEDICOS_1000"     — physicians per 1000 residents

        ❌ WRONG (dado_ibge does not exist in sihrd5):
           JOIN dado_ibge d ON ...

        ✅ CORRECT:
           JOIN socioeconomico s ON s."CO_MUNICIPIO_6D" = mu."CO_MUNICIPIO_6D"

        POSTGRESQL COLUMN QUOTING:
        - "CO_MUNICIPIO_6D", "NU_ANO", "QT_POPULACAO", "VL_MORT_INFANTIL", etc.

        EXACT QUERY EXAMPLES:
        -- Q: "Quantos municípios distintos possuem dados socioeconômicos?"
        SELECT COUNT(DISTINCT "CO_MUNICIPIO_6D") AS total_municipios
        FROM socioeconomico;

        -- Q: "Qual a taxa média de mortalidade infantil dos municípios brasileiros?"
        SELECT AVG("VL_MORT_INFANTIL") AS taxa_media_mortalidade_infantil
        FROM socioeconomico
        WHERE "VL_MORT_INFANTIL" IS NOT NULL;

        -- Q: "Qual o município com maior população?"
        SELECT mu."NO_MUNICIPIO" AS municipio, s."QT_POPULACAO" AS populacao
        FROM socioeconomico s
        JOIN municipios mu ON s."CO_MUNICIPIO_6D" = mu."CO_MUNICIPIO_6D"
        ORDER BY s."QT_POPULACAO" DESC
        LIMIT 1;

        -- Average SUS beds by state
        SELECT mu."SG_UF" AS estado, ROUND(AVG(s."VL_LEITOS_SUS_1000"), 2) AS leitos_sus_1000
        FROM socioeconomico s
        JOIN municipios mu ON s."CO_MUNICIPIO_6D" = mu."CO_MUNICIPIO_6D"
        GROUP BY mu."SG_UF"
        ORDER BY leitos_sus_1000 DESC;
""",
    "tempo": """
        TEMPO TABLE RULES - DATE DIMENSION:

        MANDATORY USAGE RULES:
        - Date dimension table: one row per date
        - PREFERRED: Use EXTRACT() directly on internacoes."DT_INTER" — NO JOIN NEEDED for most queries

        POSTGRESQL COLUMN QUOTING:
        - "data" (PK, date type), "ano", "mes", "trimestre", "dia_semana"

        ⚠️⚠️ CRITICAL ANTI-PATTERN — NEVER JOIN TEMPO ON COMPUTED EXPRESSIONS:
        ❌ CATASTROPHIC: JOIN tempo t ON EXTRACT(YEAR FROM i."DT_INTER") = t.ano
           → Each internacao joins to ALL 365/366 rows in that year = 366× row explosion!
           → "Quantas internações em 2015?" GT=1,179,761 but WRONG result = 6,736,089,123!
        ❌ CATASTROPHIC: JOIN tempo t ON EXTRACT(MONTH FROM i."DT_INTER") BETWEEN 6 AND 8
           → Each row joins to ~90 date rows = 90× explosion!

        ✅ ALWAYS USE EXTRACT DIRECTLY WITHOUT ANY JOIN:
        -- "Quantas internações ocorreram em um determinado ano?" → EXTRACT(YEAR FROM "DT_INTER") = <year>
        SELECT COUNT(*) AS total_ano FROM internacoes WHERE EXTRACT(YEAR FROM "DT_INTER") = 2020;

        -- "Quantas internações no verão (dezembro a fevereiro)?"
        SELECT COUNT(*) FROM internacoes WHERE EXTRACT(MONTH FROM "DT_INTER") IN (12, 1, 2);

        -- Filter by month range (e.g., spring: Sep-Nov):
        SELECT COUNT(*) FROM internacoes WHERE EXTRACT(MONTH FROM "DT_INTER") BETWEEN 9 AND 11;

        -- Only join tempo when grouping BY date attributes (equijoin on exact date):
        SELECT t."mes", COUNT(*) AS total
        FROM internacoes i
        JOIN tempo t ON i."DT_INTER" = t."data"
        GROUP BY t."mes"
        ORDER BY t."mes";
""",
}


# Base DuckDB template for SQL generation
BASE_SQL_TEMPLATE = """You are a DuckDB SQL expert assistant for Brazilian healthcare (SIH-RD) data analysis.

CORE DUCKDB INSTRUCTIONS:
1. Generate syntactically correct DuckDB queries
2. Use proper table and column names with double quotes
3. Handle Portuguese language questions appropriately
4. Return only the SQL query, no explanation
5. Use appropriate WHERE clauses for filtering
6. Include LIMIT clauses when appropriate (default LIMIT 100)
7. Use proper JOINs when querying multiple tables
8. Use DuckDB-compatible functions when needed (EXTRACT, ILIKE, etc.)

DATABASE SCHEMA CONTEXT:
{schema_context}

{table_specific_rules}

USER QUERY: {user_query}

Generate the DuckDB query:"""


def build_table_specific_prompt(selected_tables: list[str]) -> str:
    """
    Builds dynamic prompt based on selected tables for DuckDB sihrd5 database

    Args:
        selected_tables: List of selected table names

    Returns:
        String with specific rules for selected tables
    """
    if not selected_tables:
        return "No specific table rules available."

    rules = []
    rules.append(" DUCKDB TABLE-SPECIFIC RULES AND EXAMPLES:")
    rules.append("=" * 60)

    for table in selected_tables:
        if table in TABLE_TEMPLATES:
            rules.append(f"\n{TABLE_TEMPLATES[table]}")
        else:
            # Generic template for unmapped tables
            rules.append(f"""
        {table.upper()} - GENERAL DUCKDB RULES:
        - Use proper column names with double quotes: "COLUMN_NAME"
        - Apply appropriate WHERE conditions for filtering
        - Use LIMIT for large result sets to improve performance
        - Consider NULL values in WHERE clauses
        - Use DuckDB-compatible functions when appropriate
        """)

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


# Multi-table JOIN rules for DuckDB — sihrd5
MULTI_TABLE_RULES = """
MULTI-TABLE DUCKDB JOIN RULES (sihrd5):

CRITICAL JOIN PATTERNS:
- internacoes ↔ hospital: internacoes."CNES" = hospital."CNES"
- internacoes ↔ cid (primary diag): internacoes."DIAG_PRINC" = cid."CID"
- internacoes ↔ cid (secondary diag): internacoes."DIAG_SECUN" = cid."CID"
- internacoes ↔ cid (analytical death cause): internacoes."DIAG_PRINC" = cid."CID" with internacoes."MORTE" = true
- internacoes ↔ cid (raw CID_MORTE audit only): internacoes."CID_MORTE" = cid."CID"
- internacoes ↔ internacao_procedimento: internacoes."N_AIH" = internacao_procedimento."N_AIH"
- internacao_procedimento ↔ procedimentos: internacao_procedimento."PROC_REA" = procedimentos."PROC_REA"
- internacoes ↔ municipios: internacoes."MUNIC_RES" = municipios."CO_MUNICIPIO_6D"
- hospital ↔ municipios: hospital."MUNIC_MOV" = municipios."CO_MUNICIPIO_6D"
- municipios ↔ socioeconomico: municipios."CO_MUNICIPIO_6D" = socioeconomico."CO_MUNICIPIO_6D"
- internacoes ↔ sexo: internacoes."SEXO" = sexo."SEXO"
- internacoes ↔ raca_cor: internacoes."RACA_COR" = raca_cor."RACA_COR"
- internacoes ↔ instrucao: internacoes."INSTRU" = instrucao."INSTRU"
- internacoes ↔ vincprev: internacoes."VINCPREV" = vincprev."VINCPREV"
- internacoes ↔ especialidade: internacoes."ESPEC" = especialidade."ESPEC"

TABLES THAT NO LONGER EXIST IN sihrd5 — NEVER USE:
- mortes (use internacoes."MORTE" = true instead)
- cid10 (renamed to cid)
- dado_ibge (replaced by socioeconomico wide-format columns)
- uti_detalhes (use internacoes."VAL_UTI" > 0 — do NOT use ESPEC for UTI detection)
- condicoes_especificas (use internacoes."IND_VDRL" = true)
- obstetricos (use internacoes."INSC_PN", "GESTRISCO", "CONTRACEP1", "CONTRACEP2")
- diagnosticos_secundarios (use internacoes."DIAG_SECUN")
- cbor, infehosp (removed from sihrd5)

JOIN BEST PRACTICES:
- Always use table aliases for clarity (e.g., i."SEXO", h."NATUREZA")
- Use INNER JOIN for exact matches, LEFT JOIN to include null records
- Filter before joining when possible for better performance
- Always quote column names with double quotes
- When counting hospitals: COUNT(DISTINCT h."CNES")

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
    "duckdb_mode": True,
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
        "fact_tables": 2,  # internacoes, internacao_procedimento
        "reference_tables": 5,  # cid, hospital, municipios, procedimentos, socioeconomico
        "lookup_tables": 9,  # sexo, raca_cor, instrucao, vincprev, especialidade, tempo, etnia, nacionalidade, contraceptivos
        "total_db_tables": 16,  # total tables in sihrd5
    }
