from __future__ import annotations

import csv
import json
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from src.brokers.angel_one.arbitrage_feed import AngelOneArbitrageFeed
from src.config.settings import get_settings
from strategy.arbitrage.config import ArbitrageConfig
from strategy.arbitrage.costs import CostCalculator, CostConfig
from strategy.arbitrage.engine import ArbitrageEngine
from strategy.arbitrage.instruments import load_instruments
from strategy.arbitrage.models import MarketQuote
from strategy.arbitrage.paper_execution import PaperExecutor
from strategy.arbitrage.risk import OpportunityRiskManager
from strategy.arbitrage.runner import ArbitrageApplication
from strategy.arbitrage.storage import CsvJournal


def _config(**changes: Any) -> ArbitrageConfig:
    return replace(
        ArbitrageConfig(symbols=("TEST",), cooldown_seconds=0),
        **changes,
    )


def _quote(
    exchange: str,
    timestamp: datetime,
    bid: str = "99",
    bid_quantity: int = 5,
    ask: str = "100",
    ask_quantity: int = 5,
) -> MarketQuote:
    return MarketQuote(
        symbol="TEST",
        exchange=exchange,  # type: ignore[arg-type]
        bid=Decimal(bid),
        bid_quantity=bid_quantity,
        ask=Decimal(ask),
        ask_quantity=ask_quantity,
        timestamp=timestamp,
    )


def _opportunity(config: ArbitrageConfig | None = None):
    now = datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc)
    engine = ArbitrageEngine(config or _config(), CostCalculator())
    engine.update_quote(_quote("NSE", now), now)
    opportunity = engine.update_quote(
        _quote("BSE", now, bid="103", ask="104"), now
    )
    assert opportunity is not None
    return now, engine, opportunity


def test_load_instruments_uses_broker_neutral_exchange_token_keys(tmp_path: Path):
    scrip_file = tmp_path / "scrips.json"
    scrip_file.write_text(
        json.dumps(
            [
                {"name": "AAA", "exch_seg": "NSE", "symbol": "AAA-EQ", "token": "1"},
                {"name": "AAA", "exch_seg": "BSE", "symbol": "AAA", "token": "2"},
                {"name": "BBB", "exch_seg": "NSE", "symbol": "BBB-EQ", "token": "3"},
            ]
        ),
        encoding="utf-8",
    )

    catalog = load_instruments(scrip_file, ("AAA", "BBB"))

    assert catalog.by_token[("NSE", "1")] == ("AAA", "NSE")
    assert catalog.missing_names == ("BBB",)


def test_engine_detects_bid_ask_opportunity_after_costs():
    _, _, opportunity = _opportunity()

    assert opportunity.buy_exchange == "NSE"
    assert opportunity.sell_exchange == "BSE"
    assert opportunity.estimated_net_profit > 0
    assert opportunity.estimated_net_profit < opportunity.gross_profit


def test_market_quote_rejects_naive_timestamps_and_invalid_prices():
    with pytest.raises(ValueError, match="timezone"):
        _quote("NSE", datetime(2026, 10, 2, 10, 0))
    with pytest.raises(ValueError, match="positive prices"):
        _quote("NSE", datetime.now(timezone.utc), bid="0")


def test_engine_rejects_unsynchronized_and_stale_quotes():
    now = datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc)
    engine = ArbitrageEngine(_config(max_quote_age_seconds=1), CostCalculator())
    engine.update_quote(_quote("NSE", now), now)

    assert engine.update_quote(
        _quote("BSE", now + timedelta(seconds=2), bid="103", ask="104"),
        now + timedelta(seconds=2),
    ) is None


def test_cost_calculator_rates_are_configurable():
    _, _, opportunity = _opportunity()
    expensive_costs = CostCalculator(
        CostConfig(brokerage_rate=Decimal("0.01"), brokerage_cap_per_order=Decimal("100"))
    ).calculate(
        opportunity.buy_price,
        opportunity.sell_price,
        opportunity.quantity,
        opportunity.buy_exchange,
        opportunity.sell_exchange,
    )
    normal_costs = CostCalculator().calculate(
        opportunity.buy_price,
        opportunity.sell_price,
        opportunity.quantity,
        opportunity.buy_exchange,
        opportunity.sell_exchange,
    )

    assert expensive_costs.total > normal_costs.total


def test_risk_gate_rejects_excess_order_notional():
    config = _config(max_order_notional=Decimal("50"))
    _, _, opportunity = _opportunity(config)

    decision = OpportunityRiskManager(config).validate(opportunity)

    assert not decision.approved
    assert decision.reason == "buy notional exceeds configured limit"


def test_risk_gate_kill_switch_blocks_after_daily_loss_limit():
    config = _config(max_daily_loss=Decimal("5"))
    _, _, opportunity = _opportunity(config)
    risk_manager = OpportunityRiskManager(config)
    risk_manager.record_realized_pnl(Decimal("-5"))

    decision = risk_manager.validate(opportunity)

    assert not decision.approved
    assert decision.reason == "daily loss kill switch is engaged"


def test_environment_caps_risk_and_live_opt_in_fails_closed(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("ARBITRAGE_MAX_EXPOSURE_INR", "300")
    monkeypatch.setenv("ARBITRAGE_MAX_DAILY_LOSS_INR", "60")
    monkeypatch.setenv("ARBITRAGE_MAX_FALLBACK_LOSS_INR", "30")
    get_settings.cache_clear()
    try:
        app = ArbitrageApplication(
            _config(
                knowledge_base=tmp_path,
                max_order_notional=Decimal("1000"),
                max_daily_loss=Decimal("500"),
                max_fallback_loss=Decimal("100"),
            )
        )

        assert app.config.max_order_notional == Decimal("300")
        assert app.config.max_daily_loss == Decimal("60")
        assert app.config.max_fallback_loss == Decimal("30")
        with pytest.raises(RuntimeError, match="LIVE_TRADING_ACKNOWLEDGEMENT"):
            app.run()
    finally:
        get_settings.cache_clear()


def test_paper_executor_falls_back_to_buy_exchange_to_close_position():
    now, _, opportunity = _opportunity()
    quotes = {
        "NSE": _quote("NSE", now, bid="97"),
        "BSE": _quote("BSE", now - timedelta(seconds=10), bid="103", ask="104"),
    }

    report = PaperExecutor(_config(), CostCalculator()).execute(opportunity, quotes, now)

    assert report.fallback_used
    assert report.actual_sell_exchange == "NSE"
    assert report.open_quantity == 0
    assert report.net_profit < 0


def test_paper_executor_records_unhedged_quantity_when_both_sells_unavailable():
    now, _, opportunity = _opportunity()
    quotes = {
        "NSE": _quote("NSE", now, bid_quantity=0),
        "BSE": _quote("BSE", now - timedelta(seconds=10), bid_quantity=0),
    }

    report = PaperExecutor(_config(), CostCalculator()).execute(opportunity, quotes, now)

    assert report.status == "UNHEDGED"
    assert report.open_quantity == opportunity.quantity


def test_paper_executor_respects_fallback_loss_cap():
    now, _, opportunity = _opportunity()
    quotes = {
        "NSE": _quote("NSE", now, bid="60"),
        "BSE": _quote("BSE", now - timedelta(seconds=10), bid="103", ask="104"),
    }

    report = PaperExecutor(_config(max_fallback_loss=Decimal("30")), CostCalculator()).execute(
        opportunity, quotes, now
    )

    assert report.status == "UNHEDGED"
    assert report.open_quantity == opportunity.quantity
    assert report.actual_sell_exchange is None


def test_csv_journal_records_raw_quotes_opportunities_and_paper_execution(tmp_path: Path):
    now, engine, opportunity = _opportunity()
    quotes = engine.latest_quotes["TEST"]
    decision = OpportunityRiskManager(_config()).validate(opportunity)
    execution = PaperExecutor(_config(), CostCalculator()).execute(opportunity, quotes, now)
    journal = CsvJournal(tmp_path / "knowledge_base")

    journal.record_quote(quotes["NSE"])
    journal.record_opportunity(opportunity, decision)
    journal.record_execution(execution)

    with (tmp_path / "knowledge_base" / "market_quotes.csv").open(encoding="utf-8") as source:
        assert next(csv.DictReader(source))["exchange"] == "NSE"
    with (tmp_path / "knowledge_base" / "opportunities.csv").open(encoding="utf-8") as source:
        opportunity_row = next(csv.DictReader(source))
    assert opportunity_row["risk_approved"] == "True"
    with (tmp_path / "knowledge_base" / "paper_executions.csv").open(encoding="utf-8") as source:
        execution_row = next(csv.DictReader(source))
    assert execution_row["opportunity_id"] == opportunity.opportunity_id


def test_angel_one_feed_parses_depth_and_publishes_market_quote():
    received: list[MarketQuote] = []
    errors: list[Exception] = []
    feed = AngelOneArbitrageFeed(
        "api-key",
        "client-id",
        "password",
        "totp",
        {("NSE", "1"): ("TEST", "NSE")},
        received.append,
        errors.append,
    )
    timestamp = datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc)

    feed._handle_message(
        None,
        {
            "exchange_type": 1,
            "token": "1",
            "exchange_timestamp": int(timestamp.timestamp() * 1000),
            "best_5_buy_data": [{"price": 10100, "quantity": 5}],
            "best_5_sell_data": [{"price": 10200, "quantity": 4}],
        },
    )

    assert errors == []
    assert received[0].bid == Decimal("101")
    assert received[0].ask == Decimal("102")
    assert received[0].exchange == "NSE"


def test_angel_one_feed_reconnects_and_stops_cleanly():
    connected = threading.Event()
    attempts = 0
    broker_disconnected = threading.Event()

    class FakeClient:
        access_token = "jwt-token"

        @staticmethod
        def getfeedToken() -> str:
            return "feed-token"

    class FakeBroker:
        _client = FakeClient()

        def __init__(self, *_credentials: str) -> None:
            pass

        @staticmethod
        def connect() -> None:
            return None

        @staticmethod
        def disconnect() -> None:
            broker_disconnected.set()

    class FakeWebSocket:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self.closed = threading.Event()

        def connect(self) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ConnectionError("simulated disconnect")
            connected.set()
            self.closed.wait(timeout=3)

        def close_connection(self) -> None:
            self.closed.set()

    errors: list[Exception] = []
    feed = AngelOneArbitrageFeed(
        "api-key",
        "client-id",
        "password",
        "totp",
        {},
        lambda _quote: None,
        errors.append,
        reconnect_initial_delay=0.01,
        reconnect_max_delay=0.02,
        broker_factory=FakeBroker,
        websocket_factory=FakeWebSocket,
    )

    feed.start()
    assert connected.wait(timeout=2)
    feed.stop()

    assert attempts >= 2
    assert errors == []
    assert broker_disconnected.is_set()
