"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-17

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "broker_credentials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("broker_provider", sa.String(50), nullable=False),
        sa.Column("encrypted_payload", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "instruments",
        sa.Column("instrument_id", sa.String(64), primary_key=True),
        sa.Column("trading_symbol", sa.String(64), nullable=False, index=True),
        sa.Column("exchange", sa.String(16), nullable=False),
        sa.Column("instrument_type", sa.String(16), nullable=False),
        sa.Column("lot_size", sa.Integer, nullable=False, server_default="1"),
        sa.Column("tick_size", sa.Numeric(10, 4), nullable=False, server_default="0.05"),
        sa.Column("expiry", sa.DateTime, nullable=True),
        sa.Column("strike", sa.Numeric(18, 4), nullable=True),
        sa.Column("broker_tokens", sa.JSON, nullable=False, server_default="{}"),
    )

    op.create_table(
        "strategies",
        sa.Column("strategy_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.String, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "orders",
        sa.Column("client_order_id", sa.String(64), primary_key=True),
        sa.Column("broker_order_id", sa.String(64), nullable=True),
        sa.Column("instrument_id", sa.String(64), nullable=False, index=True),
        sa.Column("transaction_type", sa.String(8), nullable=False),
        sa.Column("order_type", sa.String(16), nullable=False),
        sa.Column("product_type", sa.String(16), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("price", sa.Numeric(18, 4), nullable=True),
        sa.Column("trigger_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("filled_quantity", sa.Integer, nullable=False, server_default="0"),
        sa.Column("average_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("strategy_id", sa.String(64), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "trades",
        sa.Column("trade_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("order_client_id", sa.String(64), nullable=False, index=True),
        sa.Column("instrument_id", sa.String(64), nullable=False, index=True),
        sa.Column("transaction_type", sa.String(8), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("price", sa.Numeric(18, 4), nullable=False),
        sa.Column("strategy_id", sa.String(64), nullable=True, index=True),
        sa.Column("executed_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "backtest_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("strategy_id", sa.String(64), nullable=False, index=True),
        sa.Column("instrument_id", sa.String(64), nullable=False),
        sa.Column("start_date", sa.DateTime, nullable=False),
        sa.Column("end_date", sa.DateTime, nullable=False),
        sa.Column("total_trades", sa.Integer, nullable=False, server_default="0"),
        sa.Column("win_rate", sa.Numeric(6, 4), nullable=True),
        sa.Column("sharpe_ratio", sa.Numeric(10, 4), nullable=True),
        sa.Column("max_drawdown", sa.Numeric(10, 4), nullable=True),
        sa.Column("ending_cash", sa.Numeric(18, 4), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("backtest_results")
    op.drop_table("trades")
    op.drop_table("orders")
    op.drop_table("strategies")
    op.drop_table("instruments")
    op.drop_table("broker_credentials")
    op.drop_table("users")
