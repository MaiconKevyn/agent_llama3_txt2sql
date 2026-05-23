from collections import Counter
from pathlib import Path

from evaluation.agent.generalization_rubric import load_benchmark_questions
from evaluation.agent.run_generalization_exhaustion import (
    evaluate_response,
    run_items,
    summarize_items,
    write_markdown,
)


def test_benchmark_v1_loads_source_refs_and_clarification_cases():
    questions = load_benchmark_questions(Path("evaluation/benchmarks/v1"))

    ids = {question.id for question in questions}
    behaviors = {question.expected_behavior for question in questions}
    categories = {question.category for question in questions}

    assert "V1_TEMPORAL_001" in ids
    assert "V1_AMBIG_001" in ids
    assert "requires_clarification" in behaviors
    assert {
        "volume_temporal",
        "geografia",
        "diagnosticos_cid",
        "fora_do_schema",
        "ambiguidade",
        "visualizacao",
    } <= categories


def test_benchmark_v1_has_minimum_domain_matrix():
    questions = load_benchmark_questions(Path("evaluation/benchmarks/v1"))

    counts = Counter(question.category for question in questions)
    expected_domains = {
        "volume_temporal",
        "geografia",
        "diagnosticos_cid",
        "procedimentos",
        "custos_permanencia",
        "socioeconomico_populacao",
        "qualidade_dados",
        "fora_do_schema",
        "ambiguidade",
        "visualizacao",
    }

    assert expected_domains <= set(counts)
    assert all(counts[domain] >= 10 for domain in expected_domains)


def test_benchmark_v1_cid_concept_cases_use_versioned_prefixes():
    questions = {
        question.id: question
        for question in load_benchmark_questions(Path("evaluation/benchmarks/v1/cid.jsonl"))
    }

    diabetes = questions["V1_CID_009"]
    pneumonia = questions["V1_CID_010"]

    assert "E10%" in diabetes.reference_sql
    assert "E14%" in diabetes.reference_sql
    assert any("clinical_concepts_v1.yaml:diabetes" in item for item in diabetes.schema_basis)
    assert "J12%" in pneumonia.reference_sql
    assert "J18%" in pneumonia.reference_sql
    assert any("clinical_concepts_v1.yaml:pneumonia" in item for item in pneumonia.schema_basis)


def test_benchmark_v1_procedure_concept_cases_use_versioned_prefixes():
    questions = {
        question.id: question
        for question in load_benchmark_questions(Path("evaluation/benchmarks/v1/procedures.jsonl"))
    }

    diabetes = questions["V1_PROC_009"]
    pneumonia = questions["V1_PROC_010"]

    assert "E10%" in diabetes.reference_sql
    assert "E14%" in diabetes.reference_sql
    assert "ILIKE '%diabetes%'" not in diabetes.reference_sql
    assert any("clinical_concepts_v1.yaml:diabetes" in item for item in diabetes.schema_basis)
    assert "J12%" in pneumonia.reference_sql
    assert "J18%" in pneumonia.reference_sql
    assert "ILIKE '%pneumonia%'" not in pneumonia.reference_sql
    assert any("clinical_concepts_v1.yaml:pneumonia" in item for item in pneumonia.schema_basis)


def test_benchmark_v1_cost_cases_are_explicit_and_versioned():
    questions = {
        question.id: question
        for question in load_benchmark_questions(Path("evaluation/benchmarks/v1/costs.jsonl"))
    }

    assert "UF de residencia" in questions["V1_COST_001"].question
    assert "UF de residencia" in questions["V1_COST_002"].question
    assert "UF de residencia" in questions["V1_COST_007"].question
    assert "UF de residencia" in questions["V1_COST_008"].question

    pneumonia = questions["V1_COST_005"]
    assert "J12%" in pneumonia.reference_sql
    assert "J18%" in pneumonia.reference_sql
    assert "ILIKE '%pneumonia%'" not in pneumonia.reference_sql
    assert any("clinical_concepts_v1.yaml:pneumonia" in item for item in pneumonia.schema_basis)


def test_requires_clarification_is_product_success_without_sql():
    question = [
        item
        for item in load_benchmark_questions(Path("evaluation/benchmarks/v1/ambiguity.jsonl"))
        if item.id == "V1_AMBIG_001"
    ][0]
    result = {
        "success": True,
        "response": "Voce quer usar residencia do paciente ou hospital/atendimento?",
        "sql_query": "",
        "metadata": {"critical_ambiguity": "geography_residence_vs_hospital"},
    }

    judgement = evaluate_response(question, result)

    assert judgement["passed"] is True
    assert judgement["judge"]["missing"] == []


def test_benchmark_dry_run_outputs_answerability_fields():
    items = run_items(
        run_id="test_dry_run",
        limit=2,
        benchmark=Path("evaluation/benchmarks/v1"),
        dry_run=True,
    )

    assert len(items) == 2
    assert all(item["status"] == "dry_run" for item in items)


def test_summary_and_markdown_include_domain_scores_and_case_details(tmp_path):
    items = [
        {
            "id": "A",
            "category": "ambiguidade",
            "status": "passed",
            "answerability": "requires_clarification",
            "latency_seconds": 0.2,
            "question": "Qual a mortalidade por UF?",
            "response": "residencia ou hospital?",
            "metadata": {"domain_caveats": ["caveat teste"]},
        },
        {
            "id": "B",
            "category": "cid",
            "status": "failed",
            "answerability": "technical_error",
            "severity": "high",
            "root_cause": "sql_execution_error",
            "question": "CID?",
            "sql": "SELECT 1",
            "metadata": {},
        },
    ]
    payload = {
        "run_id": "test",
        "dry_run": False,
        "summary": summarize_items(items),
        "items": items,
    }
    output = tmp_path / "report.md"

    write_markdown(payload, output)
    text = output.read_text(encoding="utf-8")

    assert "## Domain Scores" in text
    assert "`ambiguidade`" in text
    assert "requires_clarification" in text
    assert "caveat teste" in text
