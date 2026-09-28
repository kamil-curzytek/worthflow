from __future__ import annotations

from pydantic import BaseModel, Field


class ChatMessageDto(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    currency: str = "EUR"
    goal: str = ""
    messages: list[ChatMessageDto]


class ChatResponse(BaseModel):
    reply: str
