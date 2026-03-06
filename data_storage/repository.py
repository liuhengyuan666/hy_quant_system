from __future__ import annotations

from datetime import date
from typing import Mapping, Sequence

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from data_storage.models import MarketPrice, SignalRecord, TechnicalIndicator


def _to_date(value: object) -> date:
    if isinstance(value, date):
        return value
    converted = pd.to_datetime(value, errors="coerce")
    if pd.isna(converted):
        raise ValueError(f"invalid date value: {value}")
    return converted.date()


def _to_float(value: object, default: float = 0.0) -> float:
    converted = pd.to_numeric(value, errors="coerce")
    if pd.isna(converted):
        return default
    return float(converted)


def upsert_market_prices(session: Session, rows: Sequence[Mapping[str, object]]) -> int:
    cleaned: list[dict[str, object]] = []
    for row in rows:
        cleaned.append(
            {
                "symbol": str(row["symbol"]),
                "date": _to_date(row["date"]),
                "open": _to_float(row.get("open")),
                "high": _to_float(row.get("high")),
                "low": _to_float(row.get("low")),
                "close": _to_float(row.get("close")),
                "volume": _to_float(row.get("volume"), default=0.0),
            }
        )
    if not cleaned:
        return 0

    stmt = pg_insert(MarketPrice).values(cleaned)
    stmt = stmt.on_conflict_do_update(
        index_elements=["symbol", "date"],
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
            "updated_at": func.now(),
        },
    )
    session.execute(stmt)
    return len(cleaned)


def upsert_technical_indicators(session: Session, rows: Sequence[Mapping[str, object]]) -> int:
    cleaned: list[dict[str, object]] = []
    for row in rows:
        cleaned.append(
            {
                "symbol": str(row["symbol"]),
                "date": _to_date(row["date"]),
                "ma20": _to_float(row.get("ma20"), default=float("nan")),
                "ma60": _to_float(row.get("ma60"), default=float("nan")),
                "macd": _to_float(row.get("macd"), default=float("nan")),
                "macd_signal": _to_float(row.get("macd_signal"), default=float("nan")),
                "macd_hist": _to_float(row.get("macd_hist"), default=float("nan")),
                "rsi": _to_float(row.get("rsi"), default=float("nan")),
            }
        )
    if not cleaned:
        return 0

    stmt = pg_insert(TechnicalIndicator).values(cleaned)
    stmt = stmt.on_conflict_do_update(
        index_elements=["symbol", "date"],
        set_={
            "ma20": stmt.excluded.ma20,
            "ma60": stmt.excluded.ma60,
            "macd": stmt.excluded.macd,
            "macd_signal": stmt.excluded.macd_signal,
            "macd_hist": stmt.excluded.macd_hist,
            "rsi": stmt.excluded.rsi,
            "updated_at": func.now(),
        },
    )
    session.execute(stmt)
    return len(cleaned)


def upsert_signals(session: Session, rows: Sequence[Mapping[str, object]]) -> int:
    cleaned: list[dict[str, object]] = []
    for row in rows:
        cleaned.append(
            {
                "date": _to_date(row["date"]),
                "symbol": str(row["symbol"]),
                "strategy": str(row["strategy"]),
                "mode": str(row.get("mode", "eod")),
                "bar_frequency": str(row.get("bar_frequency", "D")).upper(),
                "signal": str(row["signal"]),
                "score": None if row.get("score") is None else _to_float(row.get("score")),
                "meta": row.get("meta") if isinstance(row.get("meta"), dict) else None,
            }
        )
    if not cleaned:
        return 0

    stmt = pg_insert(SignalRecord).values(cleaned)
    stmt = stmt.on_conflict_do_update(
        index_elements=["date", "symbol", "strategy", "mode", "bar_frequency"],
        set_={
            "signal": stmt.excluded.signal,
            "score": stmt.excluded.score,
            "meta": stmt.excluded.meta,
        },
    )
    session.execute(stmt)
    return len(cleaned)


def load_market_prices(session: Session, symbol: str, limit: int = 800, as_of_date: date | None = None) -> pd.DataFrame:
    stmt = (
        select(MarketPrice)
        .where(MarketPrice.symbol == symbol)
    )
    if as_of_date is not None:
        stmt = stmt.where(MarketPrice.date <= as_of_date)
    stmt = stmt.order_by(MarketPrice.date.desc()).limit(limit)
    rows = list(session.scalars(stmt).all())
    if not rows:
        return pd.DataFrame(columns=["symbol", "date", "open", "high", "low", "close", "volume"])
    records = [
        {
            "symbol": row.symbol,
            "date": row.date,
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.close,
            "volume": row.volume,
        }
        for row in reversed(rows)
    ]
    return pd.DataFrame(records)


def load_market_prices_map(
    session: Session,
    symbols: Sequence[str],
    limit: int = 800,
    as_of_date: date | None = None,
) -> dict[str, pd.DataFrame]:
    data: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        data[symbol] = load_market_prices(session, symbol, limit=limit, as_of_date=as_of_date)
    return data


def load_latest_market_date(session: Session, symbols: Sequence[str] | None = None) -> date | None:
    stmt = select(func.max(MarketPrice.date))
    if symbols:
        stmt = stmt.where(MarketPrice.symbol.in_(list(symbols)))
    value = session.execute(stmt).scalar_one_or_none()
    if value is None:
        return None
    return _to_date(value)


def load_latest_signal_date(session: Session, mode: str | None = None, bar_frequency: str | None = None) -> date | None:
    stmt = select(func.max(SignalRecord.date))
    if mode is not None:
        stmt = stmt.where(SignalRecord.mode == mode)
    if bar_frequency is not None:
        stmt = stmt.where(SignalRecord.bar_frequency == bar_frequency.upper())
    value = session.execute(stmt).scalar_one_or_none()
    if value is None:
        return None
    return _to_date(value)


def load_signals_by_date(
    session: Session,
    signal_date: date,
    mode: str | None = None,
    bar_frequency: str | None = None,
) -> pd.DataFrame:
    stmt = (
        select(SignalRecord)
        .where(SignalRecord.date == signal_date)
    )
    if mode is not None:
        stmt = stmt.where(SignalRecord.mode == mode)
    if bar_frequency is not None:
        stmt = stmt.where(SignalRecord.bar_frequency == bar_frequency.upper())
    stmt = stmt.order_by(
        SignalRecord.bar_frequency.asc(),
        SignalRecord.strategy.asc(),
        SignalRecord.symbol.asc(),
    )
    rows = list(session.scalars(stmt).all())
    if not rows:
        return pd.DataFrame(columns=["date", "symbol", "strategy", "mode", "bar_frequency", "signal", "score", "meta"])

    records = [
        {
            "date": row.date,
            "symbol": row.symbol,
            "strategy": row.strategy,
            "mode": row.mode,
            "bar_frequency": row.bar_frequency,
            "signal": row.signal,
            "score": row.score,
            "meta": row.meta,
        }
        for row in rows
    ]
    return pd.DataFrame(records)
