"""
Cancel an open Angel One order.

Usage (from the project root):
    python scripts/cancel_angel_one_order.py                    # uses data/last_order.json
    python scripts/cancel_angel_one_order.py --order-id 2510XXXXXXXXXX
    python scripts/cancel_angel_one_order.py --order-id 2510XXXXXXXXXX --variety NORMAL
    python scripts/cancel_angel_one_order.py --yes              # skip confirmation
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pyotp
from SmartApi import SmartConnect

# project root = first parent folder that contains "src"
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "src").exists())
sys.path.insert(0, str(ROOT))

from src.config.settings import get_settings  # noqa: E402

LAST_ORDER_FILE = ROOT / "data" / "last_order.json"

# Orders in these states can no longer be cancelled
FINAL_STATES = {"complete", "cancelled", "rejected"}


def login() -> tuple[SmartConnect, str]:
    s = get_settings()
    client = SmartConnect(api_key=s.angel_one_api_key)
    session = client.generateSession(
        s.angel_one_client_id,
        s.angel_one_password,
        pyotp.TOTP(s.angel_one_totp_secret).now(),
    )
    if not session.get("status"):
        raise SystemExit(f"Login failed: {session}")
    return client, s.angel_one_client_id


def find_order(client: SmartConnect, order_id: str) -> dict | None:
    book = client.orderBook() or {}
    for order in book.get("data") or []:
        if str(order.get("orderid")) == str(order_id):
            return order
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Cancel an Angel One order")
    parser.add_argument(
        "--order-id",
        help="order id to cancel (default: order id in data/last_order.json)",
    )
    parser.add_argument("--variety", default=None, help="NORMAL (default), AMO, STOPLOSS or ROBO")
    parser.add_argument("--yes", action="store_true", help="skip confirmation prompt")
    args = parser.parse_args()

    order_id, variety = args.order_id, args.variety
    if not order_id:
        if not LAST_ORDER_FILE.exists():
            raise SystemExit("No --order-id given and data/last_order.json does not exist.")
        last = json.loads(LAST_ORDER_FILE.read_text(encoding="utf-8"))
        order_id = last["orderid"]
        variety = variety or last.get("variety", "NORMAL")
    variety = variety or "NORMAL"

    client, client_id = login()
    try:
        order = find_order(client, order_id)
        if order:
            status = str(order.get("orderstatus", "")).lower()
            print(f"Order {order_id}: {order.get('tradingsymbol')} "
                  f"{order.get('transactiontype')} {order.get('quantity')} "
                  f"status = {status}")
            if status in FINAL_STATES:
                raise SystemExit(f"Order is already '{status}', nothing to cancel.")
        else:
            print(f"Order {order_id} not found in today's order book; will still try to cancel.")

        if not args.yes and input("Type YES to cancel this order: ").strip() != "YES":
            raise SystemExit("Not cancelled.")

        resp = client.cancelOrder(order_id, variety)
        print("Response:", resp)
    finally:
        client.terminateSession(client_id)


if __name__ == "__main__":
    main()