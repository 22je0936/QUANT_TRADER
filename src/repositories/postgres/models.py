"""SQLAlchemy ORM models — PostgreSQL persistence for users, instruments, orders,
trades, strategies and backtest results. Tick data lives in ClickHouse, not here.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infra.db import Base


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    broker_credentials: Mapped[list["BrokerCredentialModel"]] = relationship(back_populates="user")


class BrokerCredentialModel(Base):
    """Encrypted per-user broker API credentials — never store plaintext secrets."""

    __tablename__ = "broker_credentials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    broker_provider: Mapped[str] = mapped_column(String(50))
    encrypted_payload: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[UserModel] = relationship(back_populates="broker_credentials")


class InstrumentModel(Base):
    __tablename__ = "instruments"

    instrument_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trading_symbol: Mapped[str] = mapped_column(String(64), index=True)
    exchange: Mapped[str] = mapped_column(String(16))
    instrument_type: Mapped[str] = mapped_column(String(16))
    lot_size: Mapped[int] = mapped_column(default=1)
    tick_size: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0.05"))
    expiry: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    strike: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    broker_tokens: Mapped[dict] = mapped_column(JSON, default=dict)


class StrategyModel(Base):
    __tablename__ = "strategies"

    strategy_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OrderModel(Base):
    __tablename__ = "orders"

    client_order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    instrument_id: Mapped[str] = mapped_column(String(64), index=True)
    transaction_type: Mapped[str] = mapped_column(String(8))
    order_type: Mapped[str] = mapped_column(String(16))
    product_type: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[int] = mapped_column()
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    trigger_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    filled_quantity: Mapped[int] = mapped_column(default=0)
    average_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    strategy_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TradeModel(Base):
    __tablename__ = "trades"

    trade_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_client_id: Mapped[str] = mapped_column(String(64), index=True)
    instrument_id: Mapped[str] = mapped_column(String(64), index=True)
    transaction_type: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[int] = mapped_column()
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    strategy_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BacktestResultModel(Base):
    __tablename__ = "backtest_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_id: Mapped[str] = mapped_column(String(64), index=True)
    instrument_id: Mapped[str] = mapped_column(String(64))
    start_date: Mapped[datetime] = mapped_column(DateTime)
    end_date: Mapped[datetime] = mapped_column(DateTime)
    total_trades: Mapped[int] = mapped_column(default=0)
    win_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    sharpe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    max_drawdown: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    ending_cash: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
