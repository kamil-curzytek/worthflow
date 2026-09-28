"""AI-assisted import: gating, preview, and commit.

Preview never writes to the database — it only calls the configured AI
provider and returns its proposal. Nothing is saved until the user reviews
the proposal (in the dashboard) and calls commit_ai_import with their
selections, which reuses snapshots_service.set_monthly_value so an AI-assisted
value for a month that already has one corrects it in place rather than
duplicating it — the same rule the Monthly Values grid follows.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import Settings
from app.database.models import AccountType, AssetClass, ImportBatch, ImportStatus, SnapshotSource
from app.services import accounts_service, snapshots_service
from app.services.ai.anthropic_import_interpreter import AnthropicImportInterpreter
from app.services.ai.import_interpreter import ImportInterpreterProvider
from app.services.ai.import_types import ImportInterpretation
from app.services.import_ai.reader import read_file_as_text


class AiImportNotConfiguredError(Exception):
    """AI-assisted import isn't usable with the current configuration."""


def build_import_interpreter(settings: Settings) -> ImportInterpreterProvider:
    if not settings.ai_analysis_enabled or not settings.ai_allow_external_data:
        raise AiImportNotConfiguredError(
            "AI-assisted import is off. It sends your file's contents to an external AI "
            "provider, so it requires both AI_ANALYSIS_ENABLED=true and "
            "AI_ALLOW_EXTERNAL_DATA=true in your .env — see the README."
        )
    if settings.ai_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise AiImportNotConfiguredError("ANTHROPIC_API_KEY is not set in your .env.")
        return AnthropicImportInterpreter(
            api_key=settings.anthropic_api_key, model=settings.ai_model
        )
    raise AiImportNotConfiguredError(
        f"AI provider {settings.ai_provider!r} does not support AI-assisted import yet."
    )


def ai_preview_import(settings: Settings, file_path: str) -> ImportInterpretation:
    interpreter = build_import_interpreter(settings)
    file_text = read_file_as_text(file_path)
    return interpreter.interpret(file_text)


class AiEntrySelection:
    def __init__(self, date: dt.date, value: str, include: bool = True):
        self.date = date
        self.value = value
        self.include = include


class AiAccountSelection:
    def __init__(
        self,
        name: str,
        currency: str,
        type: AccountType,
        asset_class: AssetClass,
        entries: list[AiEntrySelection],
        include: bool = True,
    ):
        self.name = name
        self.currency = currency
        self.type = type
        self.asset_class = asset_class
        self.entries = entries
        self.include = include


def commit_ai_import(
    db: Session, user_id: str, selections: list[AiAccountSelection]
) -> ImportBatch:
    batch = ImportBatch(
        source_filename="AI-assisted import", status=ImportStatus.PENDING, row_count=0
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    written = 0
    try:
        for selection in selections:
            if not selection.include:
                continue
            account = accounts_service.get_or_create_account(
                db,
                user_id,
                name=selection.name,
                type=selection.type,
                asset_class=selection.asset_class,
                currency=selection.currency,
            )
            for entry in selection.entries:
                if not entry.include:
                    continue
                snapshots_service.set_monthly_value(
                    db,
                    account=account,
                    year=entry.date.year,
                    month=entry.date.month,
                    value=Decimal(entry.value),
                    source=SnapshotSource.MANUAL,
                    note="AI-assisted import",
                )
                written += 1

        batch.row_count = written
        batch.status = ImportStatus.COMMITTED
        db.commit()
    except Exception:
        batch.status = ImportStatus.FAILED
        db.commit()
        raise

    db.refresh(batch)
    return batch
