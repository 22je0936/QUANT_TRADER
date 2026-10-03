"""Configuration for the Angel One NSE/BSE arbitrage watcher."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .costs import CostConfig

ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class ArbitrageConfig:
    # ------------------------------------------------------------
    # 1) Which stocks should the bot watch?
    # ------------------------------------------------------------
    # These are stock symbols from the NSE/BSE market data feed.
    # The bot will only look for arbitrage opportunities in these names.
    symbols: tuple[str, ...] = (
        "HDFCBANK",
        "SOBHA",
    )

    # File locations used by the bot.
    scrip_file: Path = ROOT / "data" / "share_response.json"
    knowledge_base: Path = ROOT / "knowledge_base"

    # ------------------------------------------------------------
    # 2) Data freshness and trade cooldown rules
    # ------------------------------------------------------------
    # A quote is considered stale if it is older than this many seconds.
    # This prevents the bot from acting on delayed market data.
    max_quote_age_seconds: float = 2.0

    # After an opportunity is detected, wait this long before considering the same symbol again.
    # This avoids repeated trades on the same tiny spread.
    cooldown_seconds: float = 5.0

    # ------------------------------------------------------------
    # 3) Order sizing rules
    # ------------------------------------------------------------
    # Minimum number of shares to trade in one opportunity.
    min_quantity: int = 1

    # Maximum number of shares per order for a single trade leg.
    # This is a very strict safety cap.
    max_order_quantity: int = 1

    # Maximum rupee value of a single order.
    # Example: if stock price is Rs. 180 and quantity is 2, notional = 360 > 300, so it is blocked.
    max_order_notional: Decimal = Decimal("2500")

    # ------------------------------------------------------------
    # 4) Profit and risk rules
    # ------------------------------------------------------------
    # Minimum net profit needed before the bot considers an arbitrage trade worth taking.
    min_net_profit: Decimal = Decimal("5.00")

    # Hard daily loss cap in rupees.
    # If total realized loss crosses this number, the bot stops trading for the day.
    max_daily_loss: Decimal = Decimal("60")

    # Maximum acceptable loss if the fallback leg cannot close the position cleanly.
    max_fallback_loss: Decimal = Decimal("30")

    # Transaction cost model used to estimate real profit after fees.
    costs: CostConfig = field(default_factory=CostConfig)

    # ------------------------------------------------------------
    # 5) Live order handling
    # ------------------------------------------------------------
    # How long to wait for an order to reach terminal status before cancelling / reconciling.
    live_order_timeout_seconds: float = 2.0

    # Poll interval while checking the order status.
    live_order_poll_seconds: float = 0.2

    # Delay before retrying the market-data feed if it disconnects.
    reconnect_initial_delay: float = 1.0
    reconnect_max_delay: float = 30.0