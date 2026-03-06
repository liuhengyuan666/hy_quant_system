from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from data_storage.models import IntradaySignalRecord, RealtimeBar


def _to_datetime(value: object) -> datetime:
    converted = pd.to_datetime(str(value), errors="coerce")
    if pd.isna(converted):
        raise ValueError(f"invalid datetime value: {value}")
    return converted.to_pydatetime()


def _to_float(value: object, default: float = 0.0) -> float:
    converted = pd.to_numeric([value], errors="coerce")[0]
    if pd.isna(converted):
        return default
    return float(converted)


def upsert_realtime_bars(session: Session, rows: Sequence[Mapping[str, object]]) -> int:
    cleaned: list[dict[str, object]] = []
    for row in rows:
        cleaned.append(
            {
                "ts": _to_datetime(row["ts"]),
                "symbol": str(row["symbol"]),
                "bar_frequency": str(row.get("bar_frequency", "5")),
                "source": str(row.get("source", "akshare")),
                "open": _to_float(row.get("open")),
                "high": _to_float(row.get("high")),
                "low": _to_float(row.get("low")),
                "close": _to_float(row.get("close")),
                "volume": _to_float(row.get("volume"), default=0.0),
            }
        )
    if not cleaned:
        return 0

    stmt = pg_insert(RealtimeBar).values(cleaned)
    stmt = stmt.on_conflict_do_update(
        index_elements=["symbol", "ts", "bar_frequency"],
        set_={
            "source": stmt.excluded.source,
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


def load_realtime_bars_map(session: Session, symbols: Sequence[str], bar_frequency: str = "5", limit: int = 120) -> dict[str, pd.DataFrame]:
    data: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        stmt = (
            select(RealtimeBar)
            .where(RealtimeBar.symbol == symbol, RealtimeBar.bar_frequency == bar_frequency)
            .order_by(RealtimeBar.ts.desc())
            .limit(limit)
        )
        rows = list(session.scalars(stmt).all())
        if not rows:
            data[symbol] = pd.DataFrame(columns=["symbol", "date", "open", "high", "low", "close", "volume"])
            continue
        records = [
            {
                "symbol": row.symbol,
                "date": row.ts,
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
            }
            for row in reversed(rows)
        ]
        data[symbol] = pd.DataFrame(records)
    return data


def upsert_intraday_signals(session: Session, rows: Sequence[Mapping[str, object]]) -> int:
    cleaned: list[dict[str, object]] = []
    for row in rows:
        cleaned.append(
            {
                "ts": _to_datetime(row["ts"]),
                "symbol": str(row["symbol"]),
                "strategy": str(row["strategy"]),
                "bar_frequency": str(row.get("bar_frequency", "5")),
                "signal": str(row["signal"]),
                "score": None if row.get("score") is None else _to_float(row.get("score")),
                "meta": row.get("meta") if isinstance(row.get("meta"), dict) else None,
            }
        )
    if not cleaned:
        return 0

    stmt = pg_insert(IntradaySignalRecord).values(cleaned)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ts", "symbol", "strategy", "bar_frequency"],
        set_={
            "signal": stmt.excluded.signal,
            "score": stmt.excluded.score,
            "meta": stmt.excluded.meta,
        },
    )
    session.execute(stmt)
    return len(cleaned)


def load_intraday_signals(session: Session, signal_ts: datetime, bar_frequency: str = "5") -> pd.DataFrame:
    stmt = (
        select(IntradaySignalRecord)
        .where(IntradaySignalRecord.ts == signal_ts, IntradaySignalRecord.bar_frequency == bar_frequency)
        .order_by(IntradaySignalRecord.strategy.asc(), IntradaySignalRecord.symbol.asc())
    )
    rows = list(session.scalars(stmt).all())
    if not rows:
        return pd.DataFrame(columns=["ts", "symbol", "strategy", "bar_frequency", "signal", "score", "meta"])
    return pd.DataFrame(
        [
            {
                "ts": row.ts,
                "symbol": row.symbol,
                "strategy": row.strategy,
                "bar_frequency": row.bar_frequency,
                "signal": row.signal,
                "score": row.score,
                "meta": row.meta,
            }
            for row in rows
        ]
    )


def load_latest_intraday_signal_ts(session: Session, bar_frequency: str = "5") -> datetime | None:
    stmt = select(func.max(IntradaySignalRecord.ts)).where(IntradaySignalRecord.bar_frequency == bar_frequency)
    value = session.execute(stmt).scalar_one_or_none()
    if value is None:
        return None
    return _to_datetime(value)
