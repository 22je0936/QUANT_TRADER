import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

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

def main() -> None:
    with (ROOT / "data" / "bse_share.json").open(encoding="utf-8") as source:
        bse_data = json.load(source)
    with (ROOT / "data" / "nse_share.json").open(encoding="utf-8") as source:
        nse_data = json.load(source)

    watchlist = set(WATCHLIST)
    instruments = [
        item
        for item in bse_data + nse_data
        if item.get("exch_seg") in {"NSE", "BSE"}
        and item.get("name", "").upper() in watchlist
    ]
    output_file = ROOT / "data" / "share_response.json"
    output_file.write_text(
        json.dumps(instruments, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Saved {len(instruments)} instruments to {output_file}")


if __name__ == "__main__":
    main()
