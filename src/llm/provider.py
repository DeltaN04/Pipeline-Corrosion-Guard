"""LLM provider interface. Swap backends by changing ONE config value.

LLM_BACKEND = "mock"   -> MockChatModel (deterministic, offline, default)
LLM_BACKEND = "ollama" -> real Ollama model via langchain-ollama (future scope, needs extra dep + server)

All agents call get_chat_model(), never a concrete class, so swapping is one-line.
"""
from __future__ import annotations

LLM_BACKEND: str = "mock"
OLLAMA_MODEL: str = "llama3.1"


def get_chat_model():  # noqa: ANN201
    if LLM_BACKEND == "mock":
        from src.llm.mock_model import MockChatModel

        return MockChatModel()
    if LLM_BACKEND == "ollama":  # future scope
        try:
            from langchain_ollama import ChatOllama  # type: ignore

            return ChatOllama(model=OLLAMA_MODEL)
        except ImportError as e:
            raise ImportError("Install langchain-ollama and run an Ollama server to use LLM_BACKEND='ollama'.") from e
    raise ValueError(f"Unknown LLM_BACKEND={LLM_BACKEND!r}; use 'mock' or 'ollama'.")
