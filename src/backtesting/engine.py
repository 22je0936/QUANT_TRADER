"""Event-driven backtester that replays historical candles through the SAME
StrategyRunner + RiskManager + PaperBrokerAdapter used in live/paper trading —
no separate backtest-only strategy code path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

import pandas as pd

from src.brokers.paper.paper_broker import PaperBrokerAdapter
from src.core.entities import Order
from src.core.exceptions import RiskLimitBreachedError
from src.core.interfaces import ISignalGenerator
from src.risk.risk_manager import RiskManager
from src.services.strategy_runner import StrategyRunner


@dataclass(slots=True)
class BacktestResult:
    trades: list[Order] = field(default_factory=list)
    ending_cash: Decimal = Decimal("0")


class Backtester:
    def __init__(self, strategy: ISignalGenerator, risk_manager: RiskManager | None = None) -> None:
        self._broker = PaperBrokerAdapter()
        self._broker.connect()
        self._runner = StrategyRunner(strategy=strategy, broker=self._broker, risk_manager=risk_manager or RiskManager())

    def run(self, instrument_id: str, candles: pd.DataFrame) -> BacktestResult:
        """`candles` must be sorted ascending by time with a 'close' column."""
        result = BacktestResult()
        for i in range(len(candles)):
            window = candles.iloc[: i + 1]
            self._broker.set_last_price(instrument_id, Decimal(str(window["close"].iloc[-1])))
            try:
                order = self._runner.run_once(instrument_id)
            except RiskLimitBreachedError:
                continue
            if order is not None:
                result.trades.append(order)

        result.ending_cash = Decimal(str(self._broker.get_margins()["cash"]))
        return result
