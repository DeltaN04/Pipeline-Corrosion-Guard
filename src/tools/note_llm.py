"""LLM-assisted inspector-note assessment (raise-only, fail-soft).

Keyword scanning is always the baseline. In real-LLM mode the model may only RAISE
the severe flag (never lower it), and never touches any number or severity class.
All LLM failures fall back to keyword behaviour.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, List, Optional, Tuple

from pydantic import BaseModel, Field

from src.llm import provider as _provider
from src.tools.lookup import SEVERE_KEYWORDS, note_keywords


class NoteAssessment(BaseModel):
    """Structured assessment of an inspector note (LLM output only; prose + raise-only flag)."""

    severe: bool = Field(description="True if the note describes severe/dangerous metal loss, even without trigger keywords.")
    contradicts_numbers: bool = Field(description="True if the note implies the numeric depth field understates the real severity.")
    reason: str = Field(description="One plain-sentence explanation of the assessment.")


def _structured_assess(llm, note: str, depth_pct: Optional[float]) -> Optional[NoteAssessment]:
    """Ask the LLM for a structured NoteAssessment; None on any failure."""
    if not hasattr(llm, "with_structured_output"):
        return None
    human = (
        f"Reported metal-loss depth: {depth_pct} % of wall thickness.\n"
        f"Inspector note: {note}\n"
        f"Known trigger keywords: {', '.join(SEVERE_KEYWORDS)}\n"
        "Assess the note. You may only raise severity concerns; never lower them and never change numbers."
    )
    out = llm.with_structured_output(NoteAssessment).invoke([human])
    if isinstance(out, BaseModel):
        out = out.model_dump()
    return NoteAssessment.model_validate(out)


@lru_cache(maxsize=4096)
def _cached_keyword_result(note_key: str, depth_key: Optional[float]) -> Tuple[List[str], bool, str]:
    """Deterministic keyword baseline (cacheable)."""
    flags, severe = note_keywords(note_key)
    return flags, severe, "keyword"


def assess_note(
    llm,
    note: Optional[str],
    depth_pct: Optional[float],
) -> Tuple[List[str], bool, str]:
    """Assess an inspector note -> (flags, severe, reason).

    - Always computes keyword flags first.
    - Mock backend or empty note: returns the keyword result unchanged.
    - Real mode: LLM may only RAISE severe (or lower it); on any exception,
      returns keyword result with reason "keyword_fallback".
    """
    flags, kw_severe = note_keywords(note)
    if not note or _provider.LLM_BACKEND.lower() == "mock":
        return flags, kw_severe, "keyword"

    depth_key = round(float(depth_pct)) if depth_pct is not None else None
    try:
        assessment = _structured_assess(llm, note, depth_pct)
        if assessment is None:
            return flags, kw_severe, "keyword"
        severe = kw_severe or assessment.severe or assessment.contradicts_numbers  # raise only
        return flags, severe, (assessment.reason or "llm")
    except Exception:
        return flags, kw_severe, "keyword_fallback"
