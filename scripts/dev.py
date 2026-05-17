#!/usr/bin/env python3
"""Start the local API and web UI with one command."""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"
DEFAULT_API_PORT = 8000
DEFAULT_FRONTEND_PORT = 3000
DEFAULT_HOST = "0.0.0.0"
PLACEHOLDER_MARKERS = (
    "sk-your_openai_key_here",
    "your_password",
    "/path/to/local.duckdb",
    "/absolute/path/to/sihrd5.duckdb",
)


def public_host(host: str) -> str:
    """Return a browser-friendly host for wildcard bind addresses."""
    return "localhost" if host in {"0.0.0.0", "::"} else host


def api_base_url(host: str, port: int) -> str:
    return f"http://{public_host(host)}:{port}/api/v1"


def build_api_command(
    *,
    python_executable: str,
    host: str,
    port: int,
    reload_api: bool,
) -> list[str]:
    command = [
        python_executable,
        "-m",
        "uvicorn",
        "src.interfaces.api.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload_api:
        command.append("--reload")
    return command


def build_frontend_command() -> list[str]:
    return ["npm", "--prefix", str(FRONTEND_DIR), "start"]


def build_frontend_env(
    base_env: Mapping[str, str],
    *,
    api_url: str,
    host: str,
    port: int,
) -> dict[str, str]:
    env = dict(base_env)
    env.update(
        {
            "API_BASE_URL": api_url,
            "HOST": host,
            "PORT": str(port),
            "NODE_ENV": env.get("NODE_ENV", "development"),
        }
    )
    return env


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def collect_config_warnings(root: Path, env: Mapping[str, str]) -> list[str]:
    env_file = root / ".env"
    file_values = parse_env_file(env_file)
    merged = {**file_values, **dict(env)}
    warnings: list[str] = []

    if not env_file.exists():
        warnings.append("Missing .env. Create one with: cp .env.example .env")

    api_key = merged.get("OPENAI_API_KEY", "")
    if not api_key or any(marker in api_key for marker in PLACEHOLDER_MARKERS):
        warnings.append("OPENAI_API_KEY is missing or still uses the example placeholder.")

    database_url = merged.get("DATABASE_URL", "")
    database_path = merged.get("DATABASE_PATH", "")
    if not database_url and not database_path:
        warnings.append("DATABASE_PATH or DATABASE_URL must point to a reachable DuckDB database.")
    elif any(marker in database_url for marker in PLACEHOLDER_MARKERS) or any(
        marker in database_path for marker in PLACEHOLDER_MARKERS
    ):
        warnings.append("Database configuration still contains example placeholder values.")

    return warnings


def is_port_available(host: str, port: int) -> bool:
    bind_host = "0.0.0.0" if host in {"0.0.0.0", "::"} else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((bind_host, port))
        except OSError:
            return False
    return True


def ensure_frontend_dependencies(*, skip_install: bool) -> int:
    if shutil.which("npm") is None:
        print("[error] npm was not found. Install Node.js >=16 and npm >=8.", file=sys.stderr)
        return 2

    if (FRONTEND_DIR / "node_modules").exists():
        return 0

    if skip_install:
        print(
            "[error] frontend/node_modules is missing. Run: npm --prefix frontend install",
            file=sys.stderr,
        )
        return 2

    package_lock = FRONTEND_DIR / "package-lock.json"
    command = ["npm", "ci"] if package_lock.exists() else ["npm", "install"]
    print(f"[setup] Installing frontend dependencies with: {' '.join(command)}")
    completed = subprocess.run(command, cwd=FRONTEND_DIR, check=False)
    return completed.returncode


def _start_process(
    *,
    name: str,
    command: Sequence[str],
    cwd: Path,
    env: Mapping[str, str] | None = None,
) -> subprocess.Popen:
    print(f"[dev] Starting {name}: {' '.join(command)}")
    return subprocess.Popen(
        list(command),
        cwd=cwd,
        env=dict(env) if env is not None else None,
        start_new_session=os.name != "nt",
    )


def _terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except ProcessLookupError:
        return


def stop_processes(processes: Sequence[subprocess.Popen]) -> None:
    for process in processes:
        _terminate_process(process)

    deadline = time.monotonic() + 8
    for process in processes:
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        if process.poll() is None:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()


def wait_for_services(processes: Sequence[tuple[str, subprocess.Popen]]) -> int:
    try:
        while True:
            for name, process in processes:
                code = process.poll()
                if code is not None:
                    print(f"[dev] {name} exited with code {code}. Stopping remaining services.")
                    stop_processes([item[1] for item in processes])
                    return int(code)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[dev] Stopping API and frontend...")
        stop_processes([item[1] for item in processes])
        return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the DataVisSUS API and web UI together for local development."
    )
    parser.add_argument("--api-host", default=DEFAULT_HOST)
    parser.add_argument("--api-port", type=int, default=DEFAULT_API_PORT)
    parser.add_argument("--frontend-host", default=DEFAULT_HOST)
    parser.add_argument("--frontend-port", type=int, default=DEFAULT_FRONTEND_PORT)
    parser.add_argument(
        "--api-base-url",
        default=None,
        help="Override the URL used by the frontend proxy to reach the API.",
    )
    parser.add_argument(
        "--reload-api",
        action="store_true",
        help="Run uvicorn with --reload for backend development.",
    )
    parser.add_argument(
        "--skip-npm-install",
        action="store_true",
        help="Do not install frontend dependencies automatically when node_modules is missing.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    if importlib.util.find_spec("uvicorn") is None:
        print("[error] uvicorn is not installed. Run: uv sync --extra dev", file=sys.stderr)
        return 2

    if not is_port_available(args.api_host, args.api_port):
        print(f"[error] API port {args.api_port} is already in use.", file=sys.stderr)
        return 2
    if not is_port_available(args.frontend_host, args.frontend_port):
        print(f"[error] Frontend port {args.frontend_port} is already in use.", file=sys.stderr)
        return 2

    frontend_setup_code = ensure_frontend_dependencies(skip_install=args.skip_npm_install)
    if frontend_setup_code != 0:
        return frontend_setup_code

    for warning in collect_config_warnings(ROOT, os.environ):
        print(f"[warn] {warning}")

    frontend_api_url = args.api_base_url or api_base_url(args.api_host, args.api_port)
    frontend_env = build_frontend_env(
        os.environ,
        api_url=frontend_api_url,
        host=args.frontend_host,
        port=args.frontend_port,
    )

    api_process = _start_process(
        name="API",
        command=build_api_command(
            python_executable=sys.executable,
            host=args.api_host,
            port=args.api_port,
            reload_api=args.reload_api,
        ),
        cwd=ROOT,
    )
    frontend_process = _start_process(
        name="frontend",
        command=build_frontend_command(),
        cwd=ROOT,
        env=frontend_env,
    )

    print("")
    print("[dev] Services are starting:")
    print(f"[dev] API:      http://{public_host(args.api_host)}:{args.api_port}")
    print(f"[dev] Swagger:  http://{public_host(args.api_host)}:{args.api_port}/docs")
    print(f"[dev] Frontend: http://{public_host(args.frontend_host)}:{args.frontend_port}")
    print("[dev] Press Ctrl+C to stop both services.")
    print("")

    return wait_for_services((("API", api_process), ("frontend", frontend_process)))


if __name__ == "__main__":
    raise SystemExit(main())
