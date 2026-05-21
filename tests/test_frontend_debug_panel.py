from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_frontend_debug_toggle_sends_debug_flag_and_renders_panel() -> None:
    index_html = (ROOT / "frontend/public/index.html").read_text(encoding="utf-8")
    app_js = (ROOT / "frontend/public/app.js").read_text(encoding="utf-8")
    styles = (ROOT / "frontend/public/styles.css").read_text(encoding="utf-8")

    assert 'id="debugToggle"' in index_html
    assert "debug: isDebugEnabled" in app_js
    assert "function createDebugPanel" in app_js
    assert "debug-panel" in styles


def test_frontend_proxy_only_requests_sql_and_metadata_when_debug_enabled() -> None:
    server_js = (ROOT / "frontend/server.js").read_text(encoding="utf-8")

    assert "const debugEnabled = Boolean(debug);" in server_js
    assert "include_sql: debugEnabled" in server_js
    assert "debug: debugEnabled" in server_js
    assert "metadata: debugEnabled ? response.metadata || {} : {}" in server_js


def test_frontend_preserves_debug_payload_on_error_messages() -> None:
    app_js = (ROOT / "frontend/public/app.js").read_text(encoding="utf-8")
    server_js = (ROOT / "frontend/server.js").read_text(encoding="utf-8")

    assert "const errorMessage = sanitizeAgentError(data.error_message || data.answer || data.response" in app_js
    assert "addMessage(errorMessage, 'error', {" in app_js
    assert "debug: isDebugEnabled ? data.debug || null : null" in app_js
    assert "error_message: sanitizeAgentError(response.error_message || (!response.success ? response.answer || response.response : null))" in server_js


def test_frontend_sanitizes_internal_agent_errors() -> None:
    app_js = (ROOT / "frontend/public/app.js").read_text(encoding="utf-8")
    server_js = (ROOT / "frontend/server.js").read_text(encoding="utf-8")

    assert "SAFE_AGENT_ERROR_MESSAGE" in app_js
    assert "INTERNAL_AGENT_ERROR_PATTERNS" in app_js
    assert "function sanitizeAgentError" in app_js
    assert "SEMANTIC PLAN ERROR" in app_js
    assert "sanitizeAgentError(error.message || 'Internal server error')" in server_js
