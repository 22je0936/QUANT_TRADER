import json
import os

WATCHLIST = [
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "ITC",
    "LT",
    "AXISBANK",
    "KOTAKBANK",
]

OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "share_response.json")

with open("data/bse_share.json", "r", encoding="utf-8") as f:
    bse_data = json.load(f)

with open("data/nse_share.json", "r", encoding="utf-8") as f:
    nse_data = json.load(f)

data = bse_data + nse_data

results = [
    item
    for item in data
    if (
        item.get("exch_seg") in ["NSE", "BSE"]
        and item.get("name", "").upper() in WATCHLIST
    )
]

os.makedirs(OUTPUT_DIR, exist_ok=True)

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f"Saved {len(results)} instruments to {OUTPUT_FILE}")
