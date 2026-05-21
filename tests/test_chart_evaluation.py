from evaluation.runners.run_chart_evaluation import evaluate_items


def test_chart_evaluation_scores_positive_and_negative_cases():
    report = evaluate_items(
        [
            {
                "id": "neg",
                "query": "Quais sao os 5 municipios com maior numero de internacoes?",
                "expect_requested": False,
            },
            {
                "id": "pos",
                "query": "Gere um grafico de barras dos municipios",
                "expect_requested": True,
                "expected_chart_type": "bar",
                "sql_query": "SELECT municipio, total FROM ranking",
                "results": [{"result": ["A", 10]}, {"result": ["B", 8]}],
                "row_count": 2,
            },
        ]
    )

    assert report["metrics"]["intent_precision"] == 1.0
    assert report["metrics"]["intent_recall"] == 1.0
    assert report["metrics"]["spec_validity"] == 1.0
    assert report["metrics"]["chart_type_accuracy"] == 1.0


def test_chart_evaluation_scores_presentation_contract():
    report = evaluate_items(
        [
            {
                "id": "presentation",
                "query": "Gere um grafico de barras dos municipios",
                "expect_requested": True,
                "expected_chart_type": "bar",
                "expected_value_format": "integer",
                "expected_x_label": "Municipio",
                "expected_y_label": "Total de internacoes",
                "sql_query": "SELECT municipio, total_internacoes FROM ranking",
                "results": [{"result": ["A", 10]}, {"result": ["B", 8]}],
                "row_count": 2,
            },
        ]
    )

    assert report["metrics"]["presentation_validity"] == 1.0
    assert report["counts"]["presentation_expected"] == 1
    assert report["counts"]["presentation_correct"] == 1
