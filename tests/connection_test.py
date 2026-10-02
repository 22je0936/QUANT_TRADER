
from src.config.settings import get_settings
from src.brokers.angel_one.angel_one_broker import AngelOneBrokerAdapter




s = get_settings()
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