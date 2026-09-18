from __future__ import annotations

import os

import certifi

from src.brokers.angel_one.angel_one_broker import configure_requests_ssl


def test_configure_requests_ssl_sets_cert_bundle(monkeypatch):
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)

    configure_requests_ssl()

    assert os.environ["REQUESTS_CA_BUNDLE"] == certifi.where()
    assert os.environ["SSL_CERT_FILE"] == certifi.where()
