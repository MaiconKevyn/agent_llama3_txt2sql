import json
from collections import Counter
from pathlib import Path

from evaluation.agent.generalization_rubric import load_generalization_questions


def test_load_generalization_questions_has_required_fields():
    questions = load_generalization_questions(Path("evaluation/agent/generalization_questions.jsonl"))

    assert len(questions) >= 12
    ids = [item.id for item in questions]
    assert len(ids) == len(set(ids))
    assert all(item.question.strip() for item in questions)
    assert all(
        item.expected_behavior
        in {"answer_with_sql", "safe_refusal", "answer_with_analytic_template"}
        for item in questions
    )
    assert any(item.expected_behavior == "safe_refusal" for item in questions)
    assert any(item.expected_behavior == "answer_with_sql" for item in questions)


def test_jsonl_is_valid_one_object_per_line():
    path = Path("evaluation/agent/generalization_questions.jsonl")
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    assert lines
    for line in lines:
        payload = json.loads(line)
        assert sorted(payload) == [
            "anti_overfit_family",
            "category",
            "difficulty",
            "expected_behavior",
            "expected_tables",
            "id",
            "judge",
            "persona",
            "question",
            "reference_sql",
            "schema_basis",
        ]


def test_generalization_corpus_meets_plan_coverage_targets():
    questions = load_generalization_questions(Path("evaluation/agent/generalization_questions.jsonl"))
    total = len(questions)
    behavior_counts = Counter(item.expected_behavior for item in questions)
    category_counts = Counter(item.category for item in questions)

    assert total >= 200
    assert behavior_counts["answer_with_sql"] / total >= 0.70
    assert behavior_counts["safe_refusal"] / total >= 0.20
    assert behavior_counts["answer_with_analytic_template"] / total >= 0.10

    minimums = {
        "volume_temporal": 20,
        "mortalidade_hospitalar": 25,
        "diagnosticos_cid": 25,
        "geografia": 20,
        "procedimentos": 15,
        "custos_permanencia": 20,
        "uti": 15,
        "perfil_demografico": 20,
        "socioeconomico_populacao": 15,
        "qualidade_dados": 15,
        "fora_do_schema": 20,
        "pergunta_cientifica_associativa": 20,
    }
    for category, minimum in minimums.items():
        assert category_counts[category] >= minimum
