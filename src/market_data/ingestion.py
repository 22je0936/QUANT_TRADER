"""Consumes ticks from an IMarketDataFeed, normalizes them, caches LTP in Redis,
and persists them to ClickHouse in batches.
"""
from __future__ import annotations

from src.core.entities import Tick
from src.core.interfaces import IMarketDataFeed
from src.infra.clickhouse_client import get_clickhouse_client
from src.infra.logging import get_logger
from src.infra.redis_client import get_redis_client

logger = get_logger(__name__)

_TICKS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS ticks (
    instrument_id String,
    ltp Decimal(18, 4),
    volume UInt64,
    bid Nullable(Decimal(18, 4)),
    ask Nullable(Decimal(18, 4)),
    timestamp DateTime64(3)
) ENGINE = MergeTree()
ORDER BY (instrument_id, timestamp)
"""


class MarketDataIngestionService:
    def __init__(self, feed: IMarketDataFeed, batch_size: int = 500) -> None:
        self._feed = feed
        self._batch_size = batch_size
        self._buffer: list[Tick] = []
        self._redis = get_redis_client()
        self._clickhouse = get_clickhouse_client()
        self._clickhouse.command(_TICKS_TABLE_DDL)
        self._feed.on_tick(self._handle_tick)

    def start(self, instrument_ids: list[str]) -> None:
        self._feed.connect()
        self._feed.subscribe(instrument_ids)

    def stop(self) -> None:
        self.flush()
        self._feed.disconnect()

    def _handle_tick(self, tick: Tick) -> None:
        self._redis.hset(
            f"ltp:{tick.instrument_id}",
            mapping={"price": str(tick.ltp), "timestamp": tick.timestamp.isoformat()},
        )
        self._buffer.append(tick)
        if len(self._buffer) >= self._batch_size:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        rows = [
            [t.instrument_id, t.ltp, t.volume, t.bid, t.ask, t.timestamp] for t in self._buffer
        ]
        self._clickhouse.insert(
            "ticks", rows, column_names=["instrument_id", "ltp", "volume", "bid", "ask", "timestamp"]
        )
        logger.info("ticks_flushed", count=len(rows))
        self._buffer.clear()
