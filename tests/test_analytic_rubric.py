from evaluation.agent.analytic_rubric import (
    AnalyticQuestionSet,
    score_analytic_response,
)
from evaluation.agent.run_analytic_evaluation import build_dry_run_items


def test_loads_analytic_question_set_from_default_file():
    question_set = AnalyticQuestionSet.load_default()

    assert len(question_set.questions) >= 7
    assert any(item.expected_template == "numeric_factor_by_condition" for item in question_set.questions)
    assert any(item.expected_template == "temporal_trend_by_condition" for item in question_set.questions)


def test_analytic_eval_dry_run_reports_template_matches():
    question_set = AnalyticQuestionSet.load_default()

    items = build_dry_run_items(question_set)

    assert len(items) == len(question_set.questions)
    assert all("semantic_plan" in item for item in items)
    assert any(item["template_match"] for item in items)


def test_rubric_penalizes_sample_partial_without_denominator():
    score = score_analytic_response(
        question="Existe relação entre idade e doenças pulmonares?",
        response=(
            "Existe relação. A amostra parcial mostra idade 0 com 7.207.910 internações "
            "e idade 58 com 167.413 internações."
        ),
        sql="SELECT IDADE, COUNT(*) FROM internacoes GROUP BY IDADE LIMIT 10",
        semantic_plan={"constraints": ["analytic_response_required"]},
    )

    assert score.score < 0.5
    assert "denominator_present" in score.missing
    assert "no_sample_only" in score.missing


def test_rubric_scores_complete_analytic_response_high():
    response = """
    Sim. Há uma associação observada entre idade e o diagnóstico resolvido nos dados.
    Escopo usado: CID J00-J99 - Doenças do aparelho respiratório; denominador: todas as internações.
    | Faixa etária | Internações | Taxa por 100 mil denominador | % dos casos |
    | 00-39 | 10.691.790 | 10.713,23 | 54,3% |
    Leitura objetiva: a taxa em >=60 anos foi 1,47x a taxa em <60 anos.
    Atenção sobre qualidade dos dados: IDADE=0 contém 5.164.368 registros inconsistentes.
    Limite: isto descreve associação observada nas internações, não causalidade individual.
    """
    score = score_analytic_response(
        question="Existe relação entre idade e doenças pulmonares?",
        response=response,
        sql="WITH diagnosticos_alvo AS (...) SELECT 'age_diagnosis_association' AS analysis_type",
        semantic_plan={
            "intent": "association",
            "constraints": ["analytic_response_required", "age_diagnosis_association_required"],
        },
    )

    assert score.score >= 0.85
    assert not score.missing
