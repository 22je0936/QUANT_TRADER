import importlib.util

import pytest

from src.brokers.angel_one.angel_one_broker import AngelOneBrokerAdapter
from src.config.settings import get_settings


s = get_settings()
requires_live_broker = not all(
    [
        s.angel_one_api_key,
        s.angel_one_client_id,
        s.angel_one_password,
        s.angel_one_totp_secret,
    ]
) or importlib.util.find_spec("pyotp") is None or importlib.util.find_spec("SmartApi") is None

pytestmark = pytest.mark.skipif(
    requires_live_broker,
    reason="Angel One live connection test requires configured credentials and optional SDK dependencies.",
)


def test_angel_one_live_connection_smoke():
    broker = AngelOneBrokerAdapter(
        s.angel_one_api_key,
        s.angel_one_client_id,
        s.angel_one_password,
        s.angel_one_totp_secret,
    )
    print(broker)
    try:
        broker.connect()
        print(broker.get_margins())
        print("Angel One authentication and read-only API test succeeded")
    finally:
        broker.disconnect()