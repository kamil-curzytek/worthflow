"""Data shapes for AI-assisted import.

An AI provider only ever proposes this structure — it never writes to the
database itself. The user reviews and confirms (or edits) the proposal in the
dashboard; only then does app/services/import_ai/service.py turn it into
actual accounts and snapshots, through the same set_monthly_value used by the
Monthly Values grid.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProposedEntry:
    date: str  # ISO date (YYYY-MM-DD)
    value: str  # plain decimal string


@dataclass
class ProposedAccount:
    source_label: str  # the row/column label as it appeared in the file
    suggested_name: str
    suggested_currency: str
    suggested_type: str
    suggested_asset_class: str
    entries: list[ProposedEntry] = field(default_factory=list)


@dataclass
class ImportInterpretation:
    summary: str
    accounts: list[ProposedAccount] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
