"""Small CLI wrapper around the simple SQL chatbot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simple DATASUS text-to-SQL chatbot")
    parser.add_argument("--query", "-q", help="Question to answer")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model name")
    parser.add_argument("--db-url", help="DuckDB SQLAlchemy URL")
    parser.add_argument("--environment", default="development")
    parser.add_argument("--debug-steps", action="store_true", help="Print debug metadata")
    parser.add_argument("--health-check", action="store_true", help="Check runtime health")
    return parser


def build_orchestrator(args: argparse.Namespace):
    from src.agent.orchestrator import create_orchestrator

    return create_orchestrator(
        model_name=args.model,
        environment=args.environment,
        database_url=args.db_url,
    )


def print_result(result: dict[str, Any], *, include_debug: bool = False) -> None:
    print(result.get("response") or result.get("error_message") or "Sem resposta.")
    if result.get("sql_query"):
        print()
        print("SQL:")
        print(result["sql_query"])
    if include_debug:
        print()
        print("DEBUG:")
        print(json.dumps(result.get("metadata") or {}, ensure_ascii=False, indent=2, default=str))


def run_once(args: argparse.Namespace) -> int:
    orchestrator = build_orchestrator(args)
    result = orchestrator.process_query(args.query, streaming=args.debug_steps)
    if isinstance(result, list):
        simple_state = result[-1].get("simple_agent", {})
        result = simple_state.get("simple_result", {})
    print_result(result, include_debug=args.debug_steps)
    return 0 if result.get("success") else 1


def run_interactive(args: argparse.Namespace) -> int:
    orchestrator = build_orchestrator(args)
    print("Simple DATASUS text-to-SQL chatbot. Type 'exit' to finish.")
    while True:
        query = input("> ").strip()
        if query.lower() in {"exit", "quit", "sair"}:
            return 0
        if not query:
            continue
        result = orchestrator.process_query(query, streaming=args.debug_steps)
        if isinstance(result, list):
            simple_state = result[-1].get("simple_agent", {})
            result = simple_state.get("simple_result", {})
        print_result(result, include_debug=args.debug_steps)
        print()


def main() -> int:
    args = create_parser().parse_args()
    orchestrator = None
    if args.health_check:
        orchestrator = build_orchestrator(args)
        print(json.dumps(orchestrator.health_check(), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.query:
        return run_once(args)
    return run_interactive(args)


if __name__ == "__main__":
    raise SystemExit(main())
