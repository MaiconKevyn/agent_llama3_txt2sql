"""Prompt assembly and pre-generation hints for SQL generation."""

from typing import List

from langchain_core.prompts import ChatPromptTemplate

from .schema_node import _enhance_sus_schema_context
from ..application.config.table_templates import (
    build_multi_table_prompt,
    build_table_specific_prompt,
)


def build_pregeneration_hints(selected_tables: List[str], user_query: str) -> str:
    """
    Generate targeted warnings based on selected tables.
    Injected into SQL generation BEFORE calling the LLM.
    """
    hints = []

    if "socioeconomico" in selected_tables:
        hints.append(
            "🚨 SOCIOECONOMICO ALERT: long-format table. "
            "MANDATORY: add WHERE metrica = '<metric>' in EVERY query. "
            "Options: 'populacao_total', 'idhm', 'mortalidade_infantil_1ano', "
            "'bolsa_familia_total', 'esgotamento_sanitario_domicilio', 'taxa_envelhecimento'. "
            "Choosing wrong metric OR omitting it produces WRONG aggregations."
        )

    if "tempo" in selected_tables:
        hints.append(
            "🚨 TEMPO ALERT: NEVER join tempo table on computed expression. "
            "Use EXTRACT(YEAR/MONTH FROM DT_INTER) directly — NO JOIN. "
            "✅ WHERE EXTRACT(YEAR FROM \"DT_INTER\") = 2020  "
            "❌ JOIN tempo t ON EXTRACT(YEAR FROM i.\"DT_INTER\") = t.ano → CARTESIAN PRODUCT"
        )

    if "atendimentos" in selected_tables:
        hints.append(
            "🚨 ATENDIMENTOS ALERT: junction table pattern MANDATORY. "
            "internacoes i → JOIN atendimentos a ON i.\"N_AIH\" = a.\"N_AIH\" "
            "→ JOIN procedimentos p ON a.\"PROC_REA\" = p.\"PROC_REA\". "
            "NEVER reference a.\"NOME_PROC\" — that column is in procedimentos, not atendimentos."
        )

    if "especialidade" in selected_tables:
        hints.append(
            "🚨 ESPECIALIDADE ALERT: join on ESPEC code. "
            "JOIN especialidade e ON i.\"ESPEC\" = e.\"ESPEC\" → SELECT e.\"DESCRICAO\". "
            "For UTI: use WHERE \"VAL_UTI\" > 0 (NOT ESPEC BETWEEN 74 AND 83)."
        )

    if "hospital" in selected_tables:
        hints.append(
            "🚨 HOSPITAL ALERT: hospital table has only CNES, MUNIC_MOV, GESTAO, NATUREZA, NAT_JUR — NO patient counts. "
            "To count PATIENTS by municipality: COUNT(i.\"N_AIH\") from internacoes (NOT COUNT(DISTINCT h.\"CNES\") which counts hospitals). "
            "✅ 'municípios que atendem mais pacientes' → "
            "SELECT mu.nome, COUNT(i.\"N_AIH\") FROM internacoes i "
            "JOIN hospital h ON i.\"CNES\" = h.\"CNES\" "
            "JOIN municipios mu ON h.\"MUNIC_MOV\" = mu.codigo_6d "
            "GROUP BY mu.nome ORDER BY COUNT(i.\"N_AIH\") DESC. "
            "❌ COUNT(DISTINCT h.\"CNES\") → conta hospitais, NÃO pacientes."
        )

    q_lower = user_query.lower()
    import re as _re

    per_named_group_triggers = [
        "por estado", "em cada estado", "de cada estado", "para cada estado",
        "por especialidade", "em cada especialidade", "de cada especialidade",
        "por hospital", "em cada hospital", "de cada hospital", "para cada hospital",
        "por município", "em cada município", "de cada município",
        "por cidade", "em cada cidade",
        "por raça", "por sexo", "por vínculo", "por faixa etária",
        "por ano", "em cada ano", "de cada ano",
        "por mês", "em cada mês",
    ]
    per_computed_group_triggers = ["de cada", "por cada", "por grupo", "por faixa", "por nacionalidade"]
    per_group_triggers = per_named_group_triggers + per_computed_group_triggers

    top_n_context = (
        any(t in q_lower for t in ["principais", "top", "mais comuns", "mais frequentes", "mais realizados",
                                    "maior", "maior valor", "maior custo", "maior número",
                                    "maior volume", "maior quantidade", "maior taxa",
                                    "menor", "menor custo", "menor valor",
                                    "mais alto", "mais baixo", "primeiro", "líderes"])
        or bool(_re.search(r"\b\d+\s+principais\b", q_lower))
        or bool(_re.search(r"\btop[\s\-]?\d+\b", q_lower))
    )

    count_triggers = ["quantos", "número de", "total de", "quantidade de", "proporção de", "quantas"]
    if any(t in q_lower for t in count_triggers):
        hints.append(
            "📊 COUNT SEMANTICS ALERT: a pergunta pede QUANTIDADE (não listagem). "
            "✅ Use COUNT(*) ou COUNT(DISTINCT entidade) no SELECT. "
            "❌ NÃO retorne linhas individuais ou uma lista de entidades — isso viola a intenção da pergunta. "
            "Exemplo: 'Quantos hospitais nunca tiveram óbito?' → "
            "SELECT COUNT(*) AS total FROM (SELECT DISTINCT ...) sub"
        )

    antijoin_triggers = ["nunca", "nenhum", "nenhuma", "sem registro", "não aparecem", "não tiveram",
                         "nunca tiveram", "que não", "ausentes", "jamais"]
    if any(t in q_lower for t in antijoin_triggers):
        hints.append(
            "🔗 ANTI-JOIN ALERT: a pergunta expressa AUSÊNCIA ('nunca', 'sem', 'não tiveram'). "
            "✅ PREFIRA NOT EXISTS (mais seguro e performático que NOT IN): "
            "  SELECT ... FROM tabela_a a "
            "  WHERE NOT EXISTS (SELECT 1 FROM tabela_b b WHERE b.fk = a.pk AND <condição>). "
            "Alternativa: LEFT JOIN ... ON ... WHERE b.pk IS NULL. "
            "❌ EVITE NOT IN com subquery — falha silenciosamente quando a subquery retorna NULL."
        )

    pivot_triggers = ["lado a lado", "comparando", "comparar", "versus", "vs.", " x ", "para cada estado",
                      "comparação entre", "entre os estados", "nos estados"]
    two_group_pattern = bool(_re.search(
        r"\b(estado|estados?)\s+(?:do\s+)?(\w{2})\s+e\s+(?:do\s+)?(\w{2})\b",
        q_lower
    ))
    if two_group_pattern and any(t in q_lower for t in pivot_triggers + ["comparando", "lado"]):
        state_match = _re.search(
            r"\b(?:estado|estados?)?\s*(?:do\s+)?([A-Z]{2})\s+e\s+(?:do\s+)?([A-Z]{2})\b",
            user_query
        )
        g1, g2 = (state_match.group(1), state_match.group(2)) if state_match else ("A", "B")
        hints.append(
            f"↔️ PIVOT / SIDE-BY-SIDE ALERT: a pergunta pede comparação direta entre grupos "
            f"({g1} vs {g2}). "
            "✅ Use CASE WHEN pivot para retornar UMA linha por categoria com colunas separadas por grupo: "
            f"  SELECT categoria, "
            f"    ROUND(AVG(CASE WHEN grupo = '{g1}' THEN valor END), 2) AS media_{g1}, "
            f"    ROUND(AVG(CASE WHEN grupo = '{g2}' THEN valor END), 2) AS media_{g2} "
            "  FROM ... GROUP BY categoria HAVING COUNT(CASE WHEN grupo = 'X' THEN 1 END) > N; "
            "❌ NÃO retorne formato longo (linhas separadas por estado) — a pergunta pede formato LARGO."
        )

    global_avg_triggers = ["acima da média", "abaixo da média", "média nacional", "média estadual",
                           "acima da média nacional", "abaixo da média estadual", "duas vezes acima",
                           "superior à média", "inferior à média"]
    if any(t in q_lower for t in global_avg_triggers):
        hints.append(
            "📐 GLOBAL vs LOCAL AVERAGE ALERT: a pergunta compara com uma MÉDIA DE REFERÊNCIA. "
            "✅ Compute a média de referência sobre o UNIVERSO COMPLETO (antes de filtros locais), "
            "geralmente como CTE separada: "
            "  WITH media_ref AS (SELECT SUM(caso) * 100.0 / COUNT(*) AS taxa FROM tabela_fato [WHERE condição_global]), "
            "  por_entidade AS (SELECT entidade, SUM(caso) * 100.0 / COUNT(*) AS taxa_local FROM tabela_fato GROUP BY entidade HAVING ...) "
            "  SELECT e.entidade, e.taxa_local FROM por_entidade e, media_ref m "
            "  WHERE e.taxa_local > m.taxa_ref; "
            "❌ NÃO compute AVG() sobre o conjunto já filtrado — isso dá média do subgrupo, não a referência global."
        )

    agg_on_cnes_triggers = ["hospitais com mais de", "hospitais que nunca", "hospitais sem",
                            "hospitais acima", "hospitais abaixo", "hospitais com maior", "hospitais com menor"]
    if any(t in q_lower for t in agg_on_cnes_triggers):
        hints.append(
            "🏥 AGGREGATION-FIRST ALERT: para agregar internações por hospital, "
            "✅ agrupe DIRETAMENTE na tabela 'internacoes' por \"CNES\" (não faça JOIN na tabela hospital primeiro): "
            "  SELECT \"CNES\", COUNT(*) AS total FROM internacoes GROUP BY \"CNES\" HAVING ... "
            "Isso evita perder hospitais que existem em 'internacoes' mas não na tabela 'hospital'. "
            "❌ Não: SELECT h.\"CNES\" FROM hospital h JOIN internacoes i ON ... GROUP BY h.\"CNES\" HAVING ..."
        )

    has_multi_age = (
        bool(_re.search(r"menos de\s+\d+\s+anos", q_lower))
        and ("entre" in q_lower or "acima de" in q_lower or "mais de" in q_lower)
        and top_n_context
    )
    if has_multi_age:
        age_bounds = _re.findall(r"(\d+)\s+anos", q_lower)
        limit_n = _re.search(r"\b(\d+)\s+principais", q_lower)
        n_str = limit_n.group(1) if limit_n else "10"
        cutoffs = sorted(set(int(x) for x in age_bounds)) if age_bounds else [18, 64]
        if len(cutoffs) >= 2:
            c1, c2 = cutoffs[0], cutoffs[1]
            case_expr = (
                f"CASE WHEN i.\"IDADE\" < {c1} THEN 'Menor de {c1}' "
                f"WHEN i.\"IDADE\" BETWEEN {c1} AND {c2} THEN '{c1} a {c2}' "
                f"ELSE '{c2 + 1} ou mais' END"
            )
        else:
            c1 = cutoffs[0] if cutoffs else 18
            case_expr = f"CASE WHEN i.\"IDADE\" < {c1} THEN 'Menor de {c1}' ELSE '{c1} ou mais' END"
        hints.append(
            f"🚨 MULTI-AGE-GROUP TOP-N ALERT: OBRIGATÓRIO usar ROW_NUMBER OVER PARTITION BY faixa etária. "
            f"NUNCA usar LIMIT global — LIMIT limita o TOTAL de linhas, não por grupo. "
            f"Rótulos OBRIGATÓRIOS para esta pergunta: {case_expr}. "
            f"PADRÃO ESTRUTURAL OBRIGATÓRIO (adapte as colunas à pergunta):\n"
            f"  SELECT faixa_etaria, <col1>, <col2>, cnt FROM (\n"
            f"    SELECT {case_expr} AS faixa_etaria,\n"
            f"           <col1>, <col2>, COUNT(*) AS cnt,\n"
            f"           ROW_NUMBER() OVER (PARTITION BY {case_expr} ORDER BY COUNT(*) DESC) AS rn\n"
            f"    FROM internacoes i [JOIN lookup_table ON ...]\n"
            f"    GROUP BY faixa_etaria, <col1>, <col2>\n"
            f"  ) sub WHERE rn <= {n_str} ORDER BY faixa_etaria, rn;"
        )
    elif top_n_context and any(t in q_lower for t in per_group_triggers):
        named_dim = "group_col"
        named_dim_col = "group_key"
        if any(t in q_lower for t in ["por estado", "em cada estado", "de cada estado"]):
            named_dim, named_dim_col = "estado", "mu.estado"
        elif any(t in q_lower for t in ["por especialidade", "em cada especialidade"]):
            named_dim, named_dim_col = "especialidade", "e.\"DESCRICAO\""
        elif any(t in q_lower for t in ["por hospital", "em cada hospital"]):
            named_dim, named_dim_col = "hospital (CNES)", "i.\"CNES\""
        elif any(t in q_lower for t in ["por município", "em cada município"]):
            named_dim, named_dim_col = "município", "mu.nome"
        elif any(t in q_lower for t in ["por ano", "em cada ano"]):
            named_dim, named_dim_col = "ano", "EXTRACT(YEAR FROM i.\"DT_INTER\")"
        elif any(t in q_lower for t in ["por mês", "em cada mês"]):
            named_dim, named_dim_col = "mês", "EXTRACT(MONTH FROM i.\"DT_INTER\")"

        hints.append(
            f"🚨 PER-{named_dim.upper()} TOP-N ALERT: pergunta pede top-N POR {named_dim.upper()} "
            f"(PARTITION BY = {named_dim_col}). "
            "OBRIGATÓRIO: usar ROW_NUMBER() OVER (PARTITION BY <dim> ORDER BY <métrica> DESC, <tiebreaker> ASC) AS rn, "
            "depois WHERE rn <= N (ou rn = 1 para o principal). "
            "NUNCA usar LIMIT global — LIMIT limita o total de linhas, NÃO por grupo. "
            f"PADRÃO CORRETO para esta pergunta:\n"
            f"  SELECT {named_dim_col}, <valor_col>, <metrica>\n"
            f"  FROM (SELECT {named_dim_col}, <valor_col>, <metrica>,\n"
            f"               ROW_NUMBER() OVER (PARTITION BY {named_dim_col} ORDER BY <metrica> DESC, <tiebreaker> ASC) AS rn\n"
            f"        FROM internacoes i [JOINs necessários] GROUP BY {named_dim_col}, <valor_col>) sub\n"
            f"  WHERE rn <= N ORDER BY {named_dim_col}, rn;"
        )

    if top_n_context and not any("PER-ESTADO" in h for h in hints):
        two_state_match = _re.search(
            r"no\s+estado\s+(?:de\s+|do\s+|da\s+)?([A-Z]{2})\b.*?\bno\s+estado\s+(?:de\s+|do\s+|da\s+)?([A-Z]{2})\b",
            user_query,
        )
        if two_state_match:
            g1, g2 = two_state_match.group(1), two_state_match.group(2)
            limit_m = _re.search(r"\b(\d+)\s+(?:principais|diagnósticos|hospitais|procedimentos|municípios|cidades)", q_lower)
            n_str = limit_m.group(1) if limit_m else "N"
            hints.append(
                f"🚨 PER-ESTADO TOP-{n_str} (dois estados) ALERT: pergunta pede top-{n_str} "
                f"SEPARADAMENTE para cada estado ({g1} e {g2}). "
                "OBRIGATÓRIO: usar ROW_NUMBER() OVER (PARTITION BY mu.estado ORDER BY <métrica> DESC) AS rn, "
                "depois WHERE rn <= N. "
                f"NUNCA usar WHERE estado IN ('{g1}', '{g2}') com LIMIT global — "
                "isso retorna o ranking combinado, NÃO o top por estado. "
                f"PADRÃO CORRETO:\n"
                f"  SELECT mu.estado, <col>, <metrica> FROM (\n"
                f"    SELECT mu.estado, <col>, <metrica>,\n"
                f"           ROW_NUMBER() OVER (PARTITION BY mu.estado ORDER BY <metrica> DESC) AS rn\n"
                f"    FROM internacoes i JOIN municipios mu ON i.\"MUNIC_RES\" = mu.codigo_6d\n"
                f"    WHERE mu.estado IN ('{g1}', '{g2}') [AND outros filtros]\n"
                f"    GROUP BY mu.estado, <col>\n"
                f"  ) sub WHERE rn <= {n_str} ORDER BY mu.estado, rn;"
            )

    if not hints:
        return ""

    return (
        "\n\n⚠️ TABLE-SPECIFIC WARNINGS FOR THIS QUERY:\n"
        + "\n".join(f"  {hint}" for hint in hints)
        + "\n"
    )


def build_sql_generation_messages(
    user_query: str,
    schema_context: str,
    selected_tables: List[str],
) -> tuple:
    """Build the formatted messages and pre-generation hints for SQL generation."""
    schema_context = _enhance_sus_schema_context(schema_context)

    if len(selected_tables) > 1:
        table_rules = build_multi_table_prompt(selected_tables)
    else:
        table_rules = build_table_specific_prompt(selected_tables)

    pregeneration_hints = build_pregeneration_hints(selected_tables, user_query)
    if pregeneration_hints:
        table_rules = pregeneration_hints + "\n" + table_rules

    sql_prompt_template = ChatPromptTemplate.from_messages([
        ("system", """You are a PostgreSQL expert assistant for Brazilian healthcare (SIH-RS) data analysis.

        ══════════════════════════════════════════════════════════
        CRITICAL RULES — READ THESE FIRST, THEY OVERRIDE ALL ELSE
        ══════════════════════════════════════════════════════════

        RULE A — UTI/ICU: WHERE "VAL_UTI" > 0 to count or filter UTI.
        For AVG/SUM on UTI values: also require WHERE "VAL_UTI" > 0 (excludes non-ICU zeros).
        "total gasto em UTI" / "custo UTI" → SUM("VAL_UTI") WHERE "VAL_UTI" > 0
        ❌ NEVER SUM("VAL_TOT") WHERE "VAL_UTI" > 0 — VAL_TOT is the full hospitalization cost, NOT just UTI.
        "obstétricas"/"obstétrico" = ESPEC = 2 (NEVER ESPEC BETWEEN 74 AND 83).
        ✅ WHERE "ESPEC" = 2 AND "VAL_UTI" > 0

        RULE B — DEATH CAUSE vs DIAGNOSIS:
        "causa da morte"/"morreram de"/"óbitos por DOENÇA X" → JOIN cid ON i."CID_MORTE"=c."CID" WHERE i."MORTE"=true AND i."CID_MORTE" IS NOT NULL
        "diagnóstico principal"/"internado por DOENÇA X" → JOIN cid ON i."DIAG_PRINC"=c."CID"
        "resultaram em óbito" WITHOUT a specific disease → WHERE "MORTE"=true only (NO CID JOIN)
        ✅ "Quantas internações de UTI resultaram em óbito?" → WHERE "VAL_UTI" > 0 AND "MORTE" = true

        RULE C — LIMIT: add LIMIT only when question asks for top-N (e.g. "top 5"). NEVER add default LIMIT.

        RULE D — ONLY REQUESTED FILTERS: add only filters the question explicitly mentions.
        No age filter unless age asked. No year filter unless year asked. No gender unless gender asked.
        No "MORTE"=false unless question specifically asks for discharged/surviving patients.
        No WHERE col IS NOT NULL for aggregate queries (SUM/AVG/MAX/MIN already ignore NULLs).
        ✅ "Qual o total gasto?" → SELECT SUM("VAL_TOT") FROM internacoes  (NO IS NOT NULL filter)
        ❌ SELECT SUM("VAL_TOT") FROM internacoes WHERE "VAL_TOT" IS NOT NULL  ← redundant, may alter result

        RULE E — CID COLUMN:
        • Include c."CID" ONLY WHEN: question explicitly says "com código" or "código CID".
        • Default: SELECT only c."CD_DESCRICAO", GROUP BY c."CD_DESCRICAO".
        ✅ "principais causas de morte" → SELECT c."CD_DESCRICAO", COUNT(*) GROUP BY c."CD_DESCRICAO"
        ✅ "principais CIDs de entrada" → SELECT c."CD_DESCRICAO", COUNT(*) GROUP BY c."CD_DESCRICAO"
        ✅ "com código" / "código CID" → SELECT c."CID", c."CD_DESCRICAO", COUNT(*) GROUP BY c."CID", c."CD_DESCRICAO"
        ❌ "quais os CIDs de entrada" → SELECT c."CD_DESCRICAO" only (NOT c."CID" unless "com código" stated)

        RULE F — singular "qual o X mais Y" → LIMIT 1; plural "quais os N X mais Y" → LIMIT N.

        RULE G — DATE FILTERS: use EXTRACT directly on "DT_INTER", NEVER join tempo with non-equijoin.
        ✅ WHERE EXTRACT(YEAR FROM "DT_INTER") = 2020  ← use DT_INTER for year/period filters (admission date)
        Only use "DT_SAIDA" when question explicitly asks about discharge or exit date.

        RULE H — IDADE (INTEGER) vs NASC (DATE):
        "IDADE" = pre-calculated integer age column (0-130). USE FOR ALL age filters/groupings.
        "NASC" = birth date. USE ONLY when question asks about BIRTH YEAR specifically.
        ✅ WHERE "IDADE" > 60             ✅ GROUP BY "IDADE"   ✅ CASE WHEN "IDADE" < 18
        ✅ WHERE EXTRACT(YEAR FROM "NASC") < 1950  ← "nascidos antes de 1950" → use NASC
        ❌ EXTRACT(YEAR FROM AGE("NASC")) > 60   ← NEVER! use IDADE directly
        ❌ (CURRENT_DATE - "NASC") / 365 > 60    ← NEVER! use IDADE directly

        RULE I — COUNT rows vs COUNT DISTINCT values:
        "Quantos X diferentes existem cadastrados/registrados?" → COUNT(*) rows in the table (total registros).
        COUNT(DISTINCT col) only when asking "quantos valores únicos de COLUNA" or "quantas categorias distintas".
        ✅ "Quantos procedimentos diferentes existem?" → SELECT COUNT(*) FROM procedimentos
        ❌ SELECT COUNT(DISTINCT "NOME_PROC") → WRONG for "how many procedures exist"

        RULE J — PER-GROUP TOP-N: ⚠️ MANDATORY ROW_NUMBER WHEN QUESTION ASKS top-N FOR MULTIPLE GROUPS.
        Triggers: "de cada", "por cada", "por faixa", "por grupo", OR when question lists MULTIPLE explicit segments.
        ❌ NEVER use plain LIMIT for per-group queries — LIMIT limits the entire result, not per group.
        ✅ GENERIC PATTERN — top-N per categorical group (e.g. top-1 per sex):
          SELECT group_col_desc, value_col_desc, sub.cnt FROM (
            SELECT i."GROUP_COL", i."VALUE_COL", COUNT(*) AS cnt,
                   ROW_NUMBER() OVER (PARTITION BY i."GROUP_COL" ORDER BY COUNT(*) DESC, i."VALUE_COL" ASC) AS rn
            FROM internacoes i WHERE i."VALUE_COL" IS NOT NULL GROUP BY i."GROUP_COL", i."VALUE_COL"
          ) sub
          JOIN lookup_table lt ON sub."GROUP_COL" = lt."GROUP_COL"
          WHERE sub.rn = 1 ORDER BY lt."DESCRICAO";
          ⚠️ outer SELECT must use subquery alias (sub.col), NEVER inner alias (i.col)!
          ⚠️ Add secondary ORDER BY tiebreaker in ROW_NUMBER for deterministic results.
        ✅ GENERIC PATTERN — top-N per computed group (age/range segments):
          SELECT group_label, value_desc, sub.cnt FROM (
            SELECT CASE WHEN i."GROUP_MEASURE" < threshold1 THEN 'Label_A'
                        WHEN i."GROUP_MEASURE" BETWEEN threshold1 AND threshold2 THEN 'Label_B'
                        ELSE 'Label_C' END AS group_label,
                   i."VALUE_COL", COUNT(*) AS cnt,
                   ROW_NUMBER() OVER (
                     PARTITION BY CASE WHEN i."GROUP_MEASURE" < threshold1 THEN 'Label_A'
                                       WHEN i."GROUP_MEASURE" BETWEEN threshold1 AND threshold2 THEN 'Label_B'
                                       ELSE 'Label_C' END
                     ORDER BY COUNT(*) DESC
                   ) AS rn
            FROM internacoes i GROUP BY group_label, i."VALUE_COL"
          ) sub WHERE rn <= N ORDER BY group_label, rn;
          ⚠️ Use the EXACT boundaries and labels stated in the user's question (see TABLE-SPECIFIC WARNINGS).
        Age groups: when question EXPLICITLY states boundaries, use those EXACT labels.
        When NOT specified → use natural labels ('Menor', 'Adulto', 'Idoso').

        RULE K — ANTI-JOIN (absence pattern):
        When question says "nunca tiveram", "sem", "não aparece", "jamais" → use NOT EXISTS, not NOT IN.
        ✅ SELECT COUNT(*) FROM (SELECT DISTINCT "CNES" FROM internacoes i WHERE NOT EXISTS
              (SELECT 1 FROM internacoes d WHERE d."CNES" = i."CNES" AND d."MORTE" = true)) sub
        ❌ NOT IN (SELECT "CNES" FROM internacoes WHERE "MORTE" = true)  ← breaks on NULLs

        RULE L — PIVOT FORMAT (side-by-side comparison):
        When question explicitly compares two named groups side-by-side ("X vs Y", "comparar X com Y", "lado a lado"):
        ✅ Return WIDE format: SELECT categoria, AVG(CASE WHEN grp='A' THEN val END) AS media_A, AVG(CASE WHEN grp='B' THEN val END) AS media_B FROM ... GROUP BY categoria
        ❌ Do NOT return long format (one row per category+group = double the rows)

        RULE M — AGGREGATION-FIRST (count facts, not dimension rows):
        When counting/aggregating events by entity (hospital, municipality, specialty):
        ✅ GROUP BY directly on the fact table (internacoes) by the FK key, THEN join for labels:
           SELECT h_info.nome, sub.total FROM (SELECT "CNES", COUNT(*) AS total FROM internacoes GROUP BY "CNES") sub JOIN hospital h_info ...
        ❌ Do NOT: JOIN hospital first then GROUP BY — this drops CNES values that exist in internacoes but not in hospital

        RULE N — GLOBAL vs LOCAL AVERAGE:
        When filtering entities above/below an average, compute the reference from the FULL dataset:
        ✅ WITH ref AS (SELECT SUM(CASE WHEN MORTE THEN 1 ELSE 0 END)*100.0/COUNT(*) AS taxa FROM internacoes [WHERE full_scope_filter])
           ...HAVING local_taxa > (SELECT taxa FROM ref)
        ❌ Do NOT use AVG(per_group_rate) FROM already-filtered-subgroup — that computes avg-of-avgs (wrong denominator)

        RULE O — DESCRIPTION vs CODE:
        When question asks "quais métodos", "quais diagnósticos", "quais níveis de instrução" → JOIN lookup table and return DESCRICAO, not raw code.
        instrucao level → JOIN instrucao ins ON i."INSTRU" = ins."INSTRU" → SELECT ins."DESCRICAO"
        método contraceptivo → JOIN contraceptivos c ON i."CONTRACEP1" = c."CONTRACEPTIVO" → SELECT c."DESCRICAO"
        raça/cor description → JOIN raca_cor r ON i."RACA_COR" = r."RACA_COR" → SELECT r."DESCRICAO"

        DISEASE LOOKUP: table is "cid" (NOT "cid10"). NEVER hardcode CID codes (e.g. DIAG_PRINC = 'J18' is WRONG).
        Displaying diagnosis name → ALWAYS JOIN cid c ON i."DIAG_PRINC"=c."CID" → SELECT c."CD_DESCRICAO"
        ✅ "diagnóstico mais comum" → SELECT c."CD_DESCRICAO", COUNT(*) FROM internacoes i JOIN cid c ON i."DIAG_PRINC"=c."CID" GROUP BY c."CD_DESCRICAO" ORDER BY 2 DESC LIMIT 1
        ❌ SELECT i."DIAG_PRINC", COUNT(*) → returns raw CID code, NOT description
        Filtering by named disease → JOIN cid c ON i."DIAG_PRINC"=c."CID" WHERE c."CD_DESCRICAO" ILIKE '%X%'
        Category (no specific name) → WHERE "DIAG_PRINC" LIKE 'J%' (J=Respiratory, I=Cardiovascular, C=Cancer, K=Digestive)
        For cause of death by disease → JOIN cid ON i."CID_MORTE"=c."CID" (see RULE B)

        ══════════════════════════════════════════════════════════

        CORE: Use double quotes for all columns: "COLUMN_NAME". Return ONLY the SQL query.

        DATABASE SCHEMA:
        {schema_context}"""),
        ("system", "{table_specific_rules}"),
        ("human", "USER QUERY: {user_query}\n\nGenerate the SQL query:"),
    ])

    formatted_messages = sql_prompt_template.format_messages(
        schema_context=schema_context,
        table_specific_rules=table_rules,
        user_query=user_query,
    )

    import re as _re_check
    if pregeneration_hints and (
        _re_check.search(r"TOP-[N\d]", pregeneration_hints) or "MULTI-AGE" in pregeneration_hints
    ):
        from langchain_core.messages import HumanMessage as _HumanMessage

        reminder = (
            "⚠️ MANDATORY CONSTRAINT FOR THIS QUERY: You MUST use "
            "ROW_NUMBER() OVER (PARTITION BY ...) — do NOT use global LIMIT. "
            "See the SQL pattern in the TABLE-SPECIFIC WARNINGS above and follow it exactly."
        )
        formatted_messages = list(formatted_messages) + [_HumanMessage(content=reminder)]

    return formatted_messages, pregeneration_hints


__all__ = [
    "build_pregeneration_hints",
    "build_sql_generation_messages",
]
