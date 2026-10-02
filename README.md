# Quant Trader Engine

A production-grade, broker-agnostic quantitative trading engine for Indian
markets, built with clean architecture principles. Starts on **Angel One
SmartAPI** and is designed to migrate to **Zerodha Kite** (or any future
broker) without touching strategy, risk, or analytics code.

## Why this design

Trading strategies, indicators, risk rules, and backtests are the valuable,
long-lived IP. Broker APIs change, get deprecated, or you outgrow them. This
engine isolates broker-specific code behind interfaces (`IBrokerGateway`,
`IMarketDataFeed`) so that a broker migration is a new adapter, not a rewrite.

See [workflow.md](workflow.md) for the phased build plan and architecture
diagrams, and [requirements.md](requirements.md) for the full functional and
non-functional requirements.

## Core Principles

- **Clean Architecture / Hexagonal**: core domain has zero dependency on
  brokers, databases, or frameworks.
- **SOLID + Repository Pattern**: persistence and broker access are always
  behind interfaces; services depend on abstractions, not implementations.
- **Dependency Injection**: every service receives its dependencies via
  constructor — no hidden global state.
- **Paper-first**: every strategy runs through a `PaperBrokerAdapter` before
  it ever touches live capital, using the exact same code path.

## Tech Stack

- **API**: FastAPI
- **Tick storage**: ClickHouse
- **Relational storage**: PostgreSQL (users, trades, strategies, backtests)
- **Cache**: Redis
- **Brokers**: Angel One SmartAPI (now), Zerodha Kite Connect (future)
- **Future**: Kafka (event bus), ML-based signal generation

## Project Structure

```
quant_trader/
├── src/
│   ├── core/            # entities, interfaces, DTOs — broker/db agnostic
│   ├── brokers/          # angel_one/, kite/, paper/ adapters
│   ├── market_data/       # ingestion, normalization, candles
│   ├── indicators/         # pure technical indicator functions
│   ├── order_flow/
│   ├── options_analytics/
│   ├── risk/
│   ├── signals/            # strategies (ISignalGenerator impls)
│   ├── backtesting/
│   ├── services/            # orchestration (StrategyRunner, etc.)
│   ├── repositories/         # Postgres/ClickHouse/Redis implementations
│   ├── api/                   # FastAPI routers & schemas
│   ├── infra/                  # DB/Redis/DI wiring
│   └── config/
├── tests/
│   ├── unit/
│   ├── contract/                # run against every broker adapter
│   └── integration/
├── migrations/
├── scripts/
├── docker/
├── requirements.md
├── workflow.md
└── README.md
```

Full rationale for this layout is in [workflow.md](workflow.md#recommended-folder-structure).

## Getting Started

> Prerequisites: Python 3.11+, Docker, Docker Compose

```powershell
# 1. Enter the project
cd QUANT_TRADER

# 2. Create a virtual environment and install dependencies
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. Copy env template and fill in broker/db credentials
Copy-Item .env.example .env

# 4. Start infra (PostgreSQL, ClickHouse, Redis)
docker compose -f docker/docker-compose.yml up -d

# 5. Run DB migrations
alembic upgrade head

# 6. Run tests
pytest

# 7. Start the API (defaults to BROKER_PROVIDER=paper — safe, no live orders)
uvicorn src.api.main:app --reload
```

The API is now live at `http://127.0.0.1:8000/docs`. Try `GET /health`,
`POST /orders` (fills instantly against the paper broker), and `GET /positions`.

## Broker Configuration

Set the active broker via environment variable — no code changes needed:

```
BROKER_PROVIDER=paper       # paper | angel_one | kite
ANGEL_ONE_API_KEY=...
ANGEL_ONE_CLIENT_ID=...
KITE_API_KEY=...
KITE_API_SECRET=...
```

Always start with `BROKER_PROVIDER=paper` for any new strategy.

## Testing Strategy

- `tests/unit` — indicators, risk rules, signal logic (no I/O, fast).
- `tests/contract` — same suite run against `AngelOneBrokerAdapter`,
  `KiteBrokerAdapter`, and `PaperBrokerAdapter` to guarantee interchangeability.
- `tests/integration` — ingestion → ClickHouse → indicators, using
  docker-compose/testcontainers.

Run everything: `pytest`. Run a layer: `pytest tests/unit`.

## Arbitrage Engine: Paper Default, Gated Live Mode

The arbitrage watcher reads live NSE/BSE bid/ask depth, estimates transaction
costs, applies quote freshness and risk checks, and records CSV ledgers. Paper
mode is the default. A live limit-order path exists behind two environment
gates but has only been tested with fake broker responses; it is not certified
for live-market use. Angel One transport/order details are isolated under
`src/brokers/angel_one/`; the engine, cost calculator, risk gate, paper/live
execution orchestration, and CSV journal are under `strategy/arbitrage/`.

### Setup and Run

Use Python 3.11 or newer. Install the project and Angel One extra, then copy
`.env.example` to `.env` and fill in the four `ANGEL_ONE_*` values. Do not
commit `.env` or share its contents.

The arbitrage environment defaults are `LIVE_TRADING_ENABLED=false`,
`LIVE_TRADING_ACKNOWLEDGEMENT=` (blank),
`ARBITRAGE_MAX_EXPOSURE_INR=300`, `ARBITRAGE_MAX_DAILY_LOSS_INR=60`, and
`ARBITRAGE_MAX_FALLBACK_LOSS_INR=30`. These are software guardrails for the
paper/live workflow, not a promise of safe or profitable trading. Live mode
requires `LIVE_TRADING_ENABLED=true` plus the exact acknowledgement
`LIVE_TRADING_ACKNOWLEDGEMENT=I_ACCEPT_LIVE_TRADING_RISK`. The live order path
uses limit orders, polls/cancels through the Angel One order book, and blocks
startup when prior live CSV records indicate unresolved orders/positions. It
has not been verified against real Angel One responses or in a sandbox; do not
assume it is ready for real-market trading.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[angel-one,dev]'
cp -n .env.example .env
python strategy/arbitrage_watcher.py
```

Edit the watchlist and quote/risk limits in
`strategy/arbitrage/config.py`. Transaction charge assumptions are injectable
through `CostConfig` in `strategy/arbitrage/costs.py`; these estimates are not
an exchange or broker fee guarantee.

### Captured CSV Data

The application creates `knowledge_base/` on startup and appends:

- `market_quotes.csv`: timestamped NSE/BSE bid, ask, quantities, and raw feed
  payload for every validated quote.
- `opportunities.csv`: every detected opportunity, estimated charge breakdown,
  net profit, and risk approval or rejection reason.
- `paper_executions.csv`: simulated buy/sell prices, actual simulated exit
  exchange, estimated costs, net P&L, fallback use, and any remaining open size.

If the intended cross-exchange sell quote is stale or lacks enough displayed
quantity, paper execution tries to close on the buy exchange at its current
best bid. If that quote cannot close the position, the journal marks it
`UNHEDGED` and logs an error instead of claiming a completed exit. This is a
simulation rule, not a live order-management guarantee.

Open the CSV files in a spreadsheet, or load them with pandas for analysis.
The feed callback only parses, validates, journals, and queues quotes; spread
calculations and risk/execution simulation run in the application loop.

## Migration Path: Angel One → Kite

1. Implement `KiteBrokerAdapter` against the existing `IBrokerGateway` /
   `IMarketDataFeed` interfaces.
2. Run the shared contract test suite against it — must pass unmodified.
3. Add symbol/token mapping (Angel One ↔ Kite ↔ canonical instrument ID).
4. Flip `BROKER_PROVIDER=kite` in config. No strategy/service/risk code
   changes required.

Details in [workflow.md](workflow.md#phase-9--migrateadd-zerodha-kite-day-31-34).

## Contributing / Conventions

- No strategy, indicator, or risk module may import from `src/brokers/*`.
- All new broker adapters must implement and pass `tests/contract`.
- All orders must flow through the risk service — no direct broker calls
  from strategies.
- Lint/type-check must pass (`ruff`, `mypy`) before merge.

## Implementation Status

| Component | Status |
|---|---|
| Core entities, interfaces, exceptions | Implemented |
| `PaperBrokerAdapter` / `PaperMarketDataFeed` | Implemented, unit + contract tested |
| `AngelOneBrokerAdapter` / `AngelOneMarketDataFeed` | Implemented against SmartAPI; needs live credentials to test `connect()`/order flow; `modify_order`/`cancel_order`/`get_order_status` are stubbed (`NotImplementedError`) pending SmartAPI order-book lookup wiring |
| `KiteBrokerAdapter` / `KiteMarketDataFeed` | Implemented against Kite Connect; same stubbed methods as Angel One, ready for Phase 9 migration |
| Indicators (SMA/EMA/RSI/MACD/ATR/VWAP/Bollinger) | Implemented, unit tested |
| Order flow analytics | Implemented |
| Options analytics (Greeks, IV, PCR) | Implemented, unit tested |
| Risk manager (limits, kill-switch) | Implemented, unit tested |
| `StrategyRunner` + `EmaCrossoverStrategy` | Implemented |
| Backtesting engine | Implemented (reuses `StrategyRunner` + `PaperBrokerAdapter`) |
| Market data ingestion (ClickHouse + Redis) | Implemented |
| PostgreSQL models + repositories + Alembic migration | Implemented |
| FastAPI app (`/health`, `/orders`, `/positions`) | Implemented |
| Auth (JWT), rate limiting, secrets encryption | Not yet implemented — required before any live-money deployment |
| Kafka event bus, ML signal generator | Deferred — see [workflow.md](workflow.md#phase-10--future-scaling) |

## License

Internal / proprietary (update as applicable).
