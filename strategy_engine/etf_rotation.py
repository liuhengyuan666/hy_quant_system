from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import pandas as pd

from strategy_engine.base import CrossSectionalStrategy, Signal, has_minimum_rows


@dataclass
class ETFRotationStrategy(CrossSectionalStrategy):
    lookback_days: int = 20
    name: str = "ETF_rotation_strategy"
    last_momentum: dict[str, float] = field(default_factory=dict)

    def _momentum(self, data: pd.DataFrame) -> float | None:
        if not has_minimum_rows(data, self.lookback_days + 1):
            return None
        close = data.sort_values("date")["close"].astype(float)
        past = close.iloc[-self.lookback_days - 1]
        latest = close.iloc[-1]
        if past == 0:
            return None
        return (latest / past) - 1

    def generate_signals(self, data_by_symbol: Mapping[str, pd.DataFrame]) -> dict[str, Signal]:
        momentum_map: dict[str, float] = {}
        for symbol, data in data_by_symbol.items():
            score = self._momentum(data)
            if score is not None:
                momentum_map[symbol] = score

        self.last_momentum = momentum_map

        result = {symbol: Signal.HOLD for symbol in data_by_symbol.keys()}
        if not momentum_map:
            return result

        winner = max(momentum_map, key=momentum_map.get)
        for symbol in result.keys():
            result[symbol] = Signal.BUY if symbol == winner else Signal.SELL
        return result
