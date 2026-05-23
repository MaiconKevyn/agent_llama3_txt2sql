from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_assistant_chart_messages_use_wide_layout_class() -> None:
    app_js = (ROOT / "frontend/public/app.js").read_text(encoding="utf-8")
    styles = (ROOT / "frontend/public/styles.css").read_text(encoding="utf-8")

    assert "message.classList.add('message-has-chart')" in app_js
    assert ".message-has-chart" in styles
    assert "grid-template-columns: 34px minmax(0, 1fr)" in styles
    assert ".message-has-chart .message-content" in styles


def test_echarts_charts_share_default_visual_height() -> None:
    styles = (ROOT / "frontend/public/styles.css").read_text(encoding="utf-8")

    assert ".echarts-chart" in styles
    assert "min-height: 360px" in styles
    assert ".echarts-chart-pie,\n.echarts-chart-donut" not in styles


def test_frontend_renders_chart_subtitle_summary_and_footnote() -> None:
    app_js = (ROOT / "frontend/public/app.js").read_text(encoding="utf-8")
    styles = (ROOT / "frontend/public/styles.css").read_text(encoding="utf-8")

    assert "chart-subtitle" in app_js
    assert "chart-summary" in app_js
    assert "chart-footnote" in app_js
    assert ".chart-subtitle" in styles
    assert ".chart-summary" in styles
    assert ".chart-footnote" in styles


def test_frontend_formats_chart_values_from_echarts_metadata() -> None:
    app_js = (ROOT / "frontend/public/app.js").read_text(encoding="utf-8")

    assert "formatChartValue" in app_js
    assert "_valueFormat" in app_js
    assert "currency_brl" in app_js
    assert "percent" in app_js


def test_assistant_messages_keep_source_question_for_chart_generation() -> None:
    app_js = (ROOT / "frontend/public/app.js").read_text(encoding="utf-8")

    assert "sourceQuestion: message" in app_js
    assert "canGenerateChartFromMessage" in app_js
    assert "buildChartFollowupQuestion" in app_js


def test_frontend_renders_generate_chart_action_for_text_answers() -> None:
    app_js = (ROOT / "frontend/public/app.js").read_text(encoding="utf-8")
    styles = (ROOT / "frontend/public/styles.css").read_text(encoding="utf-8")

    assert "createMessageActionBar" in app_js
    assert "requestChartForMessage" in app_js
    assert "Gerar grafico" in app_js
    assert "message-action-bar" in styles
    assert "generate-chart-btn" in styles


def test_generate_chart_action_does_not_append_user_chat_message() -> None:
    app_js = (ROOT / "frontend/public/app.js").read_text(encoding="utf-8")

    assert "function requestChartForMessage" in app_js
    assert "buildChartFollowupQuestion" in app_js
    assert "addMessage(chartQuestion, 'user')" not in app_js
    assert "appendChartToExistingMessage" in app_js


def test_generated_chart_is_persisted_on_existing_message() -> None:
    app_js = (ROOT / "frontend/public/app.js").read_text(encoding="utf-8")

    assert "messageData.metadata.chart = chartPayload" in app_js
    assert "messageData.metadata.chartGenerationState = 'done'" in app_js
    assert "saveMessageHistory();" in app_js


def test_generate_chart_action_has_accessible_loading_and_error_states() -> None:
    app_js = (ROOT / "frontend/public/app.js").read_text(encoding="utf-8")
    styles = (ROOT / "frontend/public/styles.css").read_text(encoding="utf-8")

    assert "aria-label', 'Gerar grafico para esta resposta'" in app_js
    assert "fa-spinner fa-spin" in app_js
    assert "chart-inline-error" in app_js
    assert ".generate-chart-btn.is-loading" in styles
    assert ".chart-inline-error" in styles


def test_generate_chart_action_requests_cached_result_chart() -> None:
    app_js = (ROOT / "frontend/public/app.js").read_text(encoding="utf-8")

    assert "chart_from_last_result: true" in app_js
    assert "Consulta original:" not in app_js


def test_generate_chart_action_uses_chart_reason_when_available() -> None:
    app_js = (ROOT / "frontend/public/app.js").read_text(encoding="utf-8")

    assert "extractChartFailureReason" in app_js
    assert "data.chart" in app_js
    assert "data.chart.spec" in app_js
