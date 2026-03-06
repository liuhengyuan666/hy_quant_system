from __future__ import annotations

from typing import Sequence

import pandas as pd

from config.settings import PostgresConfig, load_universe_config
from data_service.fetch_etf import fetch_etf_batch
from data_service.fetch_index import fetch_index_batch
from data_storage.database import init_database, session_scope
from data_storage.repository import upsert_market_prices


def sync_market_data(
    index_symbols: Sequence[str] | None = None,
    etf_symbols: Sequence[str] | None = None,
    start_date: str = "20050101",
    end_date: str | None = None,
    config: PostgresConfig | None = None,
) -> dict[str, int]:
    universe = load_universe_config()
    selected_indexes = list(index_symbols or universe.index_symbols)
    selected_etfs = list(etf_symbols or universe.etf_symbols)

    index_df = fetch_index_batch(selected_indexes, start_date=start_date, end_date=end_date)
    etf_df = fetch_etf_batch(selected_etfs, start_date=start_date, end_date=end_date)

    frames = [frame for frame in [index_df, etf_df] if not frame.empty]
    if not frames:
        return {"rows": 0, "symbols": 0}

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.sort_values(["symbol", "date"]).reset_index(drop=True)

    init_database(config)
    with session_scope(config) as session:
        written = upsert_market_prices(session, merged.to_dict("records"))

    return {
        "rows": written,
        "symbols": int(merged["symbol"].nunique()),
    }
