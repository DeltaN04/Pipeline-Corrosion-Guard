"""Tests for the env-var driven LLM provider (mock default, real backends, fail-soft)."""
from typing import List, Optional

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

import src.llm.provider as provider


class FakeExplodingChatModel(BaseChatModel):
    """Real-mode fake that always raises."""

    @property
    def _llm_type(self) -> str:
        return "fake-exploding"

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
                  run_manager: object = None, **kwargs) -> ChatResult:
        raise RuntimeError("server down")


def test_unknown_backend_raises_value_error():
    provider.LLM_BACKEND = "does-not-exist"
    with pytest.raises(ValueError, match="Unknown LLM_BACKEND"):
        provider.get_chat_model()


def test_mock_backend_returns_mock_model():
    provider.LLM_BACKEND = "mock"
    llm = provider.get_chat_model()
    assert llm._llm_type == "corrosionguard-mock"
    # Mock mode llm_text renders the deterministic template
    out = provider.llm_text(llm, "[SUMMARY]\nrun_id=X")
    assert "Run X" in out


def test_real_mode_falls_back_to_mock_on_exception():
    """Real-mode invoke failure -> mock template output, no crash."""
    provider.LLM_BACKEND = "ollama"
    out = provider.llm_text(FakeExplodingChatModel(), "[SUMMARY]\nrun_id=X")
    assert "Run X" in out  # fell back to MockChatModel template


def test_real_mode_passes_system_message():
    """Real mode prepends a SystemMessage with instruction + tag hint."""

    captured = {}

    class FakeRealModel(BaseChatModel):
        @property
        def _llm_type(self) -> str:
            return "fake-real"

        def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
                      run_manager: object = None, **kwargs) -> ChatResult:
            captured["messages"] = messages
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="prose"))])

    provider.LLM_BACKEND = "anthropic"
    out = provider.llm_text(FakeRealModel(), "[CRITIC]\nanomaly_id=A-1\nverdict=UPGRADE_REQUIRED")
    assert out == "prose"
    msgs = captured["messages"]
    assert msgs[0].type == "system"
    assert "NEVER change" in msgs[0].content
    assert "critic verdict" in msgs[0].content  # tag hint included
    assert any("[CRITIC]" in m.content for m in msgs[1:])


def test_rationale_gate_real_mode():
    """llm_text_or_mock: real mode only calls the LLM for gated classes."""
    calls = []

    class CountingModel(FakeExplodingChatModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            calls.append(1)
            raise RuntimeError("server down")

    provider.LLM_BACKEND = "ollama"
    # Gated class -> attempts LLM (fails -> mock template)
    provider.llm_text_or_mock(CountingModel(), "[SUMMARY]\nx=1", "IMMEDIATE")
    assert len(calls) == 1
    # Non-gated class -> no LLM call, mock template directly
    provider.llm_text_or_mock(CountingModel(), "[SUMMARY]\nx=1", "MONITOR")
    assert len(calls) == 1  # unchanged
    # Mock backend -> always "LLM" (the mock model)
    provider.LLM_BACKEND = "mock"
    provider.llm_text_or_mock(CountingModel(), "[SUMMARY]\nx=1", "MONITOR")
    assert len(calls) == 1  # the gated real-mode attempt above (fell back to mock template)
