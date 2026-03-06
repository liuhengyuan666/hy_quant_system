from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from strategy_engine.base import Signal, Strategy, has_minimum_rows


def _rolling_beta(high: pd.Series, low: pd.Series, window: int) -> pd.Series:
    length = len(high)
    beta = np.full(length, np.nan, dtype=float)

    high_values = high.to_numpy(dtype=float)
    low_values = low.to_numpy(dtype=float)

    for idx in range(window - 1, length):
        low_window = low_values[idx - window + 1 : idx + 1]
        high_window = high_values[idx - window + 1 : idx + 1]
        low_mean = low_window.mean()
        high_mean = high_window.mean()
        denominator = np.sum((low_window - low_mean) ** 2)
        if denominator == 0:
            continue
        numerator = np.sum((low_window - low_mean) * (high_window - high_mean))
        beta[idx] = numerator / denominator

    return pd.Series(beta, index=high.index)


@dataclass
class RSRSTimingStrategy(Strategy):
    regression_window: int = 18
    zscore_window: int = 600
    buy_threshold: float = 0.7
    sell_threshold: float = -0.7
    name: str = "RSRS_strategy"

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        min_rows = max(self.regression_window + 1, 60)
        if not has_minimum_rows(data, min_rows):
            return Signal.HOLD

        frame = data.sort_values("date")
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        beta = _rolling_beta(high=high, low=low, window=self.regression_window)

        rolling_mean = beta.rolling(self.zscore_window, min_periods=max(self.regression_window, 30)).mean()
        rolling_std = beta.rolling(self.zscore_window, min_periods=max(self.regression_window, 30)).std(ddof=0)
        zscore = (beta - rolling_mean) / rolling_std.replace(0, np.nan)
        latest = zscore.iloc[-1]

        if pd.isna(latest):
            return Signal.HOLD
        if latest > self.buy_threshold:
            return Signal.BUY
        if latest < self.sell_threshold:
            return Signal.SELL
        return Signal.HOLD
