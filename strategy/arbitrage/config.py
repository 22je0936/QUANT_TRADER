"""Broker-neutral arbitrage and paper-trading configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .costs import CostConfig

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class ArbitrageConfig:
    symbols: tuple[str, ...] = (
        "RELIANCE",
        "TCS",
        "INFY",
        "HDFCBANK",
        "ICICIBANK",
        "SBIN",
        "ITC",
        "LT",
        "AXISBANK",
        "KOTAKBANK",
    )
    scrip_file: Path = ROOT / "data" / "share_response.json"
    knowledge_base: Path = ROOT / "knowledge_base"
    max_quote_age_seconds: float = 2.0
    cooldown_seconds: float = 5.0
    min_quantity: int = 1
    paper_quantity: int = 1
    min_net_profit: Decimal = Decimal("0.00")
    max_order_notional: Decimal = Decimal("300")
    max_daily_loss: Decimal = Decimal("60")
    max_fallback_loss: Decimal = Decimal("30")
    costs: CostConfig = field(default_factory=CostConfig)
    live_order_timeout_seconds: float = 2.0
    live_order_poll_seconds: float = 0.2
    reconnect_initial_delay: float = 1.0
    reconnect_max_delay: float = 30.0