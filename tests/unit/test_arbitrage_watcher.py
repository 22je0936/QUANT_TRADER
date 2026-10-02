from __future__ import annotations

import json
from dataclasses import replace

from src.core.arbitrage_config import Config
from strategy.arbitrage.instruments import load_instruments
from strategy.arbitrage.signals import ArbitrageSignalEngine, Quote, parse_quote


def test_load_instruments_maps_exchange_tokens_and_reports_missing(tmp_path):
    scrip_file = tmp_path / "scrips.json"
    scrip_file.write_text(
        json.dumps(
            [
                {"name": "AAA", "exch_seg": "NSE", "symbol": "AAA-EQ", "token": "1"},
                {"name": "AAA", "exch_seg": "BSE", "symbol": "AAA", "token": "2"},
                {"name": "BBB", "exch_seg": "NSE", "symbol": "BBB-EQ", "token": "3"},
            ]
        ),
        encoding="utf-8",
    )

    catalog = load_instruments(scrip_file, ("AAA", "BBB"))

    assert catalog.by_name["AAA"]["NSE"].symbol == "AAA-EQ"
    assert catalog.by_token[(1, "1")] == ("AAA", "NSE")
    assert catalog.missing_names == ("BBB",)


def test_parse_quote_selects_best_levels_and_converts_minor_units():
    quote = parse_quote(
        {
            "best_5_buy_data": [
                {"price": "10000", "quantity": "5"},
                {"price": "10100", "quantity": "2"},
            ],
            "best_5_sell_data": [
                {"price": "10300", "quantity": "4"},
                {"price": "10200", "quantity": "3"},
            ],
        },
        timestamp=10.0,
    )

    assert quote == Quote(101.0, 2, 102.0, 3, 10.0)


def test_signal_engine_emits_opportunity_and_applies_cooldown():
    engine = ArbitrageSignalEngine(Config())
    nse_quote = Quote(bid=99.0, bid_qty=5, ask=100.0, ask_qty=3, timestamp=10.0)
    bse_quote = Quote(bid=101.0, bid_qty=2, ask=102.0, ask_qty=4, timestamp=10.5)

    assert engine.update_quote("AAA", "NSE", nse_quote, now=10.5) is None
    signal = engine.update_quote("AAA", "BSE", bse_quote, now=10.5)

    assert signal is not None
    assert (signal.buy_exchange, signal.sell_exchange) == ("NSE", "BSE")
    assert signal.quantity == 2
    assert engine.evaluate("AAA", now=11.0) is None


def test_signal_engine_rejects_stale_quotes_and_insufficient_quantity():
    config = replace(Config(), max_quote_age=1.0, min_qty=2)
    engine = ArbitrageSignalEngine(config)
    assert engine.update_quote(
        "AAA", "NSE", Quote(99.0, 5, 100.0, 1, 10.0), now=10.0
    ) is None
    assert engine.update_quote(
        "AAA", "BSE", Quote(101.0, 1, 102.0, 5, 12.0), now=12.0
    ) is None

    signal = engine.update_quote(
        "AAA", "NSE", Quote(99.0, 5, 100.0, 3, 12.0), now=12.0
    )
    assert signal is None