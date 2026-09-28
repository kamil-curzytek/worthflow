"""AI provider + analysis abstraction — an extension point, not a built feature yet.

Deliberately minimal for now (see docs/architecture.md, Phase 7). The contract
is fixed early so the calculation engine and API never need to change shape
when real AI analysis is added later: AI always receives already-computed,
deterministic StructuredFinancialData and returns a StructuredAnalysis — it
never does the arithmetic itself.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StructuredFinancialData:
    """Deterministic output of the calculation engine, handed to AI as input."""

    display_currency: str
    period_start: str
    period_end: str
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class StructuredAnalysis:
    summary: str
    observations: list[str] = field(default_factory=list)
    trends: list[str] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class AIProvider(ABC):
    name: str

    @abstractmethod
    def analyze(self, data: StructuredFinancialData) -> StructuredAnalysis:
        raise NotImplementedError


class LocalNullProvider(AIProvider):
    """Default provider: no external call, no analysis. Always available, always private."""

    name = "local"

    def analyze(self, data: StructuredFinancialData) -> StructuredAnalysis:
        return StructuredAnalysis(
            summary="AI analysis is disabled. Enable it in configuration to get insights.",
        )
