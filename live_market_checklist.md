# Live Market Test Checklist

Use this checklist before starting the arbitrage watcher in the live market.

## 1. Environment and credentials

- [ ] Confirm `.env` exists in the project root.
- [ ] Confirm Angel One API key is filled.
- [ ] Confirm Angel One client ID is filled.
- [ ] Confirm Angel One password is filled.
- [ ] Confirm Angel One TOTP secret is filled.
- [ ] Confirm `LIVE_TRADING_ENABLED` is set correctly for your intended mode.
- [ ] Confirm `LIVE_TRADING_ACKNOWLEDGEMENT` matches exactly: `I_ACCEPT_LIVE_TRADING_RISK`.
- [ ] Confirm `LOG_LEVEL` is set to a readable level like `INFO`.

## 2. Safety checks

- [ ] Confirm you understand the risk limits configured in `src/strategies/arbitrage/config.py`.
- [ ] Confirm `max_order_quantity` is small enough for your test size.
- [ ] Confirm `max_order_notional` is intentionally capped.
- [ ] Confirm the account is flat and has no unexpected open positions.
- [ ] Confirm there are no leftover open orders in the broker account.
- [ ] Confirm you are not accidentally using real orders with a wrong environment flag.

## 3. Symbol and data checks

- [ ] Confirm symbol list is correct in `src/strategies/arbitrage/config.py`.
- [ ] Confirm the instrument mapping file exists and is valid.
- [ ] Confirm `data/share_response.json` has the expected stocks and exchange mappings.
- [ ] Confirm the market feed is able to connect to Angel One successfully.

## 4. Runtime checks before starting

- [ ] Run the app once in a safe environment to verify it starts without crashes.
- [ ] Watch the dashboard console for a clean startup block.
- [ ] Confirm the application shows the proper market monitor banner.
- [ ] Confirm the symbol board is populating or the feed is active.
- [ ] Confirm there are no repeated reconnect or authentication failures.

## 5. During live run

- [ ] Watch the console for BUY / SELL / WARN / FAIL labels.
- [ ] Confirm the symbol and action values look correct.
- [ ] Confirm notional and quantity values remain inside configured limits.
- [ ] Confirm risk gate is approving only valid opportunities.
- [ ] Confirm execution is not happening on stale or delayed quotes.

## 6. After trading

- [ ] Check the CSV journal in `knowledge_base/`.
- [ ] Review `market_quotes.csv`, `opportunities.csv`, and `live_executions.csv`.
- [ ] Confirm the final order state matches the expected broker execution outcome.
- [ ] Check whether any manual reconciliation is needed.
- [ ] Record any issue in notes before the next run.

## 7. Stop conditions

Stop the program immediately if:

- [ ] there are unexplained repeated feed disconnects
- [ ] the app sees invalid or stale quotes repeatedly
- [ ] risk manager rejects too many opportunities unexpectedly
- [ ] live orders appear without a matching expected opportunity
- [ ] the account is no longer flat or risk limits are violated

## 8. Basic launch command

```powershell
.\.venv\Scripts\python.exe scripts\arbitrage_watcher.py
```

## 9. Final reminder

This project is intentionally fail-closed and minimal. Live trading should only happen when the environment, credentials, risk limits, and account state are all checked and understood.
