"""LLM provider interface. Swap backends by changing ONE config value.

LLM_BACKEND = "mock"      -> MockChatModel (deterministic, offline, default)
LLM_BACKEND = "ollama"    -> real Ollama model via langchain-ollama (needs extra dep + server)
LLM_BACKEND = "anthropic" -> real Anthropic model via langchain-anthropic (needs API key)

All agents call get_chat_model(), never a concrete class, so swapping is one-line.
Real-LLM calls fail soft: any exception falls back to the mock/keyword behaviour.

LLM_RATIONALE_CLASSES: comma-separated classes for which real-mode rationale text is
generated (default "IMMEDIATE,60_DAY"). Mock mode always renders the template.
"""
from __future__ import annotations

import os
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

LLM_BACKEND: str = os.environ.get("LLM_BACKEND", "mock")
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "llama3.1")
ANTHROPIC_MODEL: str = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5")
LLM_RATIONALE_CLASSES: str = os.environ.get("LLM_RATIONALE_CLASSES", "IMMEDIATE,60_DAY")

SYSTEM_INSTRUCTION = (
    "You are an assistant in a pipeline-corrosion triage system. All numbers, severities, "
    "ERF values and tool results come from deterministic tools and are stated in the prompt. "
    "NEVER change, invent or correct any number or severity class. Reply in 1-3 plain sentences."
)

TAG_HINTS = {
    "[PLAN]": "Summarise the task plan and routing in one or two sentences.",
    "[RISK_RATIONALE]": "Explain in plain words why the anomaly got its triage class, citing the depth, ERF, growth rate and contributing factors given.",
    "[CRITIC]": "Explain the critic verdict comparing the executor class, the independent screen class and the legacy label in one or two sentences.",
    "[WORKORDER]": "Write a short work-order body for the crew, mentioning priority, action and due date.",
    "[SUMMARY]": "Write a short engineer-facing run summary covering the class breakdown and the critic's challenges.",
}


def _normalize_content(content: Any) -> str:
    """Convert list-of-blocks message content to a plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)


def get_chat_model():  # noqa: ANN201
    backend = LLM_BACKEND.lower()
    if backend == "mock":
        from src.llm.mock_model import MockChatModel
        return MockChatModel()
    if backend == "ollama":
        try:
            from langchain_ollama import ChatOllama  # type: ignore
            return ChatOllama(model=OLLAMA_MODEL, temperature=0)
        except ImportError as e:
            raise ImportError("Install -r requirements-llm.txt and run an Ollama server to use LLM_BACKEND='ollama'.") from e
    if backend == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic  # type: ignore
            return ChatAnthropic(model=ANTHROPIC_MODEL, temperature=0, max_tokens=300)
        except ImportError as e:
            raise ImportError("Install -r requirements-llm.txt and set ANTHROPIC_API_KEY to use LLM_BACKEND='anthropic'.") from e
    raise ValueError(f"Unknown LLM_BACKEND={LLM_BACKEND!r}; use 'mock', 'ollama' or 'anthropic'.")


def _tag_for(prompt: str) -> str:
    """Return the first mock-style tag found in the prompt, or ''."""
    for tag in TAG_HINTS:
        if tag in prompt:
            return tag
    return ""


def llm_text(llm, prompt: str) -> str:
    """Call LLM with a prompt and return text content.

    Mock mode: single HumanMessage -> invoke -> content (old behaviour).
    Real mode: prepend a SystemMessage (general instruction + per-tag hint), normalise
    list-of-blocks content to a string; on any exception fall back to the mock model.
    """
    backend = LLM_BACKEND.lower()
    content = _normalize_content(prompt)
    if backend == "mock":
        result = llm.invoke([HumanMessage(content=content)])
        return _normalize_content(result.content)
    # Real mode: system instruction + tag hint + the tagged prompt as human message.
    hint = TAG_HINTS.get(_tag_for(content), "")
    system = SYSTEM_INSTRUCTION + (f" {hint}" if hint else "")
    try:
        result = llm.invoke([
            SystemMessage(content=system),
            HumanMessage(content=content),
        ])
        return _normalize_content(result.content)
    except Exception:
        # Fail soft: fall back to the deterministic mock template.
        from src.llm.mock_model import MockChatModel
        mock = MockChatModel()
        result = mock.invoke([HumanMessage(content=content)])
        return _normalize_content(result.content)


def llm_render_compat(llm, prompt: str) -> str:
    """Backward compatibility for code using llm.render()."""
    return llm_text(llm, prompt)


# ---- Rationale call-volume limiter (real mode only) ----
_MOCK_SINGLETON = None


def _mock_render(prompt: str) -> str:
    """Deterministic template text without instantiating through invoke()."""
    global _MOCK_SINGLETON
    if _MOCK_SINGLETON is None:
        from src.llm.mock_model import MockChatModel
        _MOCK_SINGLETON = MockChatModel()
    return _MOCK_SINGLETON.render(prompt)


def rationale_classes() -> set:
    """Classes eligible for real-mode rationale prose (env LLM_RATIONALE_CLASSES)."""
    return {c.strip().upper() for c in LLM_RATIONALE_CLASSES.split(",") if c.strip()}


def llm_text_or_mock(llm, prompt: str, triage_class: str) -> str:
    """Gate per-anomaly rationale calls.
    Mock mode: deterministic template directly (identical text to MockChatModel rendering).
    Real mode: call the LLM only for anomalies whose class is in LLM_RATIONALE_CLASSES
    (llm_text fails soft to the mock template on error); otherwise mock template directly.
    """
    if LLM_BACKEND.lower() == "mock" or triage_class.upper() not in rationale_classes():
        return _mock_render(prompt)
    return llm_text(llm, prompt)
