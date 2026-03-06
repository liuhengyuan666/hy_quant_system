from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from data_storage.database import Base


class MarketPrice(Base):
    __tablename__ = "market_price"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_market_price_symbol_date"),
        Index("ix_market_price_symbol_date", "symbol", "date"),
    )


class TechnicalIndicator(Base):
    __tablename__ = "technical_indicator"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    ma20: Mapped[float | None] = mapped_column(Float, nullable=True)
    ma60: Mapped[float | None] = mapped_column(Float, nullable=True)
    macd: Mapped[float | None] = mapped_column(Float, nullable=True)
    macd_signal: Mapped[float | None] = mapped_column(Float, nullable=True)
    macd_hist: Mapped[float | None] = mapped_column(Float, nullable=True)
    rsi: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_technical_indicator_symbol_date"),
        Index("ix_technical_indicator_symbol_date", "symbol", "date"),
    )


class SignalRecord(Base):
    __tablename__ = "signal_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="eod")
    bar_frequency: Mapped[str] = mapped_column(String(8), nullable=False, default="D")
    signal: Mapped[str] = mapped_column(String(8), nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("date", "symbol", "strategy", "mode", "bar_frequency", name="uq_signal_record_scope"),
        Index("ix_signal_record_scope", "date", "mode", "bar_frequency", "symbol"),
    )


class RealtimeBar(Base):
    __tablename__ = "realtime_bar"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    bar_frequency: Mapped[str] = mapped_column(String(8), nullable=False, default="5")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="akshare")
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("symbol", "ts", "bar_frequency", name="uq_realtime_bar_scope"),
        Index("ix_realtime_bar_scope", "symbol", "bar_frequency", "ts"),
    )


class IntradaySignalRecord(Base):
    __tablename__ = "intraday_signal_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    bar_frequency: Mapped[str] = mapped_column(String(8), nullable=False, default="5")
    signal: Mapped[str] = mapped_column(String(8), nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("ts", "symbol", "strategy", "bar_frequency", name="uq_intraday_signal_scope"),
        Index("ix_intraday_signal_scope", "ts", "bar_frequency", "symbol"),
    )
