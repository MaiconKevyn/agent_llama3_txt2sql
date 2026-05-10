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
