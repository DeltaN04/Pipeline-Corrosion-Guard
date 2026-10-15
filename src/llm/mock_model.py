"""Mock deterministic LLM: LangChain-compatible chat model.

Subclasses BaseChatModel and returns rule-and-template-based text derived from
structured inputs embedded in the prompt. No network, no randomness.

Prompt protocol: agents embed a marker line + key=value facts, e.g.
    [RISK_RATIONALE]
    anomaly_id=A-001 depth_pct=62.0 erf=0.91 class=60_DAY factors=HCA,rapid_growth
The mock parses the marker and facts and fills a fixed template deterministically.
This keeps free-text rationales/summaries/objections reproducible (seed-independent).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


def _facts(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line and not line.strip().startswith("["):
            k, _, v = line.strip().partition("=")
            if k.strip():
                out[k.strip()] = v.strip()
    return out


def _render(prompt: str) -> str:
    f = _facts(prompt)
    g = lambda k, d="n/a": f.get(k, d)  # noqa: E731
    if "[PLAN]" in prompt:
        return (
            f"Plan for request '{g('request')}': 1) Research enriches {g('n_anomalies')} anomalies "
            f"(metadata, growth, HCA, neighbours, quality). 2) Executor runs B31G/ERF/risk triage. "
            f"3) Critic independently re-screens and challenges. 4) Loop-back max 2 iterations on "
            f"UPGRADE_REQUIRED, else escalate to the more severe class. 5) Human approval for IMMEDIATE, "
            f"then Business Automation writes work orders and notifications. Routing={g('routing')}."
        )
    if "[RISK_RATIONALE]" in prompt:
        return (
            f"Anomaly {g('anomaly_id')}: depth {g('depth_pct')}% with ERF {g('erf')} gives "
            f"class {g('class')}. Contributing factors: {g('factors')}. "
            f"Safe pressure {g('safe_pressure')} MPa vs MAOP {g('maop')} MPa; "
            f"projected depth {g('projected')} % in 2yr at {g('growth')} %/yr. "
            f"Conservative where inputs were missing; see tool trace for exact numbers."
        )
    if "[CRITIC]" in prompt:
        return (
            f"Critic review of {g('anomaly_id')}: executor={g('executor_class')}, "
            f"independent screen={g('screen_class')}, legacy={g('legacy')}. Verdict {g('verdict')}. "
            f"Reasons: {g('reasons')}. "
            + (
                "The numeric triage understates context/notes risk; upgrade required."
                if g("verdict") == "UPGRADE_REQUIRED"
                else "Independent checks corroborate the executor class."
            )
        )
    if "[SUMMARY]" in prompt:
        return (
            f"Run {g('run_id')}: {g('n_total')} anomalies triaged ({g('breakdown')}). "
            f"Critic challenged {g('n_challenged')}, upgraded {g('n_upgraded')}, "
            f"escalated {g('n_escalated')}. {g('n_missed_caught')} missed-critical defects caught vs legacy labels. "
            f"Immediate items pending human approval: {g('n_immediate')}."
        )
    if "[WORKORDER]" in prompt:
        return (
            f"Work order {g('work_order_id')} for {g('anomaly_id')} ({g('pipeline_id')} @ {g('chainage')} m): "
            f"priority {g('priority')}, action '{g('action')}', due {g('due')}. "
            f"Crew briefing includes ERF, depth, growth, HCA/crossing context and critic notes."
        )
    return "MockChatModel: no marker found; echoing deterministic summary of input length %d chars." % len(prompt)


class MockChatModel(BaseChatModel):
    """Deterministic LangChain chat model for offline use."""

    model_name: str = "corrosionguard-mock-1.0"

    @property
    def _llm_type(self) -> str:
        return "corrosionguard-mock"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        prompt = messages[-1].content if messages else ""
        if not isinstance(prompt, str):
            prompt = str(prompt)
        text = _render(prompt)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    # Convenience helpers used by agents (still route through _render for traceability).
    def render(self, prompt: str) -> str:
        return _render(prompt)
