"""Configurable estimate of common Indian equity transaction charges."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import CostBreakdown, ExchangeName


@dataclass(frozen=True, slots=True)
class CostConfig:
    brokerage_rate: Decimal = Decimal("0.0003")
    brokerage_cap_per_order: Decimal = Decimal("20")
    transaction_charge_rate: Decimal = Decimal("0.0000345")
    stt_sell_rate: Decimal = Decimal("0.00025")
    stamp_duty_buy_rate: Decimal = Decimal("0.00003")
    sebi_charge_rate: Decimal = Decimal("0.000001")
    gst_rate: Decimal = Decimal("0.18")


class CostCalculator:
    """Estimate round-trip charges; inject CostConfig for broker-specific rates."""

    def __init__(self, config: CostConfig | None = None) -> None:
        self.config = config or CostConfig()

    def calculate(
        self,
        buy_price: Decimal,
        sell_price: Decimal,
        quantity: int,
        buy_exchange: ExchangeName,
        sell_exchange: ExchangeName,
    ) -> CostBreakdown:
        del buy_exchange, sell_exchange  # Retained in the API for exchange-specific schedules.
        buy_turnover = buy_price * quantity
        sell_turnover = sell_price * quantity
        total_turnover = buy_turnover + sell_turnover
        brokerage = min(
            buy_turnover * self.config.brokerage_rate,
            self.config.brokerage_cap_per_order,
        ) + min(
            sell_turnover * self.config.brokerage_rate,
            self.config.brokerage_cap_per_order,
        )
        transaction_charges = total_turnover * self.config.transaction_charge_rate
        stt = sell_turnover * self.config.stt_sell_rate
        stamp_duty = buy_turnover * self.config.stamp_duty_buy_rate
        sebi_charges = total_turnover * self.config.sebi_charge_rate
        gst = (brokerage + transaction_charges) * self.config.gst_rate
        return CostBreakdown(
            brokerage=brokerage,
            transaction_charges=transaction_charges,
            stt=stt,
            stamp_duty=stamp_duty,
            sebi_charges=sebi_charges,
            gst=gst,
        )