"""Example strategy: EMA crossover. Depends only on indicators + a market data
provider function — never on any broker adapter. Implements ISignalGenerator.
"""
from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from src.core.entities import Signal, SignalAction
from src.indicators.technical import ema


class EmaCrossoverStrategy:
    """Buys when fast EMA crosses above slow EMA, sells on the reverse cross."""

    def __init__(
        self,
        strategy_id: str,
        get_candles: Callable[[str], pd.DataFrame],
        fast_period: int = 9,
        slow_period: int = 21,
    ) -> None:
        self.strategy_id = strategy_id
        self._get_candles = get_candles
        self._fast_period = fast_period
        self._slow_period = slow_period

    def generate(self, instrument_id: str) -> Signal | None:
        candles = self._get_candles(instrument_id)
        if len(candles) < self._slow_period + 1:
            return None

        fast = ema(candles["close"], self._fast_period)
        slow = ema(candles["close"], self._slow_period)

        prev_diff = fast.iloc[-2] - slow.iloc[-2]
        curr_diff = fast.iloc[-1] - slow.iloc[-1]

        if prev_diff <= 0 < curr_diff:
            return Signal(instrument_id=instrument_id, action=SignalAction.BUY, strategy_id=self.strategy_id)
        if prev_diff >= 0 > curr_diff:
            return Signal(instrument_id=instrument_id, action=SignalAction.SELL, strategy_id=self.strategy_id)
        return None
