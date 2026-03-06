from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

try:
    import pandas as pd
except Exception:
    pd = None

try:
    from signal_service.analysis import analyze_signals_csv, analyze_signals_dataframe
except Exception:
    analyze_signals_dataframe = None
    analyze_signals_csv = None


@unittest.skipIf(
    pd is None or analyze_signals_dataframe is None or analyze_signals_csv is None,
    "runtime dependencies unavailable",
)
class SignalAnalysisTests(unittest.TestCase):
    def test_analysis_counts_and_rank(self):
        frame = pd.DataFrame(
            [
                {"date": "2026-03-06", "symbol": "000300", "strategy": "MA_strategy", "signal": "BUY"},
                {"date": "2026-03-06", "symbol": "000300", "strategy": "RSRS_strategy", "signal": "SELL"},
                {"date": "2026-03-06", "symbol": "000905", "strategy": "MA_strategy", "signal": "BUY"},
                {"date": "2026-03-06", "symbol": "000905", "strategy": "RSRS_strategy", "signal": "HOLD"},
                {"date": "2026-03-06", "symbol": "000001", "strategy": "MA_strategy", "signal": "BUY"},
                {"date": "2026-03-06", "symbol": "000001", "strategy": "RSRS_strategy", "signal": "BUY"},
            ]
        )

        output = analyze_signals_dataframe(frame)
        self.assertEqual(output["total_signals"], 6)
        self.assertEqual(output["signal_counts"], {"BUY": 4, "SELL": 1, "HOLD": 1})
        self.assertEqual(output["top_buy_symbols"][0], "000001")
        self.assertIn("000300", output["top_sell_symbols"])

    def test_empty_frame(self):
        frame = pd.DataFrame(columns=["date", "symbol", "strategy", "signal"])
        output = analyze_signals_dataframe(frame)
        self.assertEqual(output["total_signals"], 0)
        self.assertEqual(output["strategy_summary"], [])

    def test_csv_keeps_symbol_leading_zero(self):
        rows = [
            "date,symbol,strategy,signal,score,meta",
            "2026-03-07,000905,MA_strategy,BUY,,",
            "2026-03-07,000905,RSRS_strategy,HOLD,,",
            "2026-03-07,000001,MA_strategy,SELL,,",
        ]
        content = "\n".join(rows)

        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "signals_test.csv"
            file_path.write_text(content, encoding="utf-8")
            output = analyze_signals_csv(file_path)

        self.assertIn("000905", output["top_buy_symbols"])
        self.assertNotIn("905", output["top_buy_symbols"])


if __name__ == "__main__":
    unittest.main()
