# RULES A–O — SQL Generation Rules v1

**Source:** `src/agent/prompt_builder.py:build_sql_generation_messages`  
**Version:** v1  
**Active since:** 2026-04-30  
**EX baseline with these rules:** 93.3 % (120-query benchmark)

These rules are injected verbatim into the system prompt before every SQL
generation call. Changing any rule requires:
1. Bumping `prompt_version` in `OrchestratorConfig` to `"v2"`.
2. Running the regression suite (`make regression`) before merging.
3. Recording EX before/after in the PR description.

---

## RULE A — UTI / ICU

```
WHERE "VAL_UTI" > 0 to count or filter UTI.
For AVG/SUM on UTI values: also require WHERE "VAL_UTI" > 0 (excludes non-ICU zeros).
"total gasto em UTI" / "custo UTI" → SUM("VAL_UTI") WHERE "VAL_UTI" > 0
❌ NEVER SUM("VAL_TOT") WHERE "VAL_UTI" > 0 — VAL_TOT is the full hospitalization cost, NOT just UTI.
"obstétricas"/"obstétrico" = ESPEC = 2 (NEVER ESPEC BETWEEN 74 AND 83).
✅ WHERE "ESPEC" = 2 AND "VAL_UTI" > 0
```

---

## RULE B — Death Cause vs Diagnosis

```
"causa da morte"/"morreram de"/"óbitos por DOENÇA X"
  → JOIN cid ON i."CID_MORTE"=c."CID" WHERE i."MORTE"=true AND i."CID_MORTE" IS NOT NULL
"diagnóstico principal"/"internado por DOENÇA X"
  → JOIN cid ON i."DIAG_PRINC"=c."CID"
"resultaram em óbito" WITHOUT a specific disease
  → WHERE "MORTE"=true only (NO CID JOIN)
✅ "Quantas internações de UTI resultaram em óbito?" → WHERE "VAL_UTI" > 0 AND "MORTE" = true
```

---

## RULE C — LIMIT

```
Add LIMIT only when question asks for top-N (e.g. "top 5").
NEVER add a default LIMIT.
```

---

## RULE D — Only Requested Filters

```
Add only filters the question explicitly mentions.
No age filter unless age asked. No year filter unless year asked.
No gender unless gender asked.
No "MORTE"=false unless question specifically asks for discharged/surviving patients.
No WHERE col IS NOT NULL for aggregate queries (SUM/AVG/MAX/MIN already ignore NULLs).
✅ "Qual o total gasto?" → SELECT SUM("VAL_TOT") FROM internacoes  (NO IS NOT NULL filter)
❌ SELECT SUM("VAL_TOT") FROM internacoes WHERE "VAL_TOT" IS NOT NULL
```

---

## RULE E — CID Column

```
Include c."CID" ONLY WHEN: question explicitly says "com código" or "código CID".
Default: SELECT only c."CD_DESCRICAO", GROUP BY c."CD_DESCRICAO".
✅ "principais causas de morte" → SELECT c."CD_DESCRICAO", COUNT(*) GROUP BY c."CD_DESCRICAO"
✅ "com código" / "código CID" → SELECT c."CID", c."CD_DESCRICAO", COUNT(*) GROUP BY c."CID", c."CD_DESCRICAO"
❌ "quais os CIDs de entrada" → SELECT c."CD_DESCRICAO" only (NOT c."CID" unless "com código" stated)
```

---

## RULE F — Singular vs Plural LIMIT

```
Singular "qual o X mais Y" → LIMIT 1
Plural "quais os N X mais Y" → LIMIT N
```

---

## RULE G — Date Filters

```
Use EXTRACT directly on "DT_INTER". NEVER join tempo with non-equijoin.
✅ WHERE EXTRACT(YEAR FROM "DT_INTER") = 2020
Only use "DT_SAIDA" when question explicitly asks about discharge or exit date.
```

---

## RULE H — IDADE (INTEGER) vs NASC (DATE)

```
"IDADE" = pre-calculated integer age column (0–130). USE FOR ALL age filters/groupings.
"NASC" = birth date. USE ONLY when question asks about BIRTH YEAR specifically.
✅ WHERE "IDADE" > 60   ✅ GROUP BY "IDADE"   ✅ CASE WHEN "IDADE" < 18
✅ WHERE EXTRACT(YEAR FROM "NASC") < 1950  ← "nascidos antes de 1950" → use NASC
❌ EXTRACT(YEAR FROM AGE("NASC")) > 60     ← NEVER
❌ (CURRENT_DATE - "NASC") / 365 > 60     ← NEVER
```

---

## RULE I — COUNT rows vs COUNT DISTINCT values

```
"Quantos X diferentes existem cadastrados/registrados?" → COUNT(*) rows in the table.
COUNT(DISTINCT col) only when asking "quantos valores únicos de COLUNA".
✅ "Quantos procedimentos diferentes existem?" → SELECT COUNT(*) FROM procedimentos
❌ SELECT COUNT(DISTINCT "NOME_PROC")
```

---

## RULE J — Per-Group Top-N (ROW_NUMBER mandatory)

```
MANDATORY ROW_NUMBER WHEN QUESTION ASKS top-N FOR MULTIPLE GROUPS.
Triggers: "de cada", "por cada", "por faixa", "por grupo", OR multiple explicit segments.
❌ NEVER plain LIMIT for per-group queries.
✅ ROW_NUMBER() OVER (PARTITION BY <group> ORDER BY <metric> DESC) AS rn … WHERE rn <= N
```

---

## RULE K — Anti-Join (absence pattern)

```
"nunca tiveram", "sem", "não aparece", "jamais" → NOT EXISTS, not NOT IN.
✅ WHERE NOT EXISTS (SELECT 1 FROM tabela_b b WHERE b.fk = a.pk AND <condition>)
❌ NOT IN (SELECT col FROM ... WHERE ...)  ← breaks silently when subquery returns NULL
```

---

## RULE L — Pivot Format (side-by-side comparison)

```
Explicit side-by-side comparison ("X vs Y", "comparar X com Y", "lado a lado"):
✅ WIDE format: CASE WHEN pivot
❌ Long format (one row per category+group)
```

---

## RULE M — Aggregation-First

```
Count/aggregate events by entity → GROUP BY directly on fact table (internacoes),
then JOIN for labels.
✅ SELECT "CNES", COUNT(*) FROM internacoes GROUP BY "CNES" → JOIN hospital for name
❌ JOIN hospital first, then GROUP BY — drops CNES values not in hospital table
```

---

## RULE N — Global vs Local Average

```
Filtering entities above/below an average → compute reference from FULL dataset:
✅ WITH ref AS (SELECT … FROM internacoes [full scope]) … HAVING local_taxa > (SELECT taxa FROM ref)
❌ AVG(per_group_rate) FROM already-filtered-subgroup
```

---

## RULE O — Description vs Code

```
"quais métodos", "quais diagnósticos", "quais níveis de instrução"
→ JOIN lookup table and return DESCRICAO, not raw code.
instrucao → JOIN instrucao ins ON i."INSTRU" = ins."INSTRU" → SELECT ins."DESCRICAO"
raça/cor  → JOIN raca_cor r ON i."RACA_COR" = r."RACA_COR" → SELECT r."DESCRICAO"
```

---

## Disease Lookup convention

```
Table is "cid" (NOT "cid10"). NEVER hardcode CID codes.
Displaying diagnosis → ALWAYS JOIN cid c ON i."DIAG_PRINC"=c."CID" → SELECT c."CD_DESCRICAO"
Filtering by named disease → JOIN cid c ... WHERE c."CD_DESCRICAO" ILIKE '%X%'
Category (no specific name) → WHERE "DIAG_PRINC" LIKE 'J%'
```
