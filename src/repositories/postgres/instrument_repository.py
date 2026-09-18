"""SQLAlchemy-backed implementation of IInstrumentRepository."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.entities import Exchange, Instrument, InstrumentType
from src.core.interfaces import IInstrumentRepository
from src.repositories.postgres.models import InstrumentModel


def _to_entity(model: InstrumentModel) -> Instrument:
    return Instrument(
        instrument_id=model.instrument_id,
        trading_symbol=model.trading_symbol,
        exchange=Exchange(model.exchange),
        instrument_type=InstrumentType(model.instrument_type),
        lot_size=model.lot_size,
        tick_size=model.tick_size,
        expiry=model.expiry,
        strike=model.strike,
        broker_tokens=model.broker_tokens or {},
    )


class PostgresInstrumentRepository(IInstrumentRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_instrument_id(self, instrument_id: str) -> Instrument | None:
        model = self._session.get(InstrumentModel, instrument_id)
        return _to_entity(model) if model else None

    def get_by_broker_token(self, broker_name: str, token: str) -> Instrument | None:
        stmt = select(InstrumentModel)
        for model in self._session.scalars(stmt):
            if (model.broker_tokens or {}).get(broker_name) == token:
                return _to_entity(model)
        return None

    def upsert(self, instrument: Instrument) -> None:
        model = self._session.get(InstrumentModel, instrument.instrument_id)
        if model is None:
            model = InstrumentModel(instrument_id=instrument.instrument_id)
            self._session.add(model)

        model.trading_symbol = instrument.trading_symbol
        model.exchange = instrument.exchange.value
        model.instrument_type = instrument.instrument_type.value
        model.lot_size = instrument.lot_size
        model.tick_size = instrument.tick_size
        model.expiry = instrument.expiry
        model.strike = instrument.strike
        model.broker_tokens = instrument.broker_tokens
