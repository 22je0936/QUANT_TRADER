
from src.config.settings import get_settings
from src.brokers.angel_one.angel_one_broker import AngelOneBrokerAdapter


import requests
print("ji")
print(
    requests.get(
        "https://apiconnect.angelone.in",
        timeout=10
    ).status_code
)


s = get_settings()
broker = AngelOneBrokerAdapter(
    s.angel_one_api_key,
    s.angel_one_client_id,
    s.angel_one_password,
    s.angel_one_totp_secret,
)

try:
    broker.connect()
    broker.get_margins()
    print("Angel One authentication and read-only API test succeeded")
finally:
    broker.disconnect()