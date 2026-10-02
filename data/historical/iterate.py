from __future__ import annotations

import csv
import json
from pathlib import Path
from datetime import datetime


ROOT = Path(__file__).resolve().parents[2]

NSE_FILE = ROOT / "data" / "historical"  / "data" / "equity_RELIANCE_2026-10-01_nse.json"
BSE_FILE = ROOT / "data" / "historical"  / "data" / "equity_RELIANCE_2026-10-01_bse.json"
OUTPUT_FILE = ROOT / "data" / "historical" / "analysis" / "arbitrage_analysis.csv"

 
# -----------------------------
# Load JSON
# -----------------------------
with open(NSE_FILE, "r") as file:
    nse_data = json.load(file)

with open(BSE_FILE, "r") as file:
    bse_data = json.load(file)


# -----------------------------
# Convert candles into dictionaries
# indexed by timestamp
# -----------------------------
nse_candles = {
    candle["timestamp"]: candle
    for candle in nse_data["candles"]
}

bse_candles = {
    candle["timestamp"]: candle
    for candle in bse_data["candles"]
}


# Only timestamps available in BOTH exchanges
common_timestamps = sorted(
    set(nse_candles.keys()) & set(bse_candles.keys())
)


rows = []


for timestamp in common_timestamps:

    nse = nse_candles[timestamp]
    bse = bse_candles[timestamp]

    # -----------------------------
    # Prices
    # -----------------------------
    nse_close = nse["close"]
    bse_close = bse["close"]

    price_difference = bse_close - nse_close

    # Percentage spread relative to NSE
    spread_percent = (
        price_difference / nse_close
    ) * 100

    # Absolute spread
    absolute_spread = abs(price_difference)

    # -----------------------------
    # Volume
    # -----------------------------
    nse_volume = nse["volume"]
    bse_volume = bse["volume"]

    if nse_volume > 0:
        volume_ratio = bse_volume / nse_volume
    else:
        volume_ratio = 0

    # -----------------------------
    # Determine direction
    # -----------------------------
    if price_difference > 0:
        direction = "BUY NSE / SELL BSE"

    elif price_difference < 0:
        direction = "BUY BSE / SELL NSE"

    else:
        direction = "NO DIFFERENCE"

    # -----------------------------
    # Time conversion
    # -----------------------------
    dt = datetime.fromisoformat(timestamp)

    time_ampm = dt.strftime("%I:%M:%S %p")

    # -----------------------------
    # Add row
    # -----------------------------
    rows.append({
        "date": dt.strftime("%Y-%m-%d"),
        "time": time_ampm,

        "nse_close": nse_close,
        "bse_close": bse_close,

        "price_difference": round(price_difference, 4),
        "absolute_spread": round(absolute_spread, 4),
        "spread_percent": round(spread_percent, 4),

        "nse_open": nse["open"],
        "nse_high": nse["high"],
        "nse_low": nse["low"],

        "bse_open": bse["open"],
        "bse_high": bse["high"],
        "bse_low": bse["low"],

        "nse_volume": nse_volume,
        "bse_volume": bse_volume,
        "volume_ratio_bse_nse": round(volume_ratio, 4),

        "arbitrage_direction": direction
    })


# -----------------------------
# Save CSV
# -----------------------------
if rows:

    fieldnames = rows[0].keys()

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(rows)


print(f"Saved {len(rows)} rows")
print(f"CSV: {OUTPUT_FILE}")