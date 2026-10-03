"""Terminal-friendly structured logging for a readable trader console."""
from __future__ import annotations

import logging
import sys
import textwrap
from typing import Any

import structlog

from src.config.settings import get_settings

_RESET = "\033[0m"
_BOLD = "\033[1m"
_COLORS = {
    "INFO": "\033[92m",     # green
    "WARNING": "\033[93m",  # yellow
    "ERROR": "\033[91m",    # red
    "CRITICAL": "\033[95m", # magenta
}


def _status_label(event: str, level: str) -> str:
    event_name = str(event).lower()
    if "buy" in event_name:
        return f"{_BOLD}\033[92mBUY{_RESET}"
    if "sell" in event_name:
        return f"{_BOLD}\033[91mSELL{_RESET}"
    if level == "WARNING":
        return f"{_BOLD}\033[93mWARN{_RESET}"
    if level in {"ERROR", "CRITICAL"}:
        return f"{_BOLD}\033[91mFAIL{_RESET}"
    return f"{_BOLD}\033[94mINFO{_RESET}"


_MARKET_SYMBOL_BOARD: dict[str, str] = {}


def _dashboard_summary(event: str, level: str, event_dict: dict[str, Any]) -> str:
    symbol = event_dict.get("symbol") or event_dict.get("ticker") or event_dict.get("instrument")
    action = "BUY" if "buy" in str(event).lower() else "SELL" if "sell" in str(event).lower() else "INFO"
    pnl = (
        event_dict.get("estimated_net_profit")
        or event_dict.get("estimated_net_pnl")
        or event_dict.get("pnl")
        or event_dict.get("net_pnl")
        or 0
    )
    status_text = "LIVE" if level in {"INFO", "WARNING"} else level.title()
    quoted_pnl = f"₹{pnl}" if pnl else "₹0.00"
    summary_parts = [f"P&L: {quoted_pnl}", f"STATUS: {status_text}", f"ACTION: {action}"]
    if symbol:
        summary_parts.append(f"SYMBOL: {symbol}")
    return " | ".join(summary_parts)


def _symbol_board(event: str, event_dict: dict[str, Any]) -> str:
    symbol = event_dict.get("symbol") or event_dict.get("ticker") or event_dict.get("instrument")
    if symbol:
        action = "BUY" if "buy" in str(event).lower() else "SELL" if "sell" in str(event).lower() else "WAIT"
        _MARKET_SYMBOL_BOARD[symbol] = action
        if len(_MARKET_SYMBOL_BOARD) > 5:
            _MARKET_SYMBOL_BOARD.pop(next(iter(_MARKET_SYMBOL_BOARD)))

    board_entries = []
    for symbol_name, action_name in list(_MARKET_SYMBOL_BOARD.items())[-4:]:
        board_entries.append(f"{symbol_name}:{action_name}")

    return f"WATCHLIST | {' | '.join(board_entries) if board_entries else 'NO ACTIVE SYMBOLS'}"


def _wrap_box_text(text: str, width: int) -> list[str]:
    raw = str(text)
    if not raw:
        return [""]

    wrapped = textwrap.wrap(
        raw,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
        replace_whitespace=False,
    )
    return wrapped or [raw[:width]]


def _compact_console_formatter(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> str:
    timestamp = event_dict.pop("timestamp", "")
    level = str(event_dict.pop("level", "info")).upper()
    event = event_dict.pop("event", "log")

    color = _COLORS.get(level, "\033[96m")
    status = _status_label(event, level)
    level_label = f"{_BOLD}{color}{level:<8}{_RESET}"
    event_line = (
        f"{timestamp} {level_label} {status} {event}" if timestamp else f"{level_label} {status} {event}"
    )

    width = 100
    monitor_line = "ARBITRAGE MONITOR | MODE: LIVE | MARKET: NSE/BSE | DESK: PRIMARY"
    summary_line = _dashboard_summary(event, level, event_dict)
    board_line = _symbol_board(event, event_dict)

    box_lines = ["┌" + "─" * (width - 2) + "┐"]
    for line in [monitor_line, summary_line, board_line, event_line]:
        for wrapped in _wrap_box_text(line, width - 4):
            box_lines.append(f"│ {wrapped:<{width - 4}} │")
        box_lines.append("├" + "─" * (width - 2) + "┤")

    for key, value in sorted(event_dict.items()):
        text = f"{key}: {value}"
        for wrapped in _wrap_box_text(text, width - 4):
            box_lines.append(f"│ {wrapped:<{width - 4}} │")
    box_lines.append("└" + "─" * (width - 2) + "┘")
    return "\n".join(box_lines)


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
            _compact_console_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
