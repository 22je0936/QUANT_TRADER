"""Risk gate for paper arbitrage opportunities."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from src.infra.logging import get_logger

from .config import ArbitrageConfig
from .models import ArbitrageOpportunity, RiskDecision

logger = get_logger(__name__)


class OpportunityRiskManager:
    """Approve only bounded, cost-positive opportunities."""

    def __init__(self, config: ArbitrageConfig) -> None:
        self.config = config
        self.realized_pnl = Decimal("0")
        self.kill_switch_engaged = False

    def validate(self, opportunity: ArbitrageOpportunity) -> RiskDecision:
        reason = "approved"
        notional = opportunity.buy_price * opportunity.quantity
        if self.kill_switch_engaged:
            reason = "daily loss kill switch is engaged"
        elif opportunity.quantity > self.config.max_order_quantity:
            reason = "quantity exceeds configured order limit"
        elif notional > self.config.max_order_notional:
            reason = "buy notional exceeds configured limit"
        elif opportunity.estimated_net_profit < self.config.min_net_profit:
            reason = "estimated net profit does not exceed configured minimum"

        decision = RiskDecision(
            approved=reason == "approved",
            reason=reason,
            checked_at=datetime.now(timezone.utc),
        )
        if decision.approved:
            logger.info(
                "arbitrage_risk_approved",
                opportunity_id=opportunity.opportunity_id,
                symbol=opportunity.symbol,
                quantity=opportunity.quantity,
            )
        else:
            logger.warning(
                "arbitrage_risk_rejected",
                opportunity_id=opportunity.opportunity_id,
                symbol=opportunity.symbol,
                reason=reason,
            )
        return decision

    def record_realized_pnl(self, pnl: Decimal) -> None:
        self.realized_pnl += pnl
        if self.realized_pnl <= -self.config.max_daily_loss:
            self.engage_kill_switch(
                f"daily loss limit reached: realized_pnl={self.realized_pnl}"
            )

    def engage_kill_switch(self, reason: str) -> None:
        self.kill_switch_engaged = True
        logger.error("arbitrage_kill_switch_engaged", reason=reason)