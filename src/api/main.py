"""FastAPI application entrypoint. Run with:
uvicorn src.api.main:app --reload
"""
from __future__ import annotations

from fastapi import FastAPI

from src.api.routers import health, orders, positions
from src.infra.logging import configure_logging

configure_logging()

app = FastAPI(
    title="Quant Trader Engine",
    version="0.1.0",
    description="Broker-agnostic quantitative trading engine (Angel One -> Kite).",
)

app.include_router(health.router)
app.include_router(orders.router)
app.include_router(positions.router)
