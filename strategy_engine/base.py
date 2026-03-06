from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Mapping

import pandas as pd


class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class Strategy(ABC):
    name = "base_strategy"

    @abstractmethod
    def generate_signal(self, data: pd.DataFrame) -> Signal:
        raise NotImplementedError


class CrossSectionalStrategy(ABC):
    name = "base_cross_sectional_strategy"

    @abstractmethod
    def generate_signals(self, data_by_symbol: Mapping[str, pd.DataFrame]) -> dict[str, Signal]:
        raise NotImplementedError


def has_minimum_rows(data: pd.DataFrame, rows: int) -> bool:
    return data is not None and not data.empty and len(data.index) >= rows
