# Arbitrage Watcher Architecture and Operations Guide

## 1. Overview

This project is currently shaped as a lean arbitrage-only system for NSE/BSE trading. It is intentionally not built around a heavy production database stack by default.

The active architecture is:

- live market feed from Angel One
- quote synchronization between NSE and BSE
- arbitrage detection and risk checks
- optional live order execution
- CSV-based knowledge base / audit trail
- terminal dashboard logging for humans

Default setup is intentionally minimal:

- Postgres: not active by default
- ClickHouse: not active by default
- Redis: optional only, kept for future use
- knowledge base: local CSV files in the `knowledge_base/` folder

---

## 2. Runtime flow

The core flow is:

1. `scripts/arbitrage_watcher.py`
   - entry point
   - loads the app
   - calls the arbitrage runner

2. `src/strategies/arbitrage/runner.py`
   - creates the app
   - loads symbols and instruments
   - validates live trading flags
   - starts the Angel One feed
   - receives quotes
   - calls the arbitrage engine
   - validates risk
   - executes trade legs if risk passes

3. `src/brokers/angel_one/arbitrage_feed.py`
   - receives raw market updates from broker websockets
   - normalizes quote snapshots
   - pushes them into the arbitrage engine

4. `src/strategies/arbitrage/engine.py`
   - compares quote freshness
   - detects profitable price gaps between exchanges
   - computes opportunity details

5. `src/strategies/arbitrage/risk.py`
   - checks whether an opportunity fits risk rules
   - decides if it is approved or blocked

6. `src/strategies/arbitrage/live_execution.py`
   - submits buy and sell actions
   - handles reconciliation and order tracking
   - measures live execution outcome

7. `src/strategies/arbitrage/storage.py`
   - writes CSV records for market quotes, opportunities, and execution events
   - helps keep a local operational journal

---

## 3. Active files and their responsibility

### Entry / execution

| File | Purpose | Main class / function |
| --- | --- | --- |
| `scripts/arbitrage_watcher.py` | main script that starts the arbitrage watch process | `main()` |
| `src/strategies/arbitrage/runner.py` | orchestrates app startup, feed, risk, execution, shutdown | `ArbitrageApplication`, `main()` |

### Configuration

| File | Purpose | Main class / function |
| --- | --- | --- |
| `src/config/settings.py` | runtime environment and app settings | `Settings`, `get_settings()` |
| `src/strategies/arbitrage/config.py` | arbitrage-specific guardrails and symbol list | `ArbitrageConfig` |
| `src/strategies/arbitrage/costs.py` | fee / cost model | `CostConfig`, `CostCalculator` |

### Broker / market data

| File | Purpose | Main class / function |
| --- | --- | --- |
| `src/brokers/angel_one/angel_one_broker.py` | live broker gateway using Angel One | `AngelOneBrokerAdapter`, `configure_requests_ssl()`, `should_disable_ssl_verification()` |
| `src/brokers/angel_one/arbitrage_feed.py` | websocket-driven quote stream for arbitrage | `AngelOneArbitrageFeed` |
| `src/brokers/factory.py` | broker object creation | `build_broker_gateway()`, `build_market_data_feed()` |

### Core logic

| File | Purpose | Main class / function |
| --- | --- | --- |
| `src/strategies/arbitrage/engine.py` | detects arbitrage opportunities | `ArbitrageEngine` |
| `src/strategies/arbitrage/instruments.py` | loads exchange instruments and symbol mapping | `InstrumentCatalog`, `load_instruments()` |
| `src/strategies/arbitrage/models.py` | data models for opportunity, execution, risk | `ArbitrageOpportunity`, `RiskDecision`, `LiveExecutionReport` |
| `src/strategies/arbitrage/risk.py` | trade approval logic | `OpportunityRiskManager` |
| `src/risk/risk_manager.py` | risk guardrails and state handling | `RiskLimits`, `RiskState`, `RiskManager` |
| `src/strategies/arbitrage/live_execution.py` | actual side execution and reconciliation logic | `LiveArbitrageExecutor`, `LiveOrderReconciliationError` |
| `src/strategies/arbitrage/storage.py` | writes market and execution CSV records | `CsvJournal` |

### Infra / logging

| File | Purpose | Main class / function |
| --- | --- | --- |
| `src/infra/logging.py` | terminal dashboard formatter and logger setup | `configure_logging()`, `get_logger()`, `_compact_console_formatter()` |
| `src/infra/redis_client.py` | optional Redis access | `get_redis_client()` |

### Domain models

| File | Purpose | Main class / function |
| --- | --- | --- |
| `src/core/entities.py` | domain and market entities | `Instrument`, `MarketQuote`, `Order`, `Trade`, `Position`, `Signal` |
| `src/core/interfaces.py` | broker and repository abstractions | `IBrokerGateway`, `IMarketDataFeed` |
| `src/core/exceptions.py` | trade and infra exception types | custom exception classes |

---

## 4. What is stored and what is not

### Stored in the knowledge base / journal

This project writes local CSV-based operational records to `knowledge_base/`.

Files include:

- `market_quotes.csv`
- `opportunities.csv`
- `live_order_events.csv`
- `live_executions.csv`

These are used for:

- debugging quote quality
- tracking detected opportunities
- reviewing whether a trade was executed
- understanding P&L and risk events
- manual reconciliation when order state is unexpected

### Not active by default

The app does not use Postgres or ClickHouse by default.

This is intentional to keep the project simple and easy to operate.

If you later need database persistence, you can add it as a separate optional layer and keep it out of the default runtime path.

---

## 5. Environment variables and what they do

The settings are defined in `src/config/settings.py`.

### Required for Angel One live trading

Set these in a `.env` file at the project root:

```env
APP_ENV=development
LOG_LEVEL=INFO

ANGEL_ONE_API_KEY=your_api_key
ANGEL_ONE_CLIENT_ID=your_client_id
ANGEL_ONE_PASSWORD=your_password
ANGEL_ONE_TOTP_SECRET=your_totp_secret
```

What they do:

- `ANGEL_ONE_API_KEY` -> broker API access key
- `ANGEL_ONE_CLIENT_ID` -> Angel One client ID / username
- `ANGEL_ONE_PASSWORD` -> password
- `ANGEL_ONE_TOTP_SECRET` -> TOTP secret used to generate OTP

### Live trading safety flags

```env
LIVE_TRADING_ENABLED=false
LIVE_TRADING_ACKNOWLEDGEMENT=
```

What they do:

- `LIVE_TRADING_ENABLED=false` keeps the bot in fail-closed mode by default
- `LIVE_TRADING_ACKNOWLEDGEMENT` must match the exact string `I_ACCEPT_LIVE_TRADING_RISK` before live execution is allowed
- this is a safety gate to avoid accidental trading

### Arbitrage limits

```env
ARBITRAGE_MAX_EXPOSURE_INR=300
ARBITRAGE_MAX_DAILY_LOSS_INR=60
ARBITRAGE_MAX_FALLBACK_LOSS_INR=30
```

What they do:

- maximum order exposure per configured constraints
- maximum daily loss before kill switch
- fallback loss threshold if a trade cannot be closed cleanly

### Redis (optional)

```env
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

Only use these if you intentionally want Redis for optional cache or lightweight state.

### Security / defaults

```env
JWT_SECRET_KEY=change_me_dev_only
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60
CREDENTIAL_ENCRYPTION_KEY=
```

These are not needed for the pure arbitrage runner unless you later extend the project into APIs or auth flows.

---

## 6. What to change for what

### If you want to change watched symbols

Edit:

- `src/strategies/arbitrage/config.py`

Look for:

```python
symbols: tuple[str, ...] = (
    "HDFCBANK",
    "SOBHA",
)
```

Change to your desired symbols.

### If you want to change risk and notional caps

Edit:

- `src/strategies/arbitrage/config.py`
- or the environment values in `.env`

Key fields:

- `max_order_quantity`
- `max_order_notional`
- `min_net_profit`
- `max_daily_loss`
- `max_fallback_loss`

### If you want to change broker credentials

Edit `.env` with your Angel One values.

### If you want to switch to live trading

Set:

```env
LIVE_TRADING_ENABLED=true
LIVE_TRADING_ACKNOWLEDGEMENT=I_ACCEPT_LIVE_TRADING_RISK
```

Then ensure the broker account is flat and there are no pre-existing open positions.

### If you want to keep the project simple

Leave:

- Postgres disabled
- ClickHouse disabled
- Redis optional only
- trade journaling in CSV only

### If you want future DB storage later

Add the DB layer separately and keep it isolated from the trading engine. Do not mix it into the core arbitrage flow until you truly need it.

---

## 7. How to run the app

### Windows / local venv

From the project root:

```powershell
.\.venv\Scripts\python.exe scripts\arbitrage_watcher.py
```

Or:

```powershell
python scripts\arbitrage_watcher.py
```

### What should happen at startup

- settings are loaded
- logger is initialized
- live-trading safety checks run
- instrument catalog is loaded
- exchange feed starts
- quote updates are processed
- matching opportunities are evaluated
- risk logic approves or rejects
- execution runs if allowed

### If startup fails

Typical reasons:

- `LIVE_TRADING_ENABLED` is off
- `LIVE_TRADING_ACKNOWLEDGEMENT` is wrong
- Angel One credentials are missing
- symbol data is missing from `data/share_response.json`
- account has open positions or open orders

The application is intentionally fail-closed.

---

## 8. Important notes for this project

- This is a minimal arbitrage runner, not a full exchange platform.
- It is designed to be understandable and easy to debug.
- The actual “knowledge base” is a CSV journal, not a heavy database.
- The terminal output is intentionally formatted for easier human reading.
- The system is protected by strict risk checks before live order execution.

---

## 9. Recommended working setup

For a clean beginner-friendly architecture:

- keep only the arbitrage path active
- keep CSV journal as local log storage
- only add Postgres / ClickHouse when you need analytical queries or a long-term warehouse
- keep Redis optional and small
- keep settings and `.env` as the main control surface

This is the current recommended operating model for the project.
