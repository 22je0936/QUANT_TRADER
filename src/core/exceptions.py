"""Domain-level exceptions. Broker adapters must translate their own errors into these."""
from __future__ import annotations


class QuantTraderError(Exception):
    """Base class for all domain errors."""


class BrokerConnectionError(QuantTraderError):
    """Raised when a broker adapter cannot establish/maintain a connection."""


class BrokerAuthenticationError(QuantTraderError):
    """Raised when broker authentication fails."""


class OrderRejectedError(QuantTraderError):
    """Raised when a broker rejects an order."""


class RiskLimitBreachedError(QuantTraderError):
    """Raised when an order or position would breach a configured risk limit."""


class InstrumentNotFoundError(QuantTraderError):
    """Raised when an instrument cannot be resolved to a canonical ID or broker token."""


class InsufficientMarginError(QuantTraderError):
    """Raised when the account does not have enough margin for an order."""
