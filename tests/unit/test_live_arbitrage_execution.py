from __future__ import annotations

import csv
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from src.core.entities import Exchange, Order, OrderStatus, TransactionType
from src.risk.risk_manager import RiskLimits, RiskManager, RiskState
from strategy.arbitrage.config import ArbitrageConfig
from strategy.arbitrage.costs import CostCalculator
from strategy.arbitrage.instruments import Instrument
from strategy.arbitrage.live_execution import LiveArbitrageExecutor
from strategy.arbitrage.models import ArbitrageOpportunity, CostBreakdown, MarketQuote
from strategy.arbitrage.storage import CsvJournal


class FakeGateway:
    def __init__(self, outcomes: dict[tuple[str, str], tuple[OrderStatus, int, str]]) -> None:
        self.outcomes = outcomes
        self.orders: dict[str, Order] = {}
        self.placed: list[Order] = []

    def place_order(self, order: Order) -> Order:
        order.broker_order_id = f"BROKER-{len(self.placed) + 1}"
        order.status = OrderStatus.OPEN
        self.orders[order.client_order_id] = order
        self.placed.append(order)
        return order

    def get_order_status(self, client_order_id: str) -> Order:
        order = self.orders[client_order_id]
        status, filled, average_price = self.outcomes[(order.exchange.value, order.transaction_type.value)]
        order.status = status
        order.filled_quantity = filled
        order.average_price = Decimal(average_price) if filled else None
        return order

    def cancel_order(self, client_order_id: str) -> Order:
        order = self.orders[client_order_id]
        order.status = OrderStatus.CANCELLED
        return order

    def modify_order(self, client_order_id: str, **changes: object) -> Order:
        return self.orders[client_order_id]

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def get_positions(self):
        return []

    def get_holdings(self):
        return []

    def get_margins(self):
        return {}


def _opportunity() -> ArbitrageOpportunity:
    costs = CostBreakdown(*(Decimal("0") for _ in range(6)))
    timestamp = datetime.now(timezone.utc)
    return ArbitrageOpportunity(
        opportunity_id="OPP-1",
        symbol="TEST",
        detected_at=timestamp,
        buy_exchange="NSE",
        sell_exchange="BSE",
        buy_price=Decimal("100"),
        sell_price=Decimal("103"),
        quantity=1,
        gross_profit=Decimal("3"),
        costs=costs,
        estimated_net_profit=Decimal("3"),
        buy_quote_timestamp=timestamp,
        sell_quote_timestamp=timestamp,
    )


def _instrument(exchange: str, token: str) -> Instrument:
    return Instrument(
        name="TEST",
        exchange=exchange,
        symbol="TEST-EQ",
        token=token,
        tick_size=Decimal("0.05"),
    )


def _executor(tmp_path: Path, gateway: FakeGateway, quotes: dict[str, MarketQuote]):
    config = replace(
        ArbitrageConfig(symbols=("TEST",), knowledge_base=tmp_path, live_order_timeout_seconds=0.01),
        max_order_notional=Decimal("300"),
        max_daily_loss=Decimal("60"),
        max_fallback_loss=Decimal("30"),
    )
    risk = RiskManager(
        RiskLimits(
            max_daily_loss=config.max_daily_loss,
            max_position_size=config.max_order_notional,
            max_order_quantity=config.paper_quantity,
            max_exposure_per_symbol=config.max_order_notional,
        )
    )
    executor = LiveArbitrageExecutor(
        gateway,
        risk,
        config,
        CostCalculator(),
        CsvJournal(tmp_path),
        lambda _symbol: quotes,
    )
    return executor, risk


def _quotes(nse_bid: str = "99", bse_bid: str = "103") -> dict[str, MarketQuote]:
    timestamp = datetime.now(timezone.utc)
    return {
        "NSE": MarketQuote("TEST", "NSE", Decimal(nse_bid), 5, Decimal("100"), 5, timestamp),
        "BSE": MarketQuote("TEST", "BSE", Decimal(bse_bid), 5, Decimal("104"), 5, timestamp),
    }


def test_live_executor_places_both_exchange_legs_and_journals_fills(tmp_path: Path):
    gateway = FakeGateway(
        {
            ("NSE", "BUY"): (OrderStatus.FILLED, 1, "100"),
            ("BSE", "SELL"): (OrderStatus.FILLED, 1, "103"),
        }
    )
    executor, risk = _executor(tmp_path, gateway, _quotes())

    report = executor.execute(_opportunity(), _instrument("NSE", "1"), _instrument("BSE", "2"))

    assert report.status == "CLOSED"
    assert report.bought_quantity == report.sold_quantity == 1
    assert report.open_quantity == 0
    assert [order.exchange for order in gateway.placed] == [Exchange.NSE, Exchange.BSE]
    assert [order.transaction_type for order in gateway.placed] == [
        TransactionType.BUY,
        TransactionType.SELL,
    ]
    assert not risk.state.kill_switch_engaged
    journal = CsvJournal(tmp_path)
    with (tmp_path / "live_executions.csv").open(encoding="utf-8") as source:
        assert next(csv.DictReader(source))["status"] == "CLOSED"
    assert journal.get_live_daily_pnl(date.today()) == report.estimated_net_pnl
    journal.ensure_live_state_reconciled()


def test_live_executor_falls_back_on_buy_exchange_when_cross_sell_is_rejected(tmp_path: Path):
    gateway = FakeGateway(
        {
            ("NSE", "BUY"): (OrderStatus.FILLED, 1, "100"),
            ("BSE", "SELL"): (OrderStatus.REJECTED, 0, "0"),
            ("NSE", "SELL"): (OrderStatus.FILLED, 1, "99"),
        }
    )
    executor, risk = _executor(tmp_path, gateway, _quotes(nse_bid="99"))

    report = executor.execute(_opportunity(), _instrument("NSE", "1"), _instrument("BSE", "2"))

    assert report.status == "CLOSED"
    assert report.fallback_exchange == "NSE"
    assert report.open_quantity == 0
    assert [order.exchange for order in gateway.placed] == [Exchange.NSE, Exchange.BSE, Exchange.NSE]
    assert gateway.placed[-1].price == Decimal("99")
    assert not risk.state.kill_switch_engaged


def test_live_executor_blocks_fallback_beyond_loss_cap_and_killswitches(tmp_path: Path):
    gateway = FakeGateway(
        {
            ("NSE", "BUY"): (OrderStatus.FILLED, 1, "100"),
            ("BSE", "SELL"): (OrderStatus.REJECTED, 0, "0"),
        }
    )
    executor, risk = _executor(tmp_path, gateway, _quotes(nse_bid="50"))

    report = executor.execute(_opportunity(), _instrument("NSE", "1"), _instrument("BSE", "2"))

    assert report.status == "UNHEDGED"
    assert report.open_quantity == 1
    assert len(gateway.placed) == 2
    assert risk.state.kill_switch_engaged
