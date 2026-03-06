from __future__ import annotations

from enum import StrEnum


class AnalysisMode(StrEnum):
    EOD = "eod"
    INTRADAY = "intraday"
