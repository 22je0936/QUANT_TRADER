# Requirements

## 1. Functional Requirements

### 1.1 Broker Abstraction
- FR-1: The system SHALL define a broker-agnostic `IBrokerGateway` interface
  covering: authentication, place/modify/cancel order, get positions,
  get holdings, get margins, get order status.
- FR-2: The system SHALL define an `IMarketDataFeed` interface for
  subscribe/unsubscribe to instruments and streaming tick callbacks.
- FR-3: The system SHALL provide an Angel One SmartAPI adapter as the first
  implementation, and a Zerodha Kite adapter as a later implementation of
  the same interfaces, selectable via configuration without code changes
  to strategy/service/risk layers.
- FR-4: The system SHALL provide a `PaperBrokerAdapter` (simulated
  execution) usable interchangeably with live adapters for safe testing.
- FR-5: An instrument mapping layer SHALL translate broker-specific
  symbols/tokens to a canonical internal instrument ID.

### 1.2 Market Data
- FR-6: The system SHALL ingest real-time tick data via broker WebSocket
  feeds and persist it to ClickHouse.
- FR-7: The system SHALL maintain the latest tick/LTP per instrument in
  Redis for low-latency access.
- FR-8: The system SHALL generate OHLC candles (1m/5m/15m/1d, etc.) from
  tick data.
- FR-9: The system SHALL maintain an instrument master synced from broker
  and exchange data in PostgreSQL.

### 1.3 Analytics Modules
- FR-10: Technical indicators (SMA, EMA, RSI, MACD, ATR, VWAP, Bollinger
  Bands, etc.) SHALL be implemented as pure, broker-independent functions.
- FR-11: Order flow analytics (bid-ask imbalance, cumulative delta, volume
  profile) SHALL be computed from tick/order book data.
- FR-12: Options analytics SHALL include option chain construction, Greeks
  (delta/gamma/theta/vega/rho), implied volatility, OI change, PCR.

### 1.4 Signal Generation & Strategies
- FR-13: Strategies SHALL implement an `ISignalGenerator` interface and
  SHALL NOT import or reference any broker-specific class.
- FR-14: The `StrategyRunner` SHALL orchestrate data retrieval, signal
  generation, risk validation, and order placement via injected interfaces.

### 1.5 Risk Management
- FR-15: All orders SHALL pass through pre-trade risk checks (position
  size limits, daily loss limits, exposure limits, margin checks).
- FR-16: The system SHALL support a kill-switch to flatten positions and
  disable a strategy automatically on risk breach.
- FR-17: The system SHALL track real-time P&L per strategy/user/portfolio.

### 1.6 Backtesting
- FR-18: The backtesting engine SHALL reuse the same strategy, signal, and
  risk code used in live/paper trading (no duplicated strategy logic).
- FR-19: The backtesting engine SHALL model slippage, brokerage/taxes, and
  partial fills.
- FR-20: Backtest results (trades, equity curve, performance metrics)
  SHALL be persisted in PostgreSQL.

### 1.7 API & Users
- FR-21: The system SHALL expose a FastAPI-based REST API for strategies,
  backtests, orders, positions, instruments, and risk configuration.
- FR-22: The system SHALL support multi-user accounts with per-user
  encrypted broker API credentials.
- FR-23: The system SHALL provide authentication (JWT/OAuth2) and
  authorization for all endpoints.

---

## 2. Non-Functional Requirements

### 2.1 Architecture & Code Quality
- NFR-1: Follow Clean Architecture / Hexagonal (Ports & Adapters) with
  strict dependency direction (core has zero dependency on brokers/DBs).
- NFR-2: Follow SOLID principles; enforce via code review and static
  analysis (e.g., import-linter to forbid `strategies` importing `brokers`).
- NFR-3: All cross-layer communication SHALL go through interfaces
  (repository pattern for persistence, gateway pattern for brokers).
- NFR-4: Use dependency injection (constructor injection) — no service
  should instantiate its own dependencies.

### 2.2 Performance & Scalability
- NFR-5: Tick ingestion → ClickHouse persistence latency SHALL be < 500ms
  under normal load.
- NFR-6: The architecture SHALL support horizontal scaling of ingestion
  and signal-processing services (statelessness + partitioned consumers).
- NFR-7: The system SHALL be designed to introduce Kafka as an event bus
  between ingestion and downstream consumers without core logic changes.
- NFR-8: Redis SHALL be used to avoid ClickHouse/PostgreSQL reads on the
  hot path (LTP lookups, session/cache data).

### 2.3 Reliability
- NFR-9: Broker adapters SHALL implement retry with backoff and circuit
  breaker around network calls; WebSocket feeds SHALL auto-reconnect.
- NFR-10: Order placement SHALL be idempotent (client order IDs) to avoid
  duplicate orders on retry.
- NFR-11: The system SHALL degrade gracefully — a broker/market-data
  outage SHALL trigger the kill-switch, not silent failure.

### 2.4 Security
- NFR-12: Broker API keys/secrets SHALL be encrypted at rest and never
  logged; loaded via a secrets manager or environment-only injection.
- NFR-13: All API endpoints SHALL require authentication; sensitive
  actions (order placement, credential update) SHALL require
  authorization checks and audit logging.
- NFR-14: Input validation on all API boundaries (Pydantic schemas).

### 2.5 Observability
- NFR-15: Structured (JSON) logging with correlation/trace IDs across
  ingestion → signal → risk → order flow.
- NFR-16: Metrics (Prometheus) for tick latency, order latency, risk
  breaches, strategy P&L; dashboards (Grafana).
- NFR-17: Distributed tracing (OpenTelemetry) across service boundaries.

### 2.6 Testability
- NFR-18: Every module (indicators, order flow, options analytics, risk)
  SHALL be unit-testable with no network/DB/broker dependency.
- NFR-19: A shared contract test suite SHALL validate every
  `IBrokerGateway`/`IMarketDataFeed` implementation (Angel One, Kite,
  Paper) behaves consistently.
- NFR-20: CI SHALL run lint, type-check (mypy), unit, and contract tests
  on every push; integration tests on merge to main.

### 2.7 Compliance & Market-Specific
- NFR-21: The system SHALL honor SEBI/exchange rate limits per broker API
  (rate limiting per broker, per endpoint).
- NFR-22: The system SHALL be timezone-aware (Asia/Kolkata) and respect
  the NSE/BSE trading calendar (holidays, session times, special sessions).
- NFR-23: Order/trade records SHALL be retained per regulatory record
  keeping requirements and SHALL be immutable/append-only in storage.

---

## 3. Technology Requirements

| Concern | Technology |
|---|---|
| API Framework | FastAPI |
| Tick/time-series storage | ClickHouse |
| Relational storage (users, trades, strategies, backtests) | PostgreSQL |
| Caching / low-latency access | Redis |
| Broker (initial) | Angel One SmartAPI |
| Broker (future) | Zerodha Kite Connect |
| Event streaming (future) | Kafka |
| ORM / migrations | SQLAlchemy + Alembic |
| Validation | Pydantic v2 |
| Auth | OAuth2 / JWT (e.g., `python-jose`, `passlib`) |
| Numerical/data | NumPy, pandas or Polars |
| Testing | Pytest, pytest-asyncio, testcontainers |
| Static analysis | mypy, ruff, black, import-linter |
| Observability | Prometheus client, OpenTelemetry, structlog |
| Containerization | Docker, docker-compose (k8s later) |

---

## 4. Out of Scope (initial release)

- Kafka event bus (planned, not required for MVP).
- Machine learning signal generation (planned, interface reserved via
  `ISignalGenerator`).
- Multi-broker simultaneous live trading for a single strategy.
- Mobile/web front-end (API-only for now).
