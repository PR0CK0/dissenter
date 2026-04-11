"""Wrappers for competing LLM ensemble tools.

Each wrapper runs an external tool (llm-council, llm-consortium, consilium)
over the same benchmark dataset we use for dissenter. They implement a
common Competitor interface so the runner can drive them identically.

All competitor wrappers are *best-effort*: I don't use these tools
day-to-day, so the exact CLI invocation may need adjustment. Each
wrapper has a `validate()` method that checks the tool is installed and
callable — run that first before a real benchmark run.

Paper context: none of these tools have published benchmark numbers,
so running dissenter alongside them on standardized datasets is itself
a contribution.
"""
from .base import Competitor, CompetitorResult, CompetitorError
from .llm_council import LLMCouncil
from .llm_consortium import LLMConsortium
from .consilium import Consilium

__all__ = [
    "Competitor",
    "CompetitorResult",
    "CompetitorError",
    "LLMCouncil",
    "LLMConsortium",
    "Consilium",
]
