from src.visualization.intent import detect_visualization_intent


def test_detects_explicit_bar_chart_request():
    intent = detect_visualization_intent(
        "Quais sao os 10 municipios com mais internacoes? Gere um grafico de barras."
    )

    assert intent.requested is True
    assert intent.source == "explicit_current_query"
    assert intent.uses_last_result is False
    assert intent.chart_hint == "bar"


def test_detects_followup_chart_request():
    intent = detect_visualization_intent("Agora gere um grafico de barras disso")

    assert intent.requested is True
    assert intent.source == "explicit_followup"
    assert intent.uses_last_result is True
    assert intent.chart_hint == "bar"


def test_does_not_detect_analytic_question_as_chart_request():
    intent = detect_visualization_intent("Compare os municipios com maior mortalidade")

    assert intent.requested is False
    assert intent.source == "none"


def test_does_not_detect_temporal_question_without_chart_term():
    intent = detect_visualization_intent("Qual foi a evolucao das internacoes por ano?")

    assert intent.requested is False


def test_detects_line_chart_from_linha_temporal_phrase():
    intent = detect_visualization_intent("Mostre a linha temporal das internacoes")

    assert intent.requested is True
    assert intent.chart_hint == "line"


def test_detects_english_pie_chart_request():
    intent = detect_visualization_intent("pie grafico mostrando as 3 principais causas de mortes")

    assert intent.requested is True
    assert intent.chart_hint == "pie"


def test_detects_donut_chart_english_phrase():
    intent = detect_visualization_intent("donut chart das mortes por sexo")

    assert intent.requested is True
    assert intent.chart_hint == "donut"


def test_detects_pie_chart_english_phrase():
    intent = detect_visualization_intent("pie chart of deaths by sex")

    assert intent.requested is True
    assert intent.chart_hint == "pie"


def test_detects_bar_chart_english_phrase():
    intent = detect_visualization_intent("bar chart com top 10 municipios")

    assert intent.requested is True
    assert intent.chart_hint == "bar"


def test_detects_user_pie_request_with_typo():
    intent = detect_visualization_intent(
        "gere um grafico de pizza mostrando as mortes entre homens em mulheres"
    )

    assert intent.requested is True
    assert intent.chart_hint == "pie"
    assert intent.source == "explicit_current_query"


def test_detects_kpi_and_card_as_explicit_visualization_requests():
    kpi_intent = detect_visualization_intent("Gere um KPI com o total de internacoes")
    card_intent = detect_visualization_intent("Mostre um card com o total de mortes")

    assert kpi_intent.requested is True
    assert kpi_intent.chart_hint == "kpi"
    assert card_intent.requested is True
    assert card_intent.chart_hint == "kpi"


def test_meta_chart_question_does_not_request_visualization():
    for query in [
        "me de ideias de graficos para fazer com a base",
        "que tipo de graficos eu posso fazer?",
        "exemplos de graficos para essa base",
        "quais graficos posso explorar?",
        "sugira graficos interessantes",
    ]:
        intent = detect_visualization_intent(query)
        assert intent.requested is False, f"meta query incorrectly flagged: {query}"
