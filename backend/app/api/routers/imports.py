import datetime as dt
import shutil
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.config import get_settings
from app.database.models import User
from app.domain.import_ai.schemas import AiImportCommitRequest, ImportInterpretationDto
from app.services.ai.import_interpreter import ImportInterpreterError
from app.services.import_ai.reader import SUPPORTED_EXTENSIONS
from app.services.import_ai.service import (
    AiAccountSelection,
    AiEntrySelection,
    AiImportNotConfiguredError,
    ai_preview_import,
    commit_ai_import,
)
from app.services.import_excel.importer import commit_import, preview_import

router = APIRouter(prefix="/api/imports", tags=["imports"])


def _save_upload(file: UploadFile) -> Path:
    settings = get_settings()
    imports_dir = (settings.database_path or Path("data/private/finance.db")).parent / "imports"
    imports_dir.mkdir(parents=True, exist_ok=True)

    timestamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")
    safe_name = Path(file.filename or "upload.xlsx").name
    dest = imports_dir / f"{timestamp}_{safe_name}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    return dest


@router.post("/preview")
def preview(
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Only .xlsx/.xlsm files are supported")

    path = _save_upload(file)
    result = preview_import(db, user.id, str(path))
    return {
        "new_snapshot_count": result.new_snapshot_count,
        "duplicate_count": result.duplicate_count,
        "new_account_names": result.new_account_names,
        "warnings": result.warnings,
        "rows": [
            {
                "account_name": r.account_name,
                "snapshot_date": r.snapshot_date,
                "value": r.value,
                "currency": r.currency,
                "is_new_account": r.is_new_account,
                "is_duplicate": r.is_duplicate,
                "cell": r.cell,
            }
            for r in result.rows
        ],
        "source_path": str(path),
    }


@router.post("/commit")
def commit(
    source_path: str,
    overwrite_duplicates: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    settings = get_settings()
    imports_dir = (settings.database_path or Path("data/private/finance.db")).parent / "imports"
    resolved = Path(source_path).resolve()
    if imports_dir.resolve() not in resolved.parents or not resolved.exists():
        raise HTTPException(
            status_code=404, detail="source_path not found; call /preview first"
        )

    batch = commit_import(db, user.id, str(resolved), overwrite_duplicates=overwrite_duplicates)
    return {
        "import_batch_id": batch.id,
        "status": batch.status,
        "row_count": batch.row_count,
        "notes": batch.notes,
    }


@router.post("/ai-preview", response_model=ImportInterpretationDto)
def ai_preview(file: UploadFile):
    """AI-assisted import for arbitrary spreadsheet/CSV layouts. Never writes
    to the database — returns a proposal for the user to review and edit
    before /ai-commit."""
    filename = (file.filename or "").lower()
    if not any(filename.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Supported: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    path = _save_upload(file)
    settings = get_settings()
    try:
        interpretation = ai_preview_import(settings, str(path))
    except AiImportNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImportInterpreterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ImportInterpretationDto(**asdict(interpretation), source_path=str(path))


@router.post("/ai-commit")
def ai_commit(
    payload: AiImportCommitRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Writes the user-reviewed (and possibly edited) AI import proposal.
    Each entry is applied through set_monthly_value, so re-running this never
    duplicates a month that already has a value — it corrects it."""
    selections = [
        AiAccountSelection(
            name=a.name,
            currency=a.currency,
            type=a.type,
            asset_class=a.asset_class,
            include=a.include,
            entries=[
                AiEntrySelection(date=e.date, value=str(e.value), include=e.include)
                for e in a.entries
            ],
        )
        for a in payload.accounts
    ]
    batch = commit_ai_import(db, user.id, selections)
    return {
        "import_batch_id": batch.id,
        "status": batch.status,
        "row_count": batch.row_count,
    }
