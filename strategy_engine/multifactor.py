from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np
import pandas as pd

from strategy_engine.base import CrossSectionalStrategy, Signal, has_minimum_rows


@dataclass
class MultiFactorStrategy(CrossSectionalStrategy):
    lookback_days: int = 20
    weight_momentum: float = 0.35
    weight_trend: float = 0.35
    weight_volume: float = 0.15
    weight_volatility: float = 0.15
    name: str = "MultiFactor_strategy"
    last_scores: dict[str, float] = field(default_factory=dict)

    def _score(self, data: pd.DataFrame) -> float | None:
        if not has_minimum_rows(data, self.lookback_days + 1):
            return None

        frame = data.sort_values("date")
        close = frame["close"].astype(float)
        volume = frame["volume"].astype(float)

        momentum = (close.iloc[-1] / close.iloc[-self.lookback_days - 1]) - 1
        returns = close.pct_change().tail(self.lookback_days)
        volatility = float(returns.std(ddof=0)) if not returns.isna().all() else np.nan

        ma = close.rolling(self.lookback_days).mean().iloc[-1]
        if pd.isna(ma) or ma == 0:
            trend = np.nan
        else:
            trend = (close.iloc[-1] / ma) - 1

        volume_base = volume.tail(self.lookback_days).mean()
        if pd.isna(volume_base) or volume_base == 0:
            volume_factor = np.nan
        else:
            volume_factor = (volume.iloc[-1] / volume_base) - 1

        components = [momentum, trend, volume_factor, volatility]
        if any(pd.isna(value) for value in components):
            return None

        score = (
            (self.weight_momentum * momentum)
            + (self.weight_trend * trend)
            + (self.weight_volume * volume_factor)
            - (self.weight_volatility * volatility)
        )
        return float(score)

    def generate_signals(self, data_by_symbol: Mapping[str, pd.DataFrame]) -> dict[str, Signal]:
        scores: dict[str, float] = {}
        for symbol, data in data_by_symbol.items():
            score = self._score(data)
            if score is not None:
                scores[symbol] = score

        self.last_scores = scores

        result = {symbol: Signal.HOLD for symbol in data_by_symbol.keys()}
        if not scores:
            return result

        winner = max(scores, key=scores.get)
        for symbol in result.keys():
            result[symbol] = Signal.BUY if symbol == winner else Signal.HOLD
        return result
