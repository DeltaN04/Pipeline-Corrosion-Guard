"""Tests for the LLM-assisted note assessment (raise-only, fail-soft, keyword baseline)."""
from typing import List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel, Field

import src.llm.provider as provider
from src.tools import note_llm


class _FakeStructured(BaseModel):
    severe: bool = Field(default=False)
    contradicts_numbers: bool = Field(default=False)
    reason: str = Field(default="fake reason")


class FakeRaisingChatModel(BaseChatModel):
    """Real-mode fake: structured output RAISES severe; prose echoes."""

    @property
    def _llm_type(self) -> str:
        return "fake-raising"

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
                  run_manager: object = None, **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])

    def with_structured_output(self, schema=None, **kwargs):
        class _Wrapper:
            def invoke(self, messages):  # noqa: ANN001
                return _FakeStructured(severe=True, contradicts_numbers=False,
                                      reason="LLM judged the note severe")
        return _Wrapper()


class FakeExplodingChatModel(BaseChatModel):
    """Real-mode fake: structured output raises -> keyword fallback."""

    @property
    def _llm_type(self) -> str:
        return "fake-exploding"

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
                  run_manager: object = None, **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])

    def with_structured_output(self, schema=None, **kwargs):
        class _Wrapper:
            def invoke(self, messages):  # noqa: ANN001
                raise RuntimeError("LLM unavailable")
        return _Wrapper()


def test_mock_backend_returns_keyword_result_unchanged():
    """Mock backend: keyword result returned exactly, no LLM involved."""
    note = "Severe sharp undercut at weld toe."
    flags, severe, reason = note_llm.assess_note(None, note, 55.0)
    assert severe is True
    assert "severe" in flags
    assert reason == "keyword"


def test_real_mode_llm_can_raise_but_never_lower_keyword_severe():
    """LLM may raise severe; a keyword-severe note can never be lowered."""
    provider.LLM_BACKEND = "ollama"  # real mode (fake model substituted)
    note = "Severe sharp undercut at weld toe."  # keyword-severe
    flags, severe, reason = note_llm.assess_note(FakeRaisingChatModel(), note, 55.0)
    assert severe is True  # keyword already severe -> stays severe (never lowered)
    assert reason != "keyword"

    # Keyword-clean note + LLM raise -> severe becomes True (raise only)
    clean_note = "General wall loss, smooth profile."
    flags2, severe2, reason2 = note_llm.assess_note(FakeRaisingChatModel(), clean_note, 30.0)
    assert severe2 is True
    assert "LLM judged" in reason2


def test_exception_falls_back_to_keyword():
    """Any LLM exception -> keyword result with reason 'keyword_fallback'."""
    provider.LLM_BACKEND = "ollama"
    note = "General wall loss, smooth profile."  # keyword-clean
    flags, severe, reason = note_llm.assess_note(FakeExplodingChatModel(), note, 30.0)
    assert severe is False
    assert reason == "keyword_fallback"


def test_empty_note_short_circuits():
    provider.LLM_BACKEND = "ollama"
    flags, severe, reason = note_llm.assess_note(FakeRaisingChatModel(), "", 30.0)
    assert flags == [] and severe is False and reason == "keyword"


def test_llm_never_lowers_keyword_severe_via_contradiction_flag():
    """contradicts_numbers also only raises; combined with keyword-severe stays True."""

    class LoweringModel(FakeRaisingChatModel):
        def with_structured_output(self, schema=None, **kwargs):
            class _W:
                def invoke(self, messages):  # noqa: ANN001
                    return _FakeStructured(severe=False, contradicts_numbers=True,
                                          reason="implies numbers understate")
            return _W()

    provider.LLM_BACKEND = "anthropic"
    _, severe, _ = note_llm.assess_note(LoweringModel(), "Minor pitting, monitor.", 30.0)
    assert severe is True  # raise-only via contradicts_numbers
