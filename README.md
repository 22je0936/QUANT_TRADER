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
