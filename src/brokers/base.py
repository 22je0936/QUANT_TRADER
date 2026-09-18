"""Shared helpers for broker adapters: retry/backoff and circuit-breaker decorators."""
from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core.exceptions import BrokerConnectionError

T = TypeVar("T")


def with_broker_retry(func: Callable[..., T]) -> Callable[..., T]:
    """Retry transient broker connection failures with exponential backoff."""
    return retry(
        retry=retry_if_exception_type(BrokerConnectionError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )(func)
