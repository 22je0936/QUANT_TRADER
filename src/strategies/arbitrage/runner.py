"""Application wiring for the paper-only arbitrage workflow."""

from __future__ import annotations

import signal
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from queue import Empty, Queue
from threading import Event
from typing import NoReturn
from zoneinfo import ZoneInfo

from src.brokers.angel_one.angel_one_broker import AngelOneBrokerAdapter
from src.brokers.angel_one.arbitrage_feed import AngelOneArbitrageFeed
from src.config.settings import get_settings
from src.infra.logging import configure_logging, get_logger
from src.risk.risk_manager import RiskLimits, RiskManager, RiskState

from .config import ArbitrageConfig
from .costs import CostCalculator
from .engine import ArbitrageEngine
from .instruments import load_instruments
from .live_execution import LiveArbitrageExecutor
from .models import MarketQuote
from .risk import OpportunityRiskManager
from .storage import CsvJournal

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class FeedFailure:
    error: Exception


class ArbitrageApplication:
    """Queue quotes from the feed; detect opportunities and execute live orders."""

    def __init__(self, config: ArbitrageConfig | None = None) -> None:
        settings = get_settings()
        base_config = config or ArbitrageConfig()
        self.config = replace(
            base_config,
            max_order_notional=min(
                base_config.max_order_notional, settings.arbitrage_max_exposure_inr
            ),
            max_daily_loss=min(base_config.max_daily_loss, settings.arbitrage_max_daily_loss_inr),
            max_fallback_loss=min(
                base_config.max_fallback_loss, settings.arbitrage_max_fallback_loss_inr
            ),
        )
        self._settings = settings
        self._events: Queue[MarketQuote | FeedFailure] = Queue()
        self._stop_event = Event()
        self._journal = CsvJournal(self.config.knowledge_base)
        self._costs = CostCalculator(self.config.costs)
        self._engine = ArbitrageEngine(self.config, self._costs)
        self._risk = OpportunityRiskManager(self.config)
        self._live_executor: LiveArbitrageExecutor | None = None
        self._catalog = None

    def run(self) -> None:
        configure_logging()
        if not self._settings.live_trading_enabled:
            raise RuntimeError(
                "The arbitrage watcher is live-only. Set LIVE_TRADING_ENABLED=true "
                "after reviewing the live-risk documentation."
            )
        acknowledgement = "I_ACCEPT_LIVE_TRADING_RISK"
        if self._settings.live_trading_acknowledgement != acknowledgement:
            raise RuntimeError(
                "Live trading is fail-closed. Set LIVE_TRADING_ACKNOWLEDGEMENT="
                f"{acknowledgement} only after reviewing the live-risk documentation."
            )

        catalog = load_instruments(self.config.scrip_file, self.config.symbols)
        for symbol in catalog.missing_names:
            logger.warning(
                "arbitrage_symbol_skipped", symbol=symbol, reason="missing exchange listing"
            )
        if not catalog.by_name:
            raise RuntimeError("No configured symbol has both an NSE and BSE listing")
        self._catalog = catalog

        self._journal.ensure_live_state_reconciled()
        market_date = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        daily_pnl = self._journal.get_live_daily_pnl(market_date)
        risk_state = RiskState(realized_pnl_today=daily_pnl)
        if daily_pnl <= -self.config.max_daily_loss:
            risk_state.kill_switch_engaged = True
        live_risk_manager = RiskManager(
            RiskLimits(
                max_daily_loss=self.config.max_daily_loss,
                max_position_size=self.config.max_order_notional,
                max_order_quantity=self.config.max_order_quantity,
                max_exposure_per_symbol=self.config.max_order_notional,
            ),
            state=risk_state,
        )
        if live_risk_manager.state.kill_switch_engaged:
            raise RuntimeError("Persisted live daily loss has reached the configured limit")
        live_broker: AngelOneBrokerAdapter = AngelOneBrokerAdapter(
            self._settings.angel_one_api_key,
            self._settings.angel_one_client_id,
            self._settings.angel_one_password,
            self._settings.angel_one_totp_secret,
        )
        try:
            live_broker.connect()
            open_orders = live_broker.get_open_orders()
            if open_orders:
                raise RuntimeError(
                    "Live arbitrage requires no pre-existing open Angel One orders; "
                    "reconcile the broker order book first"
                )
            active_positions = [
                position
                for position in live_broker.get_positions()
                if position.quantity != 0
            ]
            if active_positions:
                raise RuntimeError(
                    "Live arbitrage requires a flat Angel One account; "
                    "close/reconcile existing positions first"
                )
            self._live_executor = LiveArbitrageExecutor(
                live_broker,
                live_risk_manager,
                self.config,
                self._costs,
                self._journal,
                lambda symbol: self._engine.latest_quotes.get(symbol, {}),
            )
        except Exception:
            try:
                live_broker.disconnect()
            except Exception:
                logger.exception("live_preflight_disconnect_failed")
            raise

        feed = AngelOneArbitrageFeed(
            self._settings.angel_one_api_key,
            self._settings.angel_one_client_id,
            self._settings.angel_one_password,
            self._settings.angel_one_totp_secret,
            catalog.by_token,
            self._receive_quote,
            self._receive_feed_failure,
            self.config.reconnect_initial_delay,
            self.config.reconnect_max_delay,
            broker=live_broker,
        )
        previous_handlers = self._install_shutdown_handlers()
        logger.info(
            "arbitrage_engine_starting",
            symbols=len(catalog.by_name),
            knowledge_base=str(self.config.knowledge_base),
            mode="live",
            real_orders_enabled=True,
        )
        for symbol, instruments in catalog.by_name.items():
            exchanges = ", ".join(
                f"{exchange} ({instrument.symbol})"
                for exchange, instrument in instruments.items()
            )
            logger.info(
                "arbitrage_monitoring_symbol",
                symbol=symbol,
                exchanges=exchanges,
                status="watching for arbitrage",
            )
        try:
            feed.start()
            while not self._stop_event.is_set():
                try:
                    event = self._events.get(timeout=0.25)
                except Empty:
                    continue
                if isinstance(event, FeedFailure):
                    raise RuntimeError("Market-data feed failed") from event.error
                self._process_quote(event)
        finally:
            self._stop_event.set()
            try:
                feed.stop()
            finally:
                try:
                    if live_broker is not None:
                        live_broker.disconnect()
                finally:
                    self._restore_shutdown_handlers(previous_handlers)
                    logger.info("arbitrage_engine_stopped")

    def _receive_quote(self, quote: MarketQuote) -> None:
        """Persist a validated quote in the callback, then publish it to the queue."""
        try:
            self._journal.record_quote(quote)
            self._events.put_nowait(quote)
        except Exception as exc:
            logger.exception("arbitrage_quote_ingress_failed", symbol=quote.symbol)
            self._events.put_nowait(FeedFailure(exc))

    def _receive_feed_failure(self, error: Exception) -> None:
        self._events.put_nowait(FeedFailure(error))

    def _process_quote(self, quote: MarketQuote) -> None:
        opportunity = self._engine.update_quote(quote)
        if opportunity is None:
            return

        decision = self._risk.validate(opportunity)
        self._journal.record_opportunity(opportunity, decision)
        logger.info(
            "arbitrage_opportunity_detected",
            opportunity_id=opportunity.opportunity_id,
            symbol=opportunity.symbol,
            buy_exchange=opportunity.buy_exchange,
            sell_exchange=opportunity.sell_exchange,
            estimated_net_profit=str(opportunity.estimated_net_profit),
            risk_approved=decision.approved,
        )
        if not decision.approved:
            return

        if self._live_executor is None or self._catalog is None:
            raise RuntimeError("Live execution was enabled without initialized broker components")
        instruments = self._catalog.by_name[opportunity.symbol]
        report = self._live_executor.execute(
            opportunity,
            instruments[opportunity.buy_exchange],
            instruments[opportunity.sell_exchange],
        )
        if report.open_quantity or report.status == "MANUAL_RECONCILIATION":
            self._stop_event.set()
            raise RuntimeError(
                f"Live execution needs manual reconciliation: {report.opportunity_id}"
            )
        logger.info(
            "live_arbitrage_execution_recorded",
            opportunity_id=report.opportunity_id,
            status=report.status,
            estimated_net_pnl=str(report.estimated_net_pnl),
        )

    def _install_shutdown_handlers(self) -> dict[int, object]:
        previous: dict[int, object] = {}

        def request_shutdown(_signum: int, _frame: object) -> None:
            logger.info("arbitrage_shutdown_requested")
            self._stop_event.set()

        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, request_shutdown)
        return previous

    @staticmethod
    def _restore_shutdown_handlers(previous: dict[int, object]) -> None:
        for signum, handler in previous.items():
            signal.signal(signum, handler)  # type: ignore[arg-type]


def main() -> NoReturn:
    ArbitrageApplication().run()
    raise SystemExit(0)
