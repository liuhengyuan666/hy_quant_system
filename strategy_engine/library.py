from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

from strategy_engine.base import CrossSectionalStrategy, Signal, Strategy, has_minimum_rows
from strategy_engine.etf_rotation import ETFRotationStrategy
from strategy_engine.ma_trend import MATrendStrategy
from strategy_engine.multifactor import MultiFactorStrategy
from strategy_engine.rsrs_timing import RSRSTimingStrategy


MARKET_HYPOTHESIS_ORDER = (
    "trend_following",
    "mean_reversion",
    "momentum",
    "volatility_breakout",
    "volume_based",
    "cross_asset_allocation",
    "uncategorized",
)

MARKET_HYPOTHESIS_LABELS = {
    "trend_following": "趋势跟随",
    "mean_reversion": "均值回归",
    "momentum": "动量",
    "volatility_breakout": "波动突破",
    "volume_based": "成交量",
    "cross_asset_allocation": "资产配置",
    "uncategorized": "未分类",
}


def _to_float_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype(float)


def _compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    up_move = _to_float_series(high.diff())
    down_move = _to_float_series(-low.diff())

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    atr = _compute_atr(high=high, low=low, close=close, period=period)
    plus_di = 100 * (plus_dm.rolling(period).sum() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(period).sum() / atr.replace(0, np.nan))
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    adx = dx.rolling(period).mean()
    return adx, plus_di, minus_di


@dataclass
class EMACrossStrategy(Strategy):
    fast_window: int = 12
    slow_window: int = 26
    name: str = "EMA_cross_strategy"

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        if not has_minimum_rows(data, self.slow_window + 5):
            return Signal.HOLD

        close = _to_float_series(data["close"])
        fast_ema = close.ewm(span=self.fast_window, adjust=False).mean().iloc[-1]
        slow_ema = close.ewm(span=self.slow_window, adjust=False).mean().iloc[-1]

        if pd.isna(fast_ema) or pd.isna(slow_ema):
            return Signal.HOLD
        if fast_ema > slow_ema:
            return Signal.BUY
        if fast_ema < slow_ema:
            return Signal.SELL
        return Signal.HOLD


@dataclass
class TripleMAStrategy(Strategy):
    short_window: int = 10
    mid_window: int = 20
    long_window: int = 60
    name: str = "Triple_MA_strategy"

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        if not has_minimum_rows(data, self.long_window + 2):
            return Signal.HOLD

        close = _to_float_series(data["close"])
        short_ma = close.rolling(self.short_window).mean().iloc[-1]
        mid_ma = close.rolling(self.mid_window).mean().iloc[-1]
        long_ma = close.rolling(self.long_window).mean().iloc[-1]

        if pd.isna(short_ma) or pd.isna(mid_ma) or pd.isna(long_ma):
            return Signal.HOLD
        if short_ma > mid_ma > long_ma:
            return Signal.BUY
        if short_ma < mid_ma < long_ma:
            return Signal.SELL
        return Signal.HOLD


@dataclass
class MACDHistogramStrategy(Strategy):
    fast: int = 12
    slow: int = 26
    signal_period: int = 9
    name: str = "MACD_hist_strategy"

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        if not has_minimum_rows(data, self.slow + self.signal_period + 5):
            return Signal.HOLD

        close = _to_float_series(data["close"])
        ema_fast = close.ewm(span=self.fast, adjust=False).mean()
        ema_slow = close.ewm(span=self.slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal = macd.ewm(span=self.signal_period, adjust=False).mean()
        hist = macd - signal

        latest_hist = hist.iloc[-1]
        latest_macd = macd.iloc[-1]
        latest_signal = signal.iloc[-1]

        if pd.isna(latest_hist) or pd.isna(latest_macd) or pd.isna(latest_signal):
            return Signal.HOLD
        if latest_hist > 0 and latest_macd > latest_signal:
            return Signal.BUY
        if latest_hist < 0 and latest_macd < latest_signal:
            return Signal.SELL
        return Signal.HOLD


@dataclass
class RSIReversionStrategy(Strategy):
    period: int = 14
    oversold: float = 30.0
    overbought: float = 70.0
    name: str = "RSI_reversion_strategy"

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        if not has_minimum_rows(data, self.period + 5):
            return Signal.HOLD

        close = _to_float_series(data["close"])
        rsi = _compute_rsi(close=close, period=self.period).iloc[-1]
        if pd.isna(rsi):
            return Signal.HOLD
        if rsi <= self.oversold:
            return Signal.BUY
        if rsi >= self.overbought:
            return Signal.SELL
        return Signal.HOLD


@dataclass
class BollingerBreakoutStrategy(Strategy):
    period: int = 20
    std_factor: float = 2.0
    name: str = "Bollinger_breakout_strategy"

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        if not has_minimum_rows(data, self.period + 2):
            return Signal.HOLD

        close = _to_float_series(data["close"])
        middle = close.rolling(self.period).mean()
        std = close.rolling(self.period).std(ddof=0)
        upper = middle + (self.std_factor * std)
        lower = middle - (self.std_factor * std)

        latest_close = close.iloc[-1]
        latest_upper = upper.iloc[-1]
        latest_lower = lower.iloc[-1]

        if pd.isna(latest_close) or pd.isna(latest_upper) or pd.isna(latest_lower):
            return Signal.HOLD
        if latest_close > latest_upper:
            return Signal.BUY
        if latest_close < latest_lower:
            return Signal.SELL
        return Signal.HOLD


@dataclass
class BollingerReversionStrategy(Strategy):
    period: int = 20
    std_factor: float = 2.0
    name: str = "Bollinger_reversion_strategy"

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        if not has_minimum_rows(data, self.period + 2):
            return Signal.HOLD

        close = _to_float_series(data["close"])
        middle = close.rolling(self.period).mean()
        std = close.rolling(self.period).std(ddof=0)
        upper = middle + (self.std_factor * std)
        lower = middle - (self.std_factor * std)

        latest_close = close.iloc[-1]
        latest_upper = upper.iloc[-1]
        latest_lower = lower.iloc[-1]

        if pd.isna(latest_close) or pd.isna(latest_upper) or pd.isna(latest_lower):
            return Signal.HOLD
        if latest_close < latest_lower:
            return Signal.BUY
        if latest_close > latest_upper:
            return Signal.SELL
        return Signal.HOLD


@dataclass
class DonchianBreakoutStrategy(Strategy):
    period: int = 20
    name: str = "Donchian_breakout_strategy"

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        if not has_minimum_rows(data, self.period + 2):
            return Signal.HOLD

        frame = data.sort_values("date")
        high = _to_float_series(frame["high"])
        low = _to_float_series(frame["low"])
        close = _to_float_series(frame["close"])

        upper = high.rolling(self.period).max().shift(1)
        lower = low.rolling(self.period).min().shift(1)

        latest_close = close.iloc[-1]
        latest_upper = upper.iloc[-1]
        latest_lower = lower.iloc[-1]

        if pd.isna(latest_close) or pd.isna(latest_upper) or pd.isna(latest_lower):
            return Signal.HOLD
        if latest_close > latest_upper:
            return Signal.BUY
        if latest_close < latest_lower:
            return Signal.SELL
        return Signal.HOLD


@dataclass
class MomentumStrategy(Strategy):
    lookback_days: int = 20
    threshold: float = 0.03
    name: str = "Momentum_20_strategy"

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        if not has_minimum_rows(data, self.lookback_days + 1):
            return Signal.HOLD

        close = _to_float_series(data.sort_values("date")["close"])
        latest = close.iloc[-1]
        past = close.iloc[-self.lookback_days - 1]
        if pd.isna(latest) or pd.isna(past) or past == 0:
            return Signal.HOLD

        momentum = (latest / past) - 1
        if momentum > self.threshold:
            return Signal.BUY
        if momentum < -self.threshold:
            return Signal.SELL
        return Signal.HOLD


@dataclass
class ROCStrategy(Strategy):
    period: int = 20
    buy_threshold: float = 0.05
    sell_threshold: float = -0.05
    name: str = "ROC_20_strategy"

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        if not has_minimum_rows(data, self.period + 2):
            return Signal.HOLD

        close = _to_float_series(data.sort_values("date")["close"])
        roc = close.pct_change(periods=self.period).iloc[-1]
        if pd.isna(roc):
            return Signal.HOLD
        if roc > self.buy_threshold:
            return Signal.BUY
        if roc < self.sell_threshold:
            return Signal.SELL
        return Signal.HOLD


@dataclass
class VolatilityBreakoutStrategy(Strategy):
    period: int = 20
    multiplier: float = 1.3
    name: str = "Volatility_breakout_strategy"

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        if not has_minimum_rows(data, self.period + 3):
            return Signal.HOLD

        frame = data.sort_values("date")
        close = _to_float_series(frame["close"])
        returns = close.pct_change()
        vol = returns.rolling(self.period).std(ddof=0)

        latest_move = close.iloc[-1] - close.iloc[-2]
        trigger = close.iloc[-2] * vol.iloc[-2] * self.multiplier
        if pd.isna(trigger):
            return Signal.HOLD
        if latest_move > trigger:
            return Signal.BUY
        if latest_move < -trigger:
            return Signal.SELL
        return Signal.HOLD


@dataclass
class ATRChannelStrategy(Strategy):
    atr_period: int = 14
    mid_period: int = 20
    multiplier: float = 1.5
    name: str = "ATR_channel_strategy"

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        min_rows = max(self.atr_period, self.mid_period) + 3
        if not has_minimum_rows(data, min_rows):
            return Signal.HOLD

        frame = data.sort_values("date")
        high = _to_float_series(frame["high"])
        low = _to_float_series(frame["low"])
        close = _to_float_series(frame["close"])

        atr = _compute_atr(high=high, low=low, close=close, period=self.atr_period)
        mid = close.rolling(self.mid_period).mean()
        upper = mid + (self.multiplier * atr)
        lower = mid - (self.multiplier * atr)

        latest_close = close.iloc[-1]
        latest_upper = upper.iloc[-1]
        latest_lower = lower.iloc[-1]
        if pd.isna(latest_close) or pd.isna(latest_upper) or pd.isna(latest_lower):
            return Signal.HOLD
        if latest_close > latest_upper:
            return Signal.BUY
        if latest_close < latest_lower:
            return Signal.SELL
        return Signal.HOLD


@dataclass
class KDJCrossStrategy(Strategy):
    period: int = 9
    name: str = "KDJ_cross_strategy"

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        if not has_minimum_rows(data, self.period + 5):
            return Signal.HOLD

        frame = data.sort_values("date")
        high = _to_float_series(frame["high"])
        low = _to_float_series(frame["low"])
        close = _to_float_series(frame["close"])

        lowest = low.rolling(self.period).min()
        highest = high.rolling(self.period).max()
        rsv = ((close - lowest) / (highest - lowest).replace(0, np.nan)) * 100
        k = rsv.ewm(com=2, adjust=False).mean()
        d = k.ewm(com=2, adjust=False).mean()
        j = (3 * k) - (2 * d)

        latest_k = k.iloc[-1]
        latest_d = d.iloc[-1]
        latest_j = j.iloc[-1]
        if pd.isna(latest_k) or pd.isna(latest_d) or pd.isna(latest_j):
            return Signal.HOLD
        if latest_k > latest_d and latest_j < 80:
            return Signal.BUY
        if latest_k < latest_d and latest_j > 20:
            return Signal.SELL
        return Signal.HOLD


@dataclass
class CCIReversionStrategy(Strategy):
    period: int = 20
    lower: float = -100.0
    upper: float = 100.0
    name: str = "CCI_reversion_strategy"

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        if not has_minimum_rows(data, self.period + 5):
            return Signal.HOLD

        frame = data.sort_values("date")
        high = _to_float_series(frame["high"])
        low = _to_float_series(frame["low"])
        close = _to_float_series(frame["close"])

        typical_price = (high + low + close) / 3.0
        moving_avg = typical_price.rolling(self.period).mean()
        mean_dev = (typical_price - moving_avg).abs().rolling(self.period).mean()
        cci = (typical_price - moving_avg) / (0.015 * mean_dev.replace(0, np.nan))
        latest = cci.iloc[-1]

        if pd.isna(latest):
            return Signal.HOLD
        if latest <= self.lower:
            return Signal.BUY
        if latest >= self.upper:
            return Signal.SELL
        return Signal.HOLD


@dataclass
class OBVTrendStrategy(Strategy):
    period: int = 20
    name: str = "OBV_trend_strategy"

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        if not has_minimum_rows(data, self.period + 5):
            return Signal.HOLD

        frame = data.sort_values("date")
        close = _to_float_series(frame["close"])
        volume = _to_float_series(frame["volume"]).fillna(0.0)

        direction = close.diff().fillna(0.0).apply(np.sign)
        obv = (direction * volume).cumsum()
        obv_ma = obv.rolling(self.period).mean()
        close_ma = close.rolling(self.period).mean()

        latest_obv = obv.iloc[-1]
        latest_obv_ma = obv_ma.iloc[-1]
        latest_close = close.iloc[-1]
        latest_close_ma = close_ma.iloc[-1]

        if pd.isna(latest_obv) or pd.isna(latest_obv_ma) or pd.isna(latest_close) or pd.isna(latest_close_ma):
            return Signal.HOLD
        if latest_obv > latest_obv_ma and latest_close > latest_close_ma:
            return Signal.BUY
        if latest_obv < latest_obv_ma and latest_close < latest_close_ma:
            return Signal.SELL
        return Signal.HOLD


@dataclass
class ADXTrendStrategy(Strategy):
    period: int = 14
    threshold: float = 25.0
    name: str = "ADX_trend_strategy"

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        if not has_minimum_rows(data, self.period * 3):
            return Signal.HOLD

        frame = data.sort_values("date")
        high = _to_float_series(frame["high"])
        low = _to_float_series(frame["low"])
        close = _to_float_series(frame["close"])

        adx, plus_di, minus_di = _compute_adx(high=high, low=low, close=close, period=self.period)

        latest_adx = adx.iloc[-1]
        latest_plus = plus_di.iloc[-1]
        latest_minus = minus_di.iloc[-1]

        if pd.isna(latest_adx) or pd.isna(latest_plus) or pd.isna(latest_minus):
            return Signal.HOLD
        if latest_adx >= self.threshold and latest_plus > latest_minus:
            return Signal.BUY
        if latest_adx >= self.threshold and latest_plus < latest_minus:
            return Signal.SELL
        return Signal.HOLD


@dataclass(frozen=True)
class StrategySpec:
    name: str
    mode: str
    universe: str
    engine: Strategy | CrossSectionalStrategy
    supported_modes: tuple[str, ...] = ("eod",)
    profile: str = "standard"
    horizon: str = "short_term"
    report_weight: float = 1.0
    market_hypothesis: str = "uncategorized"


def build_strategy_specs() -> list[StrategySpec]:
    return [
        StrategySpec(name="MA_strategy", mode="single", universe="all", engine=MATrendStrategy(), supported_modes=("eod", "intraday"), profile="light", horizon="short_term", market_hypothesis="trend_following"),
        StrategySpec(name="RSRS_strategy", mode="single", universe="all", engine=RSRSTimingStrategy(), horizon="long_term", market_hypothesis="trend_following"),
        StrategySpec(name="EMA_cross_strategy", mode="single", universe="all", engine=EMACrossStrategy(), supported_modes=("eod", "intraday"), profile="light", horizon="short_term", market_hypothesis="trend_following"),
        StrategySpec(name="Triple_MA_strategy", mode="single", universe="all", engine=TripleMAStrategy(), horizon="long_term", market_hypothesis="trend_following"),
        StrategySpec(name="MACD_hist_strategy", mode="single", universe="all", engine=MACDHistogramStrategy(), supported_modes=("eod", "intraday"), profile="light", horizon="short_term", market_hypothesis="momentum"),
        StrategySpec(name="RSI_reversion_strategy", mode="single", universe="all", engine=RSIReversionStrategy(), supported_modes=("eod", "intraday"), profile="light", horizon="short_term", market_hypothesis="mean_reversion"),
        StrategySpec(name="Bollinger_breakout_strategy", mode="single", universe="all", engine=BollingerBreakoutStrategy(), supported_modes=("eod", "intraday"), profile="light", horizon="short_term", market_hypothesis="volatility_breakout"),
        StrategySpec(name="Bollinger_reversion_strategy", mode="single", universe="all", engine=BollingerReversionStrategy(), horizon="short_term", market_hypothesis="mean_reversion"),
        StrategySpec(name="Donchian_breakout_strategy", mode="single", universe="all", engine=DonchianBreakoutStrategy(), supported_modes=("eod", "intraday"), profile="light", horizon="short_term", market_hypothesis="volatility_breakout"),
        StrategySpec(
            name="Momentum_20_strategy",
            mode="single",
            universe="all",
            engine=MomentumStrategy(lookback_days=20, threshold=0.03, name="Momentum_20_strategy"),
            supported_modes=("eod", "intraday"),
            profile="light",
            horizon="short_term",
            market_hypothesis="momentum",
        ),
        StrategySpec(
            name="Momentum_60_strategy",
            mode="single",
            universe="all",
            engine=MomentumStrategy(lookback_days=60, threshold=0.08, name="Momentum_60_strategy"),
            horizon="long_term",
            market_hypothesis="momentum",
        ),
        StrategySpec(name="ROC_20_strategy", mode="single", universe="all", engine=ROCStrategy(), supported_modes=("eod", "intraday"), profile="light", horizon="short_term", market_hypothesis="momentum"),
        StrategySpec(name="Volatility_breakout_strategy", mode="single", universe="all", engine=VolatilityBreakoutStrategy(), supported_modes=("eod", "intraday"), profile="light", horizon="short_term", market_hypothesis="volatility_breakout"),
        StrategySpec(name="ATR_channel_strategy", mode="single", universe="all", engine=ATRChannelStrategy(), horizon="long_term", market_hypothesis="volatility_breakout"),
        StrategySpec(name="KDJ_cross_strategy", mode="single", universe="all", engine=KDJCrossStrategy(), supported_modes=("eod", "intraday"), profile="light", horizon="short_term", market_hypothesis="mean_reversion"),
        StrategySpec(name="CCI_reversion_strategy", mode="single", universe="all", engine=CCIReversionStrategy(), horizon="short_term", market_hypothesis="mean_reversion"),
        StrategySpec(name="OBV_trend_strategy", mode="single", universe="all", engine=OBVTrendStrategy(), supported_modes=("eod", "intraday"), profile="light", horizon="long_term", market_hypothesis="volume_based"),
        StrategySpec(name="ADX_trend_strategy", mode="single", universe="all", engine=ADXTrendStrategy(), horizon="long_term", market_hypothesis="trend_following"),
        StrategySpec(name="ETF_rotation_strategy", mode="cross", universe="etf", engine=ETFRotationStrategy(), horizon="long_term", report_weight=1.2, market_hypothesis="cross_asset_allocation"),
        StrategySpec(name="MultiFactor_strategy", mode="cross", universe="etf", engine=MultiFactorStrategy(), horizon="long_term", report_weight=1.2, market_hypothesis="cross_asset_allocation"),
    ]


def list_strategy_names() -> list[str]:
    return [item.name for item in build_strategy_specs()]


def list_strategy_names_by_mode(supported_mode: str) -> list[str]:
    return [item.name for item in build_strategy_specs() if supported_mode in item.supported_modes]


def list_strategy_names_by_horizon(horizon: str) -> list[str]:
    return [item.name for item in build_strategy_specs() if item.horizon == horizon]


def list_strategy_names_by_hypothesis(market_hypothesis: str) -> list[str]:
    return [item.name for item in build_strategy_specs() if item.market_hypothesis == market_hypothesis]


def market_hypothesis_label(market_hypothesis: str) -> str:
    return MARKET_HYPOTHESIS_LABELS.get(market_hypothesis, MARKET_HYPOTHESIS_LABELS["uncategorized"])


def resolve_strategy_specs(
    selected_names: Sequence[str] | None = None,
    supported_mode: str | None = None,
    horizon: str | None = None,
) -> list[StrategySpec]:
    specs = build_strategy_specs()
    if supported_mode is not None:
        specs = [item for item in specs if supported_mode in item.supported_modes]
    if horizon is not None:
        specs = [item for item in specs if item.horizon == horizon]
    if selected_names is None:
        return specs

    selected = [name.strip() for name in selected_names if name.strip()]
    if not selected:
        return specs

    by_name = {item.name: item for item in specs}
    unknown = [name for name in selected if name not in by_name]
    if unknown:
        raise ValueError(f"unknown strategies: {unknown}")

    return [by_name[name] for name in selected]
