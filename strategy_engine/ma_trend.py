from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from strategy_engine.base import Signal, Strategy, has_minimum_rows


@dataclass
class MATrendStrategy(Strategy):
    fast_window: int = 20
    slow_window: int = 60
    name: str = "MA_strategy"

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        if not has_minimum_rows(data, self.slow_window):
            return Signal.HOLD

        close = data["close"].astype(float)
        fast_ma = close.rolling(self.fast_window).mean().iloc[-1]
        slow_ma = close.rolling(self.slow_window).mean().iloc[-1]

        if pd.isna(fast_ma) or pd.isna(slow_ma):
            return Signal.HOLD
        if fast_ma > slow_ma:
            return Signal.BUY
        if fast_ma < slow_ma:
            return Signal.SELL
        return Signal.HOLD
