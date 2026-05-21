"""Explicit visualization-intent detection."""

from __future__ import annotations

import re
import unicodedata

from .schema import ChartHint, VisualizationIntent

_CHART_PATTERNS: tuple[tuple[str, ChartHint], ...] = (
    (r"\bgrafico\s+de\s+barras?\b", "bar"),
    (r"\bgrafico\s+de\s+colunas?\b", "bar"),
    (r"\bbar\s+chart\b|\bcolumn\s+chart\b", "bar"),
    (r"\bbarras?\b|\bcolunas?\b", "bar"),
    (r"\bgrafico\s+de\s+linhas?\b", "line"),
    (r"\bline\s+chart\b", "line"),
    (r"\blinha\s+temporal\b", "line"),
    (r"\bserie\s+temporal\b", "line"),
    (r"\bscatter\b|\bdispersao\b|\bscatter\s+plot\b", "scatter"),
    (r"\bpie\s+chart\b|\bpizza\s+chart\b", "pie"),
    (r"\bdonut\s+chart\b|\brosca\s+chart\b", "donut"),
    (r"\bdonut\b|\brosca\b", "donut"),
    (r"\bpie\b|\bpizza\b", "pie"),
    (r"\barea\s+chart\b|\barea\b", "area"),
    (r"\bkpi\b|\bcard\b", "kpi"),
    (r"\btabela\b", "table"),
)

_EXPLICIT_CHART_TERMS = (
    "grafico",
    "graficos",
    "plot",
    "plotar",
    "plote",
    "visualizar em grafico",
    "visualize em grafico",
    "mostre em grafico",
    "mostre em colunas",
    "mostre em barras",
    "mostrar em colunas",
    "mostrar em barras",
    "visualize em colunas",
    "visualize em barras",
    "mostrar em grafico",
    "graficamente",
    "visualize",
    "visualizacao",
    "visualize esses dados",
    "visualizar esses dados",
    "gere um grafico",
    "gerar um grafico",
    "crie um grafico",
    "criar um grafico",
    "linha temporal",
    "pie chart",
    "bar chart",
    "column chart",
    "donut chart",
    "line chart",
    "area chart",
    "scatter chart",
    "scatter plot",
    "scatter",
    "dispersao",
    "pizza",
    "donut",
    "rosca",
    "barras",
    "colunas",
    "em linha",
    "em linhas",
    "kpi",
    "card",
    "pizza chart",
    "rosca chart",
    "chart de",
)

_FOLLOWUP_REFERENCES = (
    "disso",
    "dessa resposta",
    "essa resposta",
    "resultado anterior",
    "ultimo resultado",
    "ultima resposta",
    "esses dados",
    "esses resultados",
    "isso",
)

# Phrases where the user is *talking about* charts in the abstract instead of
# requesting one to be generated. These suppress visualization intent even when
# a chart-related term ("grafico", "chart") is present.
_META_CHART_PHRASES = (
    "ideias de grafico",
    "ideias de graficos",
    "que tipo de grafico",
    "que tipos de grafico",
    "que graficos",
    "quais graficos",
    "exemplos de grafico",
    "exemplos de graficos",
    "tipos de grafico",
    "tipos de graficos",
    "sugestoes de grafico",
    "sugestoes de graficos",
    "sugira graficos",
    "sugira um grafico",
    "que chart",
    "what charts",
    "chart ideas",
)


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()


def _detect_chart_hint(normalized_query: str) -> ChartHint:
    for pattern, chart_hint in _CHART_PATTERNS:
        if re.search(pattern, normalized_query):
            return chart_hint
    return "auto"


def detect_visualization_intent(user_query: str) -> VisualizationIntent:
    """Detect whether the user explicitly requested a chart.

    The detector is intentionally conservative. Analytical words such as
    "compare", "evolucao", or "ranking" are not enough to request a chart.
    """

    normalized_query = _normalize(user_query)
    if not normalized_query:
        return VisualizationIntent(requested=False)

    if any(meta in normalized_query for meta in _META_CHART_PHRASES):
        return VisualizationIntent(requested=False)

    requested = any(term in normalized_query for term in _EXPLICIT_CHART_TERMS)
    if not requested:
        return VisualizationIntent(requested=False)

    uses_last_result = any(reference in normalized_query for reference in _FOLLOWUP_REFERENCES)
    chart_hint = _detect_chart_hint(normalized_query)
    source = "explicit_followup" if uses_last_result else "explicit_current_query"
    reason = "Usuario pediu explicitamente visualizacao em grafico"
    if chart_hint != "auto":
        reason = f"Usuario pediu explicitamente grafico do tipo {chart_hint}"

    return VisualizationIntent(
        requested=True,
        source=source,
        uses_last_result=uses_last_result,
        chart_hint=chart_hint,
        reason=reason,
    )
