"""Risk management: every order MUST pass through RiskManager.validate_order before
reaching a broker. No bypass path is permitted from strategies or services.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from src.core.entities import Order, Position
from src.core.exceptions import RiskLimitBreachedError
from src.infra.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class RiskLimits:
    max_daily_loss: Decimal = Decimal("25000")
    max_position_size: Decimal = Decimal("100000")
    max_order_quantity: int = 1000
    max_exposure_per_symbol: Decimal = Decimal("200000")


@dataclass(slots=True)
class RiskState:
    """Mutable, per-session risk tracking state."""

    realized_pnl_today: Decimal = Decimal("0")
    positions: dict[str, Position] = field(default_factory=dict)
    kill_switch_engaged: bool = False


class RiskManager:
    """Pre-trade and post-trade risk checks sitting between StrategyRunner and IBrokerGateway."""

    def __init__(self, limits: RiskLimits | None = None, state: RiskState | None = None) -> None:
        self.limits = limits or RiskLimits()
        self.state = state or RiskState()

    def validate_order(self, order: Order) -> None:
        if self.state.kill_switch_engaged:
            raise RiskLimitBreachedError("Kill-switch engaged: all new orders are blocked")

        if order.quantity > self.limits.max_order_quantity:
            raise RiskLimitBreachedError(
                f"Order quantity {order.quantity} exceeds max_order_quantity "
                f"{self.limits.max_order_quantity}"
            )

        if self.state.realized_pnl_today <= -self.limits.max_daily_loss:
            self.engage_kill_switch("Daily loss limit already breached")
            raise RiskLimitBreachedError("Daily loss limit breached — kill-switch engaged")

        projected_exposure = self._projected_exposure(order)
        if projected_exposure > self.limits.max_exposure_per_symbol:
            raise RiskLimitBreachedError(
                f"Projected exposure {projected_exposure} for {order.instrument_id} "
                f"exceeds max_exposure_per_symbol {self.limits.max_exposure_per_symbol}"
            )

    def record_fill_pnl(self, realized_pnl_delta: Decimal) -> None:
        self.state.realized_pnl_today += realized_pnl_delta
        if self.state.realized_pnl_today <= -self.limits.max_daily_loss:
            self.engage_kill_switch("Daily loss limit breached after fill")

    def engage_kill_switch(self, reason: str) -> None:
        self.state.kill_switch_engaged = True
        logger.warning("risk_kill_switch_engaged", reason=reason)

    def reset_daily_state(self) -> None:
        self.state.realized_pnl_today = Decimal("0")
        self.state.kill_switch_engaged = False

    def _projected_exposure(self, order: Order) -> Decimal:
        existing = self.state.positions.get(order.instrument_id)
        existing_qty = Decimal(existing.quantity) if existing else Decimal(0)
        existing_price = existing.average_price if existing else Decimal(0)
        price_hint = order.price or existing_price or Decimal(0)
        projected_qty = existing_qty + Decimal(order.quantity)
        return abs(projected_qty) * price_hint
