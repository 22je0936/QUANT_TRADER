"""Thread-safe CSV journal for raw quotes, opportunities, and paper executions."""

from __future__ import annotations

import csv
import json
from dataclasses import fields
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo

from src.infra.logging import get_logger

from .models import (
    ArbitrageOpportunity,
    LiveExecutionReport,
    LiveOrderEvent,
    MarketQuote,
    PaperExecution,
    RiskDecision,
)

logger = get_logger(__name__)


class CsvJournal:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def record_quote(self, quote: MarketQuote) -> None:
        self._append(
            "market_quotes.csv",
            (
                "timestamp",
                "symbol",
                "exchange",
                "bid",
                "bid_quantity",
                "ask",
                "ask_quantity",
                "raw_payload",
            ),
            {
                "timestamp": quote.timestamp.isoformat(),
                "symbol": quote.symbol,
                "exchange": quote.exchange,
                "bid": str(quote.bid),
                "bid_quantity": quote.bid_quantity,
                "ask": str(quote.ask),
                "ask_quantity": quote.ask_quantity,
                "raw_payload": json.dumps(quote.raw_payload, default=str, separators=(",", ":")),
            },
        )

    def record_opportunity(
        self, opportunity: ArbitrageOpportunity, decision: RiskDecision
    ) -> None:
        row = {
            "opportunity_id": opportunity.opportunity_id,
            "detected_at": opportunity.detected_at.isoformat(),
            "symbol": opportunity.symbol,
            "buy_exchange": opportunity.buy_exchange,
            "sell_exchange": opportunity.sell_exchange,
            "buy_price": str(opportunity.buy_price),
            "sell_price": str(opportunity.sell_price),
            "quantity": opportunity.quantity,
            "gross_profit": str(opportunity.gross_profit),
            "brokerage": str(opportunity.costs.brokerage),
            "transaction_charges": str(opportunity.costs.transaction_charges),
            "stt": str(opportunity.costs.stt),
            "stamp_duty": str(opportunity.costs.stamp_duty),
            "sebi_charges": str(opportunity.costs.sebi_charges),
            "gst": str(opportunity.costs.gst),
            "estimated_costs": str(opportunity.costs.total),
            "estimated_net_profit": str(opportunity.estimated_net_profit),
            "risk_approved": decision.approved,
            "risk_reason": decision.reason,
        }
        self._append("opportunities.csv", tuple(row), row)

    def record_execution(self, execution: PaperExecution) -> None:
        row = {
            field.name: str(getattr(execution, field.name))
            if getattr(execution, field.name) is not None
            else ""
            for field in fields(execution)
        }
        for field_name in ("buy_price", "sell_price", "gross_profit", "costs", "net_profit"):
            value = getattr(execution, field_name)
            row[field_name] = "" if value is None else str(value)
        row["executed_at"] = execution.executed_at.isoformat()
        self._append("paper_executions.csv", tuple(row), row)

    def record_live_order_event(self, event: LiveOrderEvent) -> None:
        row = {
            "event_at": event.event_at.isoformat(),
            "opportunity_id": event.opportunity_id,
            "leg": event.leg,
            "client_order_id": event.client_order_id,
            "broker_order_id": event.broker_order_id or "",
            "exchange": event.exchange,
            "side": event.side,
            "status": event.status,
            "quantity": event.quantity,
            "filled_quantity": event.filled_quantity,
            "average_price": str(event.average_price) if event.average_price is not None else "",
            "detail": event.detail,
        }
        self._append("live_order_events.csv", tuple(row), row)

    def record_live_execution(self, report: LiveExecutionReport) -> None:
        row = {
            "opportunity_id": report.opportunity_id,
            "symbol": report.symbol,
            "status": report.status,
            "requested_quantity": report.requested_quantity,
            "bought_quantity": report.bought_quantity,
            "sold_quantity": report.sold_quantity,
            "open_quantity": report.open_quantity,
            "buy_exchange": report.buy_exchange,
            "intended_sell_exchange": report.intended_sell_exchange,
            "fallback_exchange": report.fallback_exchange or "",
            "average_buy_price": (
                str(report.average_buy_price) if report.average_buy_price is not None else ""
            ),
            "average_sell_price": (
                str(report.average_sell_price) if report.average_sell_price is not None else ""
            ),
            "estimated_costs": str(report.estimated_costs),
            "estimated_net_pnl": str(report.estimated_net_pnl),
            "started_at": report.started_at.isoformat(),
            "completed_at": report.completed_at.isoformat(),
            "detail": report.detail,
        }
        self._append("live_executions.csv", tuple(row), row)

    def ensure_live_state_reconciled(self) -> None:
        events_path = self.directory / "live_order_events.csv"
        executions_path = self.directory / "live_executions.csv"
        if not events_path.exists():
            return
        if not executions_path.exists():
            raise RuntimeError(
                "Live order events exist without execution reports; reconcile broker orders before restart"
            )

        with executions_path.open(newline="", encoding="utf-8") as source:
            reports = list(csv.DictReader(source))
        reported_ids = {row.get("opportunity_id", "") for row in reports}
        with events_path.open(newline="", encoding="utf-8") as source:
            event_opportunity_ids = {
                row.get("opportunity_id", "") for row in csv.DictReader(source)
            }
        unresolved_ids = event_opportunity_ids - reported_ids
        if unresolved_ids:
            raise RuntimeError(
                "Unreconciled live order events exist for opportunities: "
                + ", ".join(sorted(unresolved_ids))
            )

        open_reports = [
            row
            for row in reports
            if int(row.get("open_quantity") or 0) > 0
            or row.get("status") == "MANUAL_RECONCILIATION"
        ]
        if open_reports:
            ids = ", ".join(row.get("opportunity_id", "unknown") for row in open_reports)
            raise RuntimeError(
                f"Unclosed live positions exist for opportunities: {ids}; reconcile before restart"
            )

    def get_live_daily_pnl(self, trading_date: date) -> Decimal:
        path = self.directory / "live_executions.csv"
        if not path.exists():
            return Decimal("0")
        market_timezone = ZoneInfo("Asia/Kolkata")
        pnl = Decimal("0")
        with path.open(newline="", encoding="utf-8") as source:
            for row in csv.DictReader(source):
                timestamp = datetime.fromisoformat(row["completed_at"])
                if timestamp.astimezone(market_timezone).date() != trading_date:
                    continue
                pnl += Decimal(row.get("estimated_net_pnl") or "0")
        return pnl

    def _append(self, filename: str, columns: tuple[str, ...], row: dict[str, object]) -> None:
        path = self.directory / filename
        try:
            with self._lock, path.open("a", newline="", encoding="utf-8") as output:
                writer = csv.DictWriter(output, fieldnames=columns)
                if output.tell() == 0:
                    writer.writeheader()
                writer.writerow(row)
                output.flush()
        except OSError:
            logger.exception("arbitrage_csv_write_failed", path=str(path))
            raise