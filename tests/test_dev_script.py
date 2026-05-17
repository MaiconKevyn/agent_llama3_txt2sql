from pathlib import Path

from scripts import dev


def test_api_command_uses_uvicorn_app_target():
    command = dev.build_api_command(
        python_executable="/venv/bin/python",
        host="127.0.0.1",
        port=8001,
        reload_api=True,
    )

    assert command == [
        "/venv/bin/python",
        "-m",
        "uvicorn",
        "src.interfaces.api.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8001",
        "--reload",
    ]


def test_frontend_env_points_to_api_v1_endpoint():
    env = dev.build_frontend_env(
        {"NODE_ENV": "test"},
        api_url="http://localhost:8000/api/v1",
        host="127.0.0.1",
        port=3001,
    )

    assert env["API_BASE_URL"] == "http://localhost:8000/api/v1"
    assert env["HOST"] == "127.0.0.1"
    assert env["PORT"] == "3001"
    assert env["NODE_ENV"] == "test"


def test_public_host_converts_wildcard_for_browser_urls():
    assert dev.public_host("0.0.0.0") == "localhost"
    assert dev.public_host("127.0.0.1") == "127.0.0.1"
    assert dev.api_base_url("0.0.0.0", 8000) == "http://localhost:8000/api/v1"


def test_parse_env_file_ignores_comments_and_quotes(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                "OPENAI_API_KEY='sk-test'",
                'DATABASE_PATH="duckdb:////tmp/sihrd5.duckdb"',
                "EMPTY=",
            ]
        ),
        encoding="utf-8",
    )

    assert dev.parse_env_file(env_file) == {
        "OPENAI_API_KEY": "sk-test",
        "DATABASE_PATH": "duckdb:////tmp/sihrd5.duckdb",
        "EMPTY": "",
    }


def test_collect_config_warnings_reports_missing_env_and_placeholders(tmp_path: Path):
    warnings = dev.collect_config_warnings(tmp_path, {})

    assert "Missing .env. Create one with: cp .env.example .env" in warnings
    assert "OPENAI_API_KEY is missing or still uses the example placeholder." in warnings
    assert "DATABASE_PATH or DATABASE_URL must point to a reachable DuckDB database." in warnings
