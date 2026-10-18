"""Test that the pipeline works with a fake LLM - validates one-line swap capability."""
from typing import Any, List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class SimpleFakeChatModel(BaseChatModel):
    """Simple fake chat model that returns predefined responses."""
    
    def __init__(self, responses: List[str]):
        super().__init__()
        self._responses = responses
        self._call_count = 0
    
    @property
    def _llm_type(self) -> str:
        return "simple-fake"
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self._call_count < len(self._responses):
            response = self._responses[self._call_count]
        else:
            response = "Default response"
        self._call_count += 1
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=response))])


def test_pipeline_with_fake_llm():
    """End-to-end test with a simple fake LLM instead of MockChatModel."""
    from src.graph.runner import run_triage, extract_ground_truth, df_to_anomalies
    from src.graph.builder import build_graph
    from src.agents import research, executor as exec_agent, critic as critic_agent, planner as planner_agent, automation as auto_agent
    from data.ground_truth import generate_true_anomalies
    import pandas as pd
    from pathlib import Path
    import tempfile
    
    # Generate test data
    df = generate_true_anomalies(seed=42, n_total=10)
    agent_cols = [c for c in df.columns if c not in ["true_depth_pct", "true_prior_depth_pct", "true_growth_pct_per_yr", "true_erf", "truth_class", "is_planted_miss", "is_dirty"]]
    df_agent = df[agent_cols]
    
    gt = extract_ground_truth(df)
    anomalies = df_to_anomalies(df_agent)
    
    # Create fake LLM with predefined responses
    fake_responses = [
        # Planner response
        "Plan for request 'test': 1) Research... 2) Executor... 3) Critic... 4) Loop-back... 5) Human... 6) Automation. Routing=small_batch.",
        # Executor responses (one per anomaly)
        *[f"[RISK_RATIONALE] anomaly_id={a['anomaly_id']}: depth 50% with ERF 0.5 gives class 180_DAY. Factors: HCA. Safe pressure 5.0 MPa vs MAOP 7.0 MPa; projected depth 55% in 2yr at 2%/yr." for a in anomalies],
        # Critic responses (one per anomaly)
        *[f"[CRITIC] anomaly_id={a['anomaly_id']}: executor=180_DAY, screen_class=180_DAY, legacy=180_DAY. Verdict AGREE. Reasons: no screening threshold breached. Independent checks corroborate the executor class." for a in anomalies],
        # Summary
        "Run test: 10 anomalies triaged ({'180_DAY': 10}). Critic challenged 0, upgraded 0, escalated 0. 0 missed-critical defects caught vs legacy labels. Immediate items pending human approval: 0.",
        # Work order responses (one per anomaly)
        *[f"Work order WO-test-{a['anomaly_id']} for {a['anomaly_id']} (P-14 @ 1000.0 m): priority 180_DAY, action 'Schedule assessment/repair within 180 days; trend growth at next review.', due 2026-10-18." for a in anomalies],
    ]
    
    fake_llm = SimpleFakeChatModel(responses=fake_responses)
    
    # Test planner
    plan = planner_agent.build_plan("test request", len(anomalies), 0, fake_llm)
    assert "tasks" in plan
    assert plan["routing"] == "small_batch"
    
    # Test research (no LLM)
    enriched = research.enrich(anomalies)
    assert len(enriched) == len(anomalies)
    
    # Test executor
    results = exec_agent.execute(enriched, fake_llm)
    assert len(results) == len(anomalies)
    
    # Test critic
    verdicts, objections = critic_agent.review(enriched, results, fake_llm)
    assert len(verdicts) == len(anomalies)
    
    # Test automation
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs = auto_agent.build_outputs(enriched, verdicts, results, "test", Path(tmpdir), fake_llm)
        assert "work_orders_csv" in outputs
    
    # Test full graph with fake LLM (monkeypatch get_chat_model)
    import src.llm.provider as provider_module
    original_get_chat_model = provider_module.get_chat_model
    provider_module.get_chat_model = lambda: fake_llm
    
    try:
        final = run_triage(df_agent, request="test", ground_truth=gt, verbose=True)
        assert final.get("metrics") is not None
        assert len(final.get("verdicts", [])) == len(anomalies)
    finally:
        provider_module.get_chat_model = original_get_chat_model
    
    print("LLM swap test passed!")


if __name__ == "__main__":
    test_pipeline_with_fake_llm()