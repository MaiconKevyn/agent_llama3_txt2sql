from evaluation.agent.generalization_rubric import (
    judge_safe_refusal,
    score_numeric_equivalence,
)


def test_judge_safe_refusal_accepts_explicit_schema_limitation():
    result = judge_safe_refusal(
        response=(
            "O banco atual nao possui informacoes de medicamentos ou prescricoes, "
            "entao nao consigo calcular quais antibioticos foram usados."
        ),
        judge={"must_mention": ["medicamentos", "nao possui"], "must_not_claim_numeric_answer": True},
    )

    assert result["passed"] is True
    assert result["missing"] == []


def test_judge_safe_refusal_rejects_fake_zero_answer():
    result = judge_safe_refusal(
        response="Foram encontrados 0 antibioticos usados em pacientes com pneumonia.",
        judge={"must_mention": ["medicamentos", "nao esta disponivel"], "must_not_claim_numeric_answer": True},
    )

    assert result["passed"] is False
    assert "numeric_claim_for_unsupported_schema" in result["missing"]


def test_score_numeric_equivalence_allows_small_tolerance():
    expected = [{"uf": "MA", "taxa": 10.01}, {"uf": "RS", "taxa": 9.99}]
    actual = [{"uf": "MA", "taxa": 10.02}, {"uf": "RS", "taxa": 9.98}]

    result = score_numeric_equivalence(
        expected, actual, required_columns=["uf", "taxa"], tolerance=0.02
    )

    assert result["passed"] is True


def test_score_numeric_equivalence_rejects_missing_required_column():
    result = score_numeric_equivalence(
        [{"uf": "MA", "taxa": 10.0}],
        [{"uf": "MA"}],
        required_columns=["uf", "taxa"],
        tolerance=0.01,
    )

    assert result["passed"] is False
    assert "missing_column:taxa" in result["missing"]


def test_result_equivalence_rejects_wrong_ordered_values():
    expected = [{"uf": "MA", "total": 10}, {"uf": "RS", "total": 20}]
    actual = [{"uf": "MA", "total": 10}, {"uf": "RS", "total": 21}]

    result = score_numeric_equivalence(
        expected, actual, required_columns=["uf", "total"], tolerance=0.0
    )

    assert result["passed"] is False
    assert "value_mismatch:1:total" in result["missing"]


def test_result_equivalence_accepts_common_column_aliases_and_unordered_groups():
    expected = [
        {"uf_residencia": "RJ", "total_obitos": 7, "taxa_mortalidade_percentual": 3.5},
        {"uf_residencia": "MA", "total_obitos": 3, "taxa_mortalidade_percentual": 1.5},
    ]
    actual = [
        {"estado": "MA", "total_mortes": 3, "taxa_mortalidade": 1.5},
        {"estado": "RJ", "total_mortes": 7, "taxa_mortalidade": 3.5},
    ]

    result = score_numeric_equivalence(
        expected,
        actual,
        required_columns=["uf_residencia", "total_obitos", "taxa_mortalidade_percentual"],
        tolerance=0.0,
    )

    assert result["passed"] is True


def test_result_equivalence_accepts_total_alias_for_admission_count():
    result = score_numeric_equivalence(
        [{"total_internacoes": 42}],
        [{"total": 42}],
        required_columns=["total_internacoes"],
        tolerance=0.0,
    )

    assert result["passed"] is True


def test_result_equivalence_accepts_arbitrary_labels_when_topn_metric_is_fully_tied():
    result = score_numeric_equivalence(
        [
            {"especialidade": "CARDIOLOGIA", "permanencia_media": 0.0},
            {"especialidade": "SAUDE MENTAL", "permanencia_media": 0.0},
        ],
        [
            {"especialidade": "ENDOCRINOLOGIA", "permanencia_media": 0.0},
            {"especialidade": "NEUROCIRURGIA", "permanencia_media": 0.0},
        ],
        required_columns=["especialidade", "permanencia_media"],
        tolerance=0.01,
    )

    assert result["passed"] is True
