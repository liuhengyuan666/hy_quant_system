from __future__ import annotations

from typing import Mapping

import pandas as pd

from config.settings import SymbolMeta, load_symbol_meta_map


def enrich_signal_frame_with_symbol_names(
    frame: pd.DataFrame,
    symbol_meta_map: Mapping[str, SymbolMeta] | None = None,
) -> pd.DataFrame:
    if frame.empty:
        table = frame.copy()
        if "name" not in table.columns:
            table["name"] = pd.Series(dtype="string")
        if "display_symbol" not in table.columns:
            table["display_symbol"] = pd.Series(dtype="string")
        return table

    table = frame.copy()
    if "symbol" not in table.columns:
        return table

    table["symbol"] = table["symbol"].astype(str)
    mapping = dict(symbol_meta_map or load_symbol_meta_map())

    def _name_of(symbol: str) -> str:
        meta = mapping.get(symbol)
        if meta is None:
            return symbol
        return meta.name

    def _display_of(symbol: str) -> str:
        meta = mapping.get(symbol)
        if meta is None:
            return symbol
        return meta.display_symbol

    table["name"] = table["symbol"].map(_name_of)
    table["display_symbol"] = table["symbol"].map(_display_of)

    ordered_columns = [
        "date",
        "symbol",
        "display_symbol",
        "name",
        "strategy",
        "signal",
        "score",
        "meta",
    ]
    existing_ordered = [column for column in ordered_columns if column in table.columns]
    remaining_columns = [column for column in table.columns if column not in existing_ordered]
    return table[existing_ordered + remaining_columns]
