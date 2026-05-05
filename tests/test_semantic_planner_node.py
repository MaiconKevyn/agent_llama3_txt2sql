from src.agent.semantic_planner import SemanticPlannerOutput, semantic_planner_node
from src.agent.state_helpers import create_initial_messages_state
from src.semantic.plan_schema import AnswerShape, SemanticMetric, SemanticPlan
from src.semantic.planner import build_semantic_plan


def test_semantic_planner_node_reconciles_structured_llm_plan(monkeypatch):
    heuristic = build_semantic_plan("Quais são os 5 procedimentos mais comuns para cada sexo?")
    candidate = SemanticPlan(
        intent="ranking",
        base_grain="procedimento_ocorrencia",
        metrics=[SemanticMetric(name="total_internacoes", expression_type="count")],
        answer_shape=AnswerShape(row_grain="top_n_global", top_n=5, top_n_scope="global"),
    )

    class DummyLLMManager:
        def invoke_chat_structured(self, messages, schema):
            return SemanticPlannerOutput(
                semantic_plan=candidate,
                reasoning="mocked",
                confidence=0.7,
            )

    monkeypatch.setattr(
        "src.agent.semantic_planner.get_llm_manager",
        lambda: DummyLLMManager(),
    )
    state = create_initial_messages_state(
        user_query="Quais são os 5 procedimentos mais comuns para cada sexo?",
        session_id="semantic-planner-test",
    )
    state["semantic_plan"] = heuristic.model_dump(exclude_none=True)

    new_state = semantic_planner_node(state)

    assert new_state["semantic_plan"]["answer_shape"]["top_n_scope"] == "per_group"
    metadata = new_state["response_metadata"]["semantic_planner"]
    assert metadata["mode"] == "llm_reconciled"
    assert any("top_n_scope_mismatch" in conflict for conflict in metadata["conflicts"])


def test_semantic_planner_node_falls_back_to_heuristic_on_llm_error(monkeypatch):
    heuristic = build_semantic_plan("Qual a taxa de mortalidade por estado?")

    class DummyLLMManager:
        def invoke_chat_structured(self, messages, schema):
            raise RuntimeError("mock failure")

    monkeypatch.setattr(
        "src.agent.semantic_planner.get_llm_manager",
        lambda: DummyLLMManager(),
    )
    state = create_initial_messages_state(
        user_query="Qual a taxa de mortalidade por estado?",
        session_id="semantic-planner-fallback-test",
    )
    state["semantic_plan"] = heuristic.model_dump(exclude_none=True)

    new_state = semantic_planner_node(state)

    assert new_state["semantic_plan"] == heuristic.model_dump(exclude_none=True)
    assert new_state["response_metadata"]["semantic_planner"]["mode"] == "heuristic_fallback"
