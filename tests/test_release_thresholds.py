from evaluation.agent.release_thresholds import evaluate_release_thresholds


def _result(score=1.0, domain_score=1.0, latencies=None):
    domains = {
        "volume_temporal",
        "geografia",
        "diagnosticos_cid",
        "procedimentos",
        "custos_permanencia",
        "socioeconomico_populacao",
        "qualidade_dados",
        "fora_do_schema",
        "ambiguidade",
    }
    return {
        "summary": {
            "score": score,
            "category_scores": {
                domain: {"score": domain_score, "passed": 1, "total": 1} for domain in domains
            },
        },
        "items": [
            {"answerability": "answerable", "latency_seconds": latency}
            for latency in (latencies or [8.0, 10.0, 11.0])
        ],
    }


def test_release_thresholds_pass_when_scores_and_latency_meet_targets():
    evaluation = evaluate_release_thresholds(_result())

    assert evaluation["passed"] is True


def test_release_thresholds_fail_when_global_score_is_low():
    evaluation = evaluate_release_thresholds(_result(score=0.89))

    assert evaluation["passed"] is False
    failed = [check["name"] for check in evaluation["checks"] if not check["passed"]]
    assert "global_score" in failed


def test_release_thresholds_fail_when_median_latency_exceeds_target():
    evaluation = evaluate_release_thresholds(_result(latencies=[11.0, 13.0, 14.0]))

    assert evaluation["passed"] is False
    failed = [check["name"] for check in evaluation["checks"] if not check["passed"]]
    assert "latency:answerable_median" in failed
