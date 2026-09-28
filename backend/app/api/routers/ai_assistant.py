from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_fx_service
from app.config import get_settings
from app.domain.ai_assistant.schemas import ChatRequest, ChatResponse
from app.domain.currencies.currency import UnsupportedCurrencyError, validate_currency
from app.services.ai.assistant_provider import AssistantMessage, AssistantProviderError
from app.services.ai_assistant.service import AiAssistantNotConfiguredError, chat
from app.services.exchange_rates.service import ExchangeRateService

router = APIRouter(prefix="/api/ai-assistant", tags=["ai-assistant"])


@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    fx: ExchangeRateService = Depends(get_fx_service),
):
    """Stateless: the frontend resends the full conversation each turn.
    Nothing here is persisted — no chat history touches the database."""
    try:
        currency = validate_currency(payload.currency)
    except UnsupportedCurrencyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not payload.messages or payload.messages[-1].role != "user":
        raise HTTPException(
            status_code=422, detail="messages must be non-empty and end with a user turn"
        )

    settings = get_settings()
    try:
        reply = chat(
            db,
            fx,
            settings,
            target_currency=currency,
            goal=payload.goal,
            messages=[AssistantMessage(role=m.role, content=m.content) for m in payload.messages],
        )
    except AiAssistantNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AssistantProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ChatResponse(reply=reply)
