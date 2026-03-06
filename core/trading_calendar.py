from __future__ import annotations

from datetime import date, datetime, time, timedelta

from core.clock import SHANGHAI_TZ, now_shanghai
from config.settings import RuntimeConfig, load_runtime_config

MARKET_CLOSE_TIME = time(hour=15, minute=0)


def _rollback_to_weekday(value: date) -> date:
    current = value
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def latest_closed_trading_date(reference: datetime | None = None) -> date:
    current = reference.astimezone(SHANGHAI_TZ) if reference is not None else now_shanghai()
    trading_day = _rollback_to_weekday(current.date())

    if current.date().weekday() < 5 and current.time() < MARKET_CLOSE_TIME:
        trading_day = _rollback_to_weekday(trading_day - timedelta(days=1))

    return trading_day


def _parse_time(value: str) -> time:
    hour_text, minute_text = value.strip().split(":", maxsplit=1)
    return time(hour=int(hour_text), minute=int(minute_text))


def is_trading_session(reference: datetime | None = None, runtime_config: RuntimeConfig | None = None) -> bool:
    current = reference.astimezone(SHANGHAI_TZ) if reference is not None else now_shanghai()
    if current.weekday() >= 5:
        return False

    config = runtime_config or load_runtime_config()
    current_time = current.time()
    am_start = _parse_time(config.intraday_window_am_start)
    am_end = _parse_time(config.intraday_window_am_end)
    pm_start = _parse_time(config.intraday_window_pm_start)
    pm_end = _parse_time(config.intraday_window_pm_end)
    return (am_start <= current_time <= am_end) or (pm_start <= current_time <= pm_end)
