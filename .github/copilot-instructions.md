# Copilot Instructions — Quant Trader Engine

This file gives AI coding agents the essential context to work productively in
this repository. Read this before making changes.

## What this project is

A broker-agnostic, production-grade quantitative trading engine for Indian
markets (NSE/BSE). Starts on **Angel One SmartAPI**, designed to migrate to
**Zerodha Kite Connect** later without touching strategy/risk/analytics code.
Origin spec: [prompt.md](../prompt.md). Full requirements:
[requirements.md](../requirements.md). Phased build plan + architecture
diagrams: [workflow.md](../workflow.md). Project overview: [README.md](../README.md).

## Architecture (read this before editing anything)

Clean/Hexagonal architecture — **strict dependency direction inward**:

```
strategies/signals, risk, indicators, backtesting  (core — zero broker/DB deps)
            ↓ depend only on interfaces in src/core/interfaces.py
brokers/*, repositories/postgres/*, infra/*        (adapters — implement interfaces)
```

**Hard rule:** code in `src/signals/`, `src/risk/`, `src/indicators/`,
`src/order_flow/`, `src/options_analytics/`, `src/backtesting/` must NEVER
import from `src/brokers/*`. They depend only on `src/core/interfaces.py`
(`IBrokerGateway`, `IMarketDataFeed`, `ISignalGenerator`, repository
interfaces). This is what makes Angel One ↔ Kite ↔ Paper interchangeable.

Every new broker adapter must implement `IBrokerGateway` + `IMarketDataFeed`
and pass the shared suite in `tests/contract/test_broker_contract.py`
unmodified — that's the proof of interchangeability.

## Tech stack

FastAPI · PostgreSQL (SQLAlchemy + Alembic) · ClickHouse (tick storage) ·
Redis (LTP cache) · pandas/numpy/scipy (indicators, options Greeks) ·
structlog (JSON logging) · pytest.

## Current implementation status (as of 2026-09-17)

Full end-to-end skeleton exists and is runnable. See the status table in
[README.md](../README.md#implementation-status) for the authoritative,
up-to-date list. Summary:

- **Done:** core entities/interfaces/exceptions, `PaperBrokerAdapter` (fully
  working, unit + contract tested), `AngelOneBrokerAdapter`/`KiteBrokerAdapter`
  (implemented against real SDKs, `place_order`/`get_positions`/`get_margins`
  wired; `modify_order`/`cancel_order`/`get_order_status` are
  `NotImplementedError` stubs pending broker order-book lookup), indicators
  (SMA/EMA/RSI/MACD/ATR/VWAP/Bollinger), order flow analytics, options
  analytics (Black-Scholes Greeks/IV/PCR), `RiskManager` (limits +
  kill-switch), `EmaCrossoverStrategy` + `StrategyRunner`, `Backtester`
  (reuses `StrategyRunner` + `PaperBrokerAdapter`), `MarketDataIngestionService`
  (ClickHouse + Redis), Postgres SQLAlchemy models + repositories + Alembic
  migration `0001_initial`, FastAPI app with `/health`, `/orders`,
  `/positions`.
- **Not yet done:** JWT auth, rate limiting, credential encryption at rest,
  Kafka event bus, ML signal generator. These are explicitly deferred (see
  [workflow.md](../workflow.md#phase-10--future-scaling) Phase 10 and the
  README status table) — do not assume they exist.

## Infrastructure setup

Databases are Docker services, not embedded files — Postgres/ClickHouse/Redis
all run as containers. Config: [docker/docker-compose.yml](../docker/docker-compose.yml).

To bring the stack up:
```powershell
docker compose -f docker/docker-compose.yml up -d   # creates empty Postgres DB + ClickHouse + Redis
alembic upgrade head                                 # creates Postgres tables (migrations/versions/0001_initial.py)
```
ClickHouse's `ticks` table is created lazily at runtime by
`MarketDataIngestionService.__init__` (see [src/market_data/ingestion.py](../src/market_data/ingestion.py)), not via a migration tool.

Known environment note: on this machine, Docker Desktop's engine is not
always running when the CLI is invoked — `docker compose up` can fail with
`failed to connect to the docker API at npipe:...dockerDesktopLinuxEngine`.
If that happens, launch Docker Desktop first and wait ~30-90s before retrying
`docker compose`.

## Conventions to follow when adding code

- Broker selection is config-driven: `BROKER_PROVIDER=paper|angel_one|kite`
  in `.env`, read via `src/config/settings.py`. The ONLY place allowed to
  branch on this value is `src/brokers/factory.py`.
- All order placement must go through `RiskManager.validate_order()` before
  reaching `IBrokerGateway.place_order()` — no bypass path, ever (see
  `src/services/strategy_runner.py` and `src/api/routers/orders.py` for the
  pattern).
- New indicators/analytics functions must be pure (pandas/numpy in, pandas/
  numpy out) — no I/O, no broker/DB imports — so they stay unit-testable
  with fixture data alone.
- New broker adapters go in `src/brokers/<name>/`, get wired into
  `src/brokers/factory.py`, and must pass `tests/contract/test_broker_contract.py`.
- Tests: `tests/unit/` (pure logic, no I/O), `tests/contract/` (every broker
  adapter, same suite), `tests/integration/` (reserved for ingestion →
  ClickHouse → indicators pipeline, not yet populated).
- Root [conftest.py](../conftest.py) inserts the project root onto `sys.path` so
  `from src...` imports resolve when running `pytest` from anywhere.
- Package layout is `where=["."], include=["src*"]` in `pyproject.toml` —
  `src` itself is a package (has `__init__.py`), so imports are always
  `from src.core...`, not `from core...`.

## What NOT to do

- Do not add Kafka, ML signal generation, or auth/rate-limiting unless
  explicitly asked — they're intentionally deferred (see status table).
- Do not let strategies/signals/risk/indicators import broker or DB code.
- Do not bypass `RiskManager` for order placement, even in new endpoints or
  scripts.
- Do not create markdown docs to describe changes unless the user asks for
  them explicitly.
