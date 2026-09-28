from __future__ import annotations

from app.config import Settings
from app.services.ai.provider import (
    AIProvider,
    LocalNullProvider,
    StructuredAnalysis,
    StructuredFinancialData,
)


class ExternalAIConsentRequiredError(Exception):
    """Raised when a non-local provider is selected but external data sharing wasn't allowed."""


class AIAnalysisService:
    """Gate that enforces the privacy contract before any provider runs.

    Financial data reaches a non-local provider only if BOTH ai_analysis_enabled
    and ai_allow_external_data are explicitly true in configuration.
    """

    def __init__(self, settings: Settings, provider: AIProvider | None = None):
        self._settings = settings
        self._provider = provider or LocalNullProvider()

    def analyze(self, data: StructuredFinancialData) -> StructuredAnalysis:
        if not self._settings.ai_analysis_enabled:
            return LocalNullProvider().analyze(data)

        if self._provider.name != "local" and not self._settings.ai_allow_external_data:
            raise ExternalAIConsentRequiredError(
                "AI_ALLOW_EXTERNAL_DATA must be explicitly enabled before financial data "
                f"can be sent to the {self._provider.name!r} provider."
            )

        return self._provider.analyze(data)
