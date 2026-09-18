"""Liveness/readiness endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from src.api.schemas import HealthResponse
from src.config.settings import get_settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", broker_provider=settings.broker_provider)
