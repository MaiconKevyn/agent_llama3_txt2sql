from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import traceback
from collections import Counter
from datetime import datetime
from multiprocessing import Process, Queue
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.agent.orchestrator import LangGraphOrchestrator, _orchestrator_config_from_env
from src.application.config.simple_config import ApplicationConfig

QUESTIONS: list[dict[str, str]] = [
    {
        "id": "Q001",
        "category": "volume_temporal",
        "question": "Quantas internações foram registradas em 2021?",
    },
    {
        "id": "Q002",
        "category": "mortalidade",
        "question": "Quantos óbitos hospitalares ocorreram em 2021?",
    },
    {
        "id": "Q003",
        "category": "mortalidade",
        "question": "Qual foi a principal causa de morte em 2021?",
    },
    {
        "id": "Q004",
        "category": "mortalidade",
        "question": "Quais foram os 5 diagnósticos com mais óbitos entre mulheres em 2021?",
    },
    {
        "id": "Q005",
        "category": "pediatria",
        "question": "Quais foram os 5 diagnósticos principais mais comuns em crianças menores de 5 anos?",
    },
    {
        "id": "Q006",
        "category": "idosos",
        "question": "Qual foi a taxa de mortalidade hospitalar em pacientes com 65 anos ou mais em 2021?",
    },
    {
        "id": "Q007",
        "category": "permanencia",
        "question": "Qual foi o tempo médio de permanência por especialidade médica em 2020?",
    },
    {
        "id": "Q008",
        "category": "uti",
        "question": "Quantas internações tiveram uso de UTI e qual foi a taxa de mortalidade dessas internações?",
    },
    {
        "id": "Q009",
        "category": "custo",
        "question": "Qual foi o valor total gasto com UTI por estado em 2021?",
    },
    {
        "id": "Q010",
        "category": "geografia",
        "question": "Quais municípios do Maranhão tiveram mais internações obstétricas em 2021?",
    },
    {
        "id": "Q011",
        "category": "perfil",
        "question": "Como foi a distribuição por raça/cor dos óbitos hospitalares no Rio Grande do Sul em 2021?",
    },
    {
        "id": "Q012",
        "category": "perfil",
        "question": "Qual foi a idade média dos pacientes internados por doenças cardiovasculares em 2021?",
    },
    {
        "id": "Q013",
        "category": "sazonalidade",
        "question": "As internações por doenças respiratórias aumentaram no inverno no Rio Grande do Sul?",
    },
    {
        "id": "Q014",
        "category": "sazonalidade",
        "question": "Qual foi a evolução mensal das internações por dengue em 2021?",
    },
    {
        "id": "Q015",
        "category": "procedimentos",
        "question": "Quais foram os procedimentos mais frequentes nos hospitais de São Luís em 2021?",
    },
    {
        "id": "Q016",
        "category": "hospital",
        "question": "Quais hospitais tiveram a maior taxa de mortalidade em 2021 considerando apenas hospitais com mais de 500 internações?",
    },
    {
        "id": "Q017",
        "category": "custo",
        "question": "Qual foi o custo médio de internação por diagnóstico principal em homens acima de 60 anos?",
    },
    {
        "id": "Q018",
        "category": "comparacao",
        "question": "Compare a taxa de mortalidade hospitalar entre Maranhão e Rio Grande do Sul em 2021.",
    },
    {
        "id": "Q019",
        "category": "perfil",
        "question": "Quais diagnósticos principais foram mais comuns entre pacientes indígenas?",
    },
    {
        "id": "Q020",
        "category": "catalogo",
        "question": "Quantos códigos CID existem no catálogo de diagnósticos?",
    },
    {
        "id": "Q021",
        "category": "covid",
        "question": "Qual proporção dos óbitos hospitalares de 2021 teve COVID-19 como diagnóstico principal?",
    },
    {
        "id": "Q022",
        "category": "tendencia",
        "question": "Como evoluíram os óbitos em internações com UTI nos últimos 5 anos disponíveis?",
    },
    {
        "id": "Q023",
        "category": "permanencia",
        "question": "Qual especialidade teve maior tempo médio de permanência entre pacientes que morreram?",
    },
    {
        "id": "Q024",
        "category": "procedimentos",
        "question": "Quais procedimentos aparecem com maior frequência em internações obstétricas?",
    },
    {
        "id": "Q025",
        "category": "geografia",
        "question": "Existe diferença de internações entre pacientes de área rural e urbana?",
    },
    {
        "id": "Q026",
        "category": "vacinacao",
        "question": "Qual foi a cobertura vacinal dos pacientes que morreram por COVID-19?",
    },
    {
        "id": "Q027",
        "category": "laboratorio",
        "question": "Quais exames laboratoriais mais apareceram em internações por anemia?",
    },
    {
        "id": "Q028",
        "category": "medicacao",
        "question": "Quais antibióticos foram mais usados em pacientes internados por pneumonia?",
    },
    {
        "id": "Q029",
        "category": "readmissao",
        "question": "Qual foi a taxa de reinternação em até 30 dias após alta hospitalar?",
    },
    {
        "id": "Q030",
        "category": "comorbidade",
        "question": "Quantos pacientes internados tinham diabetes e hipertensão ao mesmo tempo?",
    },
    {
        "id": "Q031",
        "category": "uti",
        "question": "Qual foi a mortalidade por tipo de UTI em 2021?",
    },
    {
        "id": "Q032",
        "category": "perfil",
        "question": "A mortalidade hospitalar varia por escolaridade do paciente?",
    },
    {
        "id": "Q033",
        "category": "perfil",
        "question": "Como a mortalidade varia por vínculo previdenciário?",
    },
    {
        "id": "Q034",
        "category": "custo",
        "question": "Quais hospitais tiveram maior custo por dia de internação em 2021?",
    },
    {
        "id": "Q035",
        "category": "geografia",
        "question": "Quantas internações ocorreram fora do estado de residência do paciente?",
    },
    {
        "id": "Q036",
        "category": "obstetricia",
        "question": "Qual foi a quantidade de partos cesáreos por estado em 2021?",
    },
    {
        "id": "Q037",
        "category": "neonatal",
        "question": "Quantos óbitos neonatais ocorreram em internações de recém-nascidos?",
    },
    {
        "id": "Q038",
        "category": "socioeconomico",
        "question": "Municípios com menor renda tiveram maior mortalidade infantil hospitalar?",
    },
    {
        "id": "Q039",
        "category": "socioeconomico",
        "question": "Existe relação entre IDH municipal e taxa de internação por doenças respiratórias?",
    },
    {
        "id": "Q040",
        "category": "programas_sociais",
        "question": "Beneficiários do Bolsa Família tiveram mais internações por desnutrição?",
    },
    {
        "id": "Q041",
        "category": "saneamento",
        "question": "Municípios com pior saneamento tiveram mais internações por diarreia?",
    },
    {
        "id": "Q042",
        "category": "populacao",
        "question": "Qual estado teve maior taxa de internações por 100 mil habitantes em 2021?",
    },
    {
        "id": "Q043",
        "category": "respiratorio",
        "question": "Quantos pacientes internados por pneumonia morreram em 2021?",
    },
    {
        "id": "Q044",
        "category": "tempo_ate_evento",
        "question": "Qual foi o tempo médio entre internação e óbito em 2021?",
    },
    {
        "id": "Q045",
        "category": "cid",
        "question": "Quais capítulos CID concentraram mais internações em 2021?",
    },
    {
        "id": "Q046",
        "category": "qualidade_dado",
        "question": "Qual percentual dos óbitos de 2021 está sem informação de raça/cor?",
    },
    {
        "id": "Q047",
        "category": "infectologia",
        "question": "Quantas internações por HIV ou AIDS ocorreram em 2021?",
    },
    {
        "id": "Q048",
        "category": "infectologia",
        "question": "Qual foi a tendência anual de mortalidade por septicemia?",
    },
    {
        "id": "Q049",
        "category": "qualidade_dado",
        "question": "Quantas internações estão sem diagnóstico principal preenchido?",
    },
    {
        "id": "Q050",
        "category": "seguimento",
        "question": "Qual foi a sobrevida dos pacientes um ano após a alta hospitalar?",
    },
]


def _run_git(args: list[str]) -> str:
    try:
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _compact_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "current_model",
        "environment",
        "session_id",
        "query_number",
        "orchestrator_execution_time",
        "table_selection",
        "semantic_plan",
        "semantic_validation",
        "llamaindex_enabled",
        "llamaindex_mode",
        "llamaindex_selected_tables",
        "llamaindex_error",
        "raw_selected_tables",
        "validated_selected_tables",
        "workflow_metrics",
        "latency_by_component",
        "multi_query",
    ]
    return {key: _json_safe(metadata.get(key)) for key in keys if key in metadata}


def _classify_failure(result: dict[str, Any], response: str, error: str) -> str | None:
    if result.get("success"):
        if "não foi possível" in response.lower() or "nao foi possivel" in response.lower():
            return "soft_failure_in_response"
        return None

    text = f"{error}\n{response}".lower()
    if "semantic plan error" in text:
        return "semantic_plan_validation"
    if "catalog error" in text or "binder error" in text or "does not exist" in text:
        return "sql_schema_or_execution"
    if "unsupported" in text or "não há" in text or "nao ha" in text or "não existe" in text:
        return "unsupported_data_or_metric"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "workflow execution failed" in text:
        return "workflow_exception"
    return "agent_error"


def _status(result: dict[str, Any], response: str, failure_category: str | None) -> str:
    if not result.get("success"):
        return "incorrect_error"
    if failure_category == "soft_failure_in_response":
        return "incorrect_soft_failure"
    rows = result.get("results") or []
    if not rows:
        return "correct_no_rows"
    return "correct"


def _extract_item(
    question_item: dict[str, str], result: dict[str, Any], elapsed: float
) -> dict[str, Any]:
    response = str(result.get("response") or "")
    error = str(result.get("error_message") or result.get("error") or "")
    failure_category = _classify_failure(result, response, error)
    rows = result.get("results") or []
    metadata = result.get("metadata") or {}
    return {
        **question_item,
        "status": _status(result, response, failure_category),
        "success": bool(result.get("success")),
        "failure_category": failure_category,
        "error_message": error,
        "response": response,
        "sql_query": result.get("sql_query"),
        "row_count": len(rows),
        "results_preview": rows[:5],
        "execution_time_seconds": round(float(result.get("execution_time") or elapsed), 3),
        "metadata": _compact_metadata(metadata),
    }


def _escape_md(value: Any, max_len: int = 220) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\n", " ").replace("|", "\\|")
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _failure_reason(item: dict[str, Any]) -> str:
    category = item.get("failure_category")
    error = item.get("error_message") or item.get("response") or ""
    if category == "semantic_plan_validation":
        return "O validador semântico rejeitou o SQL gerado; normalmente há filtro, granularidade, top-N ou contrato temporal incompatível com a pergunta."
    if category == "sql_schema_or_execution":
        return "O SQL referenciou tabela/coluna fora do schema disponível ou falhou no DuckDB."
    if category == "unsupported_data_or_metric":
        return "A pergunta parece exigir dado ou métrica que não existe no banco atual."
    if category == "soft_failure_in_response":
        return "O agente retornou sucesso técnico, mas a resposta textual indica que não conseguiu responder plenamente."
    if category == "timeout":
        return "A execução excedeu o tempo esperado."
    if category == "workflow_exception":
        return "O workflow lançou exceção antes de uma resposta válida."
    return _escape_md(error, 350) or "Erro não categorizado."


def _worker_run_question(
    item: dict[str, str],
    run_id: str,
    output_queue: Queue,
) -> None:
    question_started = time.time()
    try:
        load_dotenv()
        app_config = ApplicationConfig()
        orchestrator_config = _orchestrator_config_from_env()
        orchestrator = LangGraphOrchestrator(
            app_config=app_config,
            orchestrator_config=orchestrator_config,
            environment="production",
        )
        raw_result = orchestrator.process_query(
            item["question"],
            session_id=f"{run_id}_{item['id']}",
            run_name=f"{run_id}_{item['id']}",
            tags=["health_exhaustion", item["category"]],
            metadata={"evaluation_id": run_id, "question_id": item["id"]},
        )
    except Exception as exc:
        raw_result = {
            "success": False,
            "response": "",
            "sql_query": None,
            "results": [],
            "error_message": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "execution_time": time.time() - question_started,
        }
    output_queue.put(_extract_item(item, raw_result, elapsed=time.time() - question_started))


def _timeout_item(item: dict[str, str], timeout_seconds: int) -> dict[str, Any]:
    return {
        **item,
        "status": "incorrect_timeout",
        "success": False,
        "failure_category": "timeout",
        "error_message": f"Question exceeded timeout of {timeout_seconds} seconds.",
        "response": "",
        "sql_query": None,
        "row_count": 0,
        "results_preview": [],
        "execution_time_seconds": float(timeout_seconds),
        "metadata": {},
    }


def _worker_error_item(item: dict[str, str], message: str) -> dict[str, Any]:
    return {
        **item,
        "status": "incorrect_error",
        "success": False,
        "failure_category": "workflow_exception",
        "error_message": message,
        "response": "",
        "sql_query": None,
        "row_count": 0,
        "results_preview": [],
        "execution_time_seconds": 0.0,
        "metadata": {},
    }


def _run_question_with_timeout(
    item: dict[str, str],
    run_id: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    output_queue: Queue = Queue(maxsize=1)
    process = Process(target=_worker_run_question, args=(item, run_id, output_queue))
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join(5)
        return _timeout_item(item, timeout_seconds)
    if process.exitcode not in (0, None):
        return _worker_error_item(item, f"Worker exited with code {process.exitcode}.")
    if output_queue.empty():
        return _worker_error_item(item, "Worker completed without returning a result.")
    return output_queue.get()


def _write_markdown_report(payload: dict[str, Any], report_path: Path) -> None:
    results = payload["results"]
    status_counts = Counter(item["status"] for item in results)
    failure_counts = Counter(
        item["failure_category"] for item in results if item.get("failure_category")
    )
    error_items = [
        item
        for item in results
        if item["status"].startswith("incorrect")
        or item.get("failure_category") == "unsupported_data_or_metric"
    ]

    lines = [
        "# Health Agent Exhaustion Test",
        "",
        f"- Run: `{payload['run_id']}`",
        f"- Total questions: {len(results)}",
        f"- Correct executions: {status_counts.get('correct', 0)}",
        f"- Correct with no rows: {status_counts.get('correct_no_rows', 0)}",
        f"- Incorrect or not answered: {len(error_items)}",
        f"- Total elapsed seconds: {payload['elapsed_seconds']}",
        f"- Branch: `{payload['git']['branch']}`",
        f"- Commit: `{payload['git']['commit']}`",
        f"- Database: `{payload['database_path']}`",
        "",
        "## Status Summary",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in sorted(status_counts.items()):
        lines.append(f"| `{status}` | {count} |")

    lines.extend(["", "## Failure Categories", "", "| Category | Count |", "|---|---:|"])
    if failure_counts:
        for category, count in sorted(failure_counts.items()):
            lines.append(f"| `{category}` | {count} |")
    else:
        lines.append("| none | 0 |")

    lines.extend(
        [
            "",
            "## All Questions",
            "",
            "| ID | Category | Status | Rows | Seconds | Question | Error category |",
            "|---|---|---|---:|---:|---|---|",
        ]
    )
    for item in results:
        lines.append(
            "| {id} | {category} | `{status}` | {rows} | {seconds} | {question} | {failure} |".format(
                id=item["id"],
                category=_escape_md(item["category"], 80),
                status=item["status"],
                rows=item["row_count"],
                seconds=item["execution_time_seconds"],
                question=_escape_md(item["question"], 220),
                failure=_escape_md(item.get("failure_category") or "", 120),
            )
        )

    lines.extend(
        [
            "",
            "## Incorrect Executions",
            "",
        ]
    )
    if not error_items:
        lines.append("No incorrect executions were observed.")
    else:
        lines.extend(
            [
                "| ID | Question | Failure category | Reason | Error preview |",
                "|---|---|---|---|---|",
            ]
        )
        for item in error_items:
            lines.append(
                "| {id} | {question} | `{failure}` | {reason} | {error} |".format(
                    id=item["id"],
                    question=_escape_md(item["question"], 220),
                    failure=item.get("failure_category") or "unknown",
                    reason=_escape_md(_failure_reason(item), 350),
                    error=_escape_md(item.get("error_message") or item.get("response"), 350),
                )
            )

    lines.extend(
        [
            "",
            "## Generalization Notes",
            "",
            "- Questions about data that is not in SIH/RD administrative hospitalization records should be routed to a clear unsupported-data answer instead of attempting SQL.",
            "- Questions that imply post-discharge follow-up, patient identity, medication use, vaccination, laboratory tests, or individual longitudinal linkage need explicit schema support before they can be answered.",
            "- Semantic-plan failures should be converted into regression examples only when the required data exists and the expected SQL contract is unambiguous.",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume-json", type=Path, default=None)
    parser.add_argument(
        "--query-timeout",
        type=int,
        default=int(os.getenv("HEALTH_EXHAUSTION_QUERY_TIMEOUT_SECONDS", "120")),
    )
    args = parser.parse_args()

    load_dotenv()
    output_dir = Path("evaluation/agent/results")
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.resume_json:
        json_path = args.resume_json
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        run_id = payload["run_id"]
        report_path = json_path.with_suffix(".md")
        base_elapsed = float(payload.get("elapsed_seconds") or 0)
        payload["resumed_at"] = datetime.now().isoformat(timespec="seconds")
    else:
        run_id = datetime.now().strftime("health_exhaustion_%Y%m%dT%H%M%S")
        json_path = output_dir / f"{run_id}.json"
        report_path = output_dir / f"{run_id}.md"
        app_config = ApplicationConfig()
        orchestrator_config = _orchestrator_config_from_env()
        base_elapsed = 0.0
        payload = {
            "run_id": run_id,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "git": {
                "branch": _run_git(["branch", "--show-current"]),
                "commit": _run_git(["rev-parse", "--short", "HEAD"]),
            },
            "database_path": app_config.database_path,
            "orchestrator_config": {
                "llamaindex_mode": orchestrator_config.llamaindex_mode,
                "enable_llamaindex_context": orchestrator_config.enable_llamaindex_context,
                "enable_llamaindex_sql_draft": orchestrator_config.enable_llamaindex_sql_draft,
                "llamaindex_top_k_tables": orchestrator_config.llamaindex_top_k_tables,
            },
            "total_questions": len(QUESTIONS),
            "results": [],
        }
    payload["query_timeout_seconds"] = args.query_timeout

    started = time.time()
    completed_ids = {item["id"] for item in payload["results"]}
    for index, item in enumerate(QUESTIONS, start=1):
        if item["id"] in completed_ids:
            continue
        question_started = time.time()
        print(f"[{index:02d}/{len(QUESTIONS)}] {item['id']} {item['question']}", flush=True)
        extracted = _run_question_with_timeout(item, run_id, args.query_timeout)
        if extracted["status"] != "incorrect_timeout":
            extracted["execution_time_seconds"] = round(time.time() - question_started, 3)
        payload["results"].append(extracted)
        payload["elapsed_seconds"] = round(base_elapsed + time.time() - started, 3)
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            f"  -> {extracted['status']} rows={extracted['row_count']} "
            f"seconds={extracted['execution_time_seconds']} "
            f"failure={extracted['failure_category'] or '-'}",
            flush=True,
        )

    payload["finished_at"] = datetime.now().isoformat(timespec="seconds")
    payload["elapsed_seconds"] = round(base_elapsed + time.time() - started, 3)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown_report(payload, report_path)
    print(f"JSON: {json_path}", flush=True)
    print(f"REPORT: {report_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
