"""Order flow analytics — computed from tick/order-book data. Broker-agnostic."""
from __future__ import annotations

import pandas as pd


def bid_ask_imbalance(bid_volume: pd.Series, ask_volume: pd.Series) -> pd.Series:
    """Range [-1, 1]: positive = buy-side pressure, negative = sell-side pressure."""
    total = bid_volume + ask_volume
    return (bid_volume - ask_volume) / total.replace(0, pd.NA)


def cumulative_delta(signed_volume: pd.Series) -> pd.Series:
    """signed_volume: positive for buyer-initiated trades, negative for seller-initiated."""
    return signed_volume.cumsum()


def volume_profile(price: pd.Series, volume: pd.Series, bins: int = 20) -> pd.DataFrame:
    """Volume traded at each price bucket — used to find high-volume nodes (support/resistance)."""
    buckets = pd.cut(price, bins=bins)
    profile = volume.groupby(buckets, observed=True).sum()
    return profile.reset_index().rename(columns={profile.index.name or "index": "price_bucket", 0: "volume"})
