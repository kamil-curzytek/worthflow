"""Anthropic-backed ImportInterpreterProvider.

Uses the Messages API directly over httpx (no SDK dependency, consistent with
how the exchange-rate provider is built) since the only thing needed is one
request/response round trip.
"""

from __future__ import annotations

import json
import re

import httpx

from app.database.models import AccountType, AssetClass
from app.domain.currencies.currency import SUPPORTED_CURRENCIES
from app.net import ensure_system_trust_store
from app.services.ai.import_interpreter import ImportInterpreterError, ImportInterpreterProvider
from app.services.ai.import_types import ImportInterpretation, ProposedAccount, ProposedEntry

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

_VALID_TYPES = {t.value for t in AccountType}
_VALID_ASSET_CLASSES = {a.value for a in AssetClass}
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SYSTEM_PROMPT = """You are a data-mapping assistant for a personal finance app. You will be \
given a raw dump of a spreadsheet or CSV file that represents someone's financial account \
balances over time, in an unknown layout (accounts might be rows or columns; there might be \
extra sheets, totals, or unrelated data mixed in).

Your ONLY job is to propose a structured mapping from the raw file to normalized accounts and \
dated balance entries. You never compute totals, growth, or any other arithmetic — you only \
identify and transcribe what's already in the file.

Respond with ONLY a single JSON object — no markdown code fences, no commentary before or \
after — matching exactly this schema:

{
  "summary": "<one or two plain-English sentences: what you found, how you interpreted it>",
  "accounts": [
    {
      "source_label": "<the label exactly as it appeared in the file>",
      "suggested_name": "<a clean, human-readable account name>",
      "suggested_currency": "EUR | USD | PLN",
      "suggested_type": "checking|savings|brokerage|cash|crypto|pension|equity_compensation|other",
      "suggested_asset_class": "cash | trading | crypto | equity_compensation | other",
      "entries": [ {"date": "YYYY-MM-DD", "value": "1234.56"} ]
    }
  ],
  "warnings": ["<anything ambiguous, skipped, or uncertain, naming the specific row/column>"]
}

Rules:
- Only use EUR, USD, or PLN for suggested_currency. If truly unclear, use EUR and add a warning \
naming the account.
- "value" must be a plain decimal string: no currency symbols, no thousand separators.
- "date" must be a real calendar date. If the file only gives a month and year, use the 1st of \
that month.
- Skip rows/columns that are clearly totals, subtotals, percentages, category rollups, or other \
values computed FROM the other rows — name them in "warnings" instead of listing them as accounts.
- If a row/column doesn't look like a financial account balance at all (e.g. unrelated data \
sharing the same file), leave it out and say so in "warnings".
- If you cannot confidently find any accounts, return an empty "accounts" list and explain why \
in "summary".
"""


class AnthropicImportInterpreter(ImportInterpreterProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str, timeout: float = 60.0) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def interpret(self, file_text: str) -> ImportInterpretation:
        ensure_system_trust_store()
        try:
            response = httpx.post(
                API_URL,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": API_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": 8000,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": file_text}],
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()
            text = "".join(
                block.get("text", "")
                for block in data.get("content", [])
                if block.get("type") == "text"
            )
        except httpx.HTTPError as exc:
            raise ImportInterpreterError(f"Could not reach the {self.name} API: {exc}") from exc

        return _parse_interpretation(text)


def _parse_interpretation(text: str) -> ImportInterpretation:
    payload = _extract_json(text)

    accounts = []
    warnings = list(payload.get("warnings", []))
    for raw_account in payload.get("accounts", []):
        account, account_warnings = _sanitize_account(raw_account)
        accounts.append(account)
        warnings.extend(account_warnings)

    return ImportInterpretation(
        summary=str(payload.get("summary", "")),
        accounts=accounts,
        warnings=warnings,
    )


def _extract_json(text: str) -> dict:
    text = text.strip()
    # Strip a markdown code fence if the model added one despite instructions.
    fence_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass
        snippet = text[:300]
        raise ImportInterpreterError(
            f"The AI response wasn't valid JSON. First 300 chars: {snippet!r}"
        ) from None


def _sanitize_account(raw: dict) -> tuple[ProposedAccount, list[str]]:
    warnings: list[str] = []
    label = str(raw.get("source_label", "")) or "(unknown)"
    name = str(raw.get("suggested_name", "")) or label

    currency = str(raw.get("suggested_currency", "")).upper()
    if currency not in SUPPORTED_CURRENCIES:
        warnings.append(f"{label}: unrecognized currency {currency!r} — defaulted to EUR")
        currency = "EUR"

    account_type = str(raw.get("suggested_type", ""))
    if account_type not in _VALID_TYPES:
        warnings.append(
            f"{label}: unrecognized account type {account_type!r} — defaulted to 'other'"
        )
        account_type = "other"

    asset_class = str(raw.get("suggested_asset_class", ""))
    if asset_class not in _VALID_ASSET_CLASSES:
        warnings.append(
            f"{label}: unrecognized asset class {asset_class!r} — defaulted to 'other'"
        )
        asset_class = "other"

    entries = []
    for raw_entry in raw.get("entries", []):
        date = str(raw_entry.get("date", ""))
        value = str(raw_entry.get("value", ""))
        if not _DATE_PATTERN.match(date):
            warnings.append(f"{label}: skipped entry with unparseable date {date!r}")
            continue
        try:
            float(value)
        except ValueError:
            warnings.append(f"{label}: skipped entry with non-numeric value {value!r}")
            continue
        entries.append(ProposedEntry(date=date, value=value))

    return (
        ProposedAccount(
            source_label=label,
            suggested_name=name,
            suggested_currency=currency,
            suggested_type=account_type,
            suggested_asset_class=asset_class,
            entries=entries,
        ),
        warnings,
    )
