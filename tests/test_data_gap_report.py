from __future__ import annotations

import tempfile
import unittest
import zipfile
from datetime import date
from xml.etree import ElementTree

import pandas as pd

from signal_service.data_gap_report import build_data_gap_report_frames, export_data_gap_artifacts


class DataGapReportTests(unittest.TestCase):
    def _conclusion(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "conviction_rank": 1,
                    "symbol": "000300",
                    "display_symbol": "1A0300",
                    "name": "沪深300",
                    "asset_type": "INDEX",
                    "bucket": "宽基指数",
                    "data_status": "PARTIAL",
                    "long_term_action": "MISSING",
                    "short_term_action": "SELL",
                    "preclose_signal": "SELL",
                    "overall_action": "HOLD",
                },
                {
                    "conviction_rank": 2,
                    "symbol": "159611",
                    "display_symbol": "E159611",
                    "name": "电力ETF",
                    "asset_type": "ETF",
                    "bucket": "行业",
                    "data_status": "NO_DATA",
                    "long_term_action": "NO_DATA",
                    "short_term_action": "NO_DATA",
                    "preclose_signal": "HOLD",
                    "overall_action": "NO_DATA",
                },
                {
                    "conviction_rank": 3,
                    "symbol": "510300",
                    "display_symbol": "E510300",
                    "name": "沪深300ETF",
                    "asset_type": "ETF",
                    "bucket": "宽基ETF",
                    "data_status": "OK",
                    "long_term_action": "BUY",
                    "short_term_action": "BUY",
                    "preclose_signal": "BUY",
                    "overall_action": "BUY",
                },
            ]
        )

    def test_build_data_gap_report_frames_summarizes_gap_reasons(self):
        frames = build_data_gap_report_frames(
            conclusion=self._conclusion(),
            signal_date=date(2026, 3, 10),
            signal_dates={"D": date(2026, 3, 10), "W": date(2026, 3, 7), "M": date(2026, 3, 7)},
            intraday_ts=None,
            market_data_by_symbol={
                "000300": pd.DataFrame([{"date": "2026-03-10", "close": 3800.0}] * 120),
                "159611": pd.DataFrame(),
                "510300": pd.DataFrame([{"date": "2026-03-10", "close": 4.56}] * 200),
            },
        )

        data_gaps = frames["Data_Gaps"]
        overview = frames["Overview"]

        self.assertEqual(list(frames.keys()), ["Data_Gaps", "Universe_Status", "Overview"])
        self.assertEqual(len(data_gaps.index), 2)
        partial_row = data_gaps[data_gaps["symbol"] == "000300"].iloc[0]
        no_data_row = data_gaps[data_gaps["symbol"] == "159611"].iloc[0]
        self.assertEqual(partial_row["missing_horizons"], "long_term")
        self.assertEqual(partial_row["reason"], "缺少长线策略信号")
        self.assertEqual(int(partial_row["market_data_rows"]), 120)
        self.assertEqual(no_data_row["missing_horizons"], "long_term,short_term")
        self.assertEqual(no_data_row["reason"], "缺少历史行情")

        counts = overview[overview["section"] == "data_status_count"].set_index("item")["value"].to_dict()
        self.assertEqual(counts["NO_DATA"], "1")
        self.assertEqual(counts["PARTIAL"], "1")
        self.assertEqual(counts["OK"], "1")

    def test_export_data_gap_artifacts_writes_workbook(self):
        frames = build_data_gap_report_frames(
            conclusion=self._conclusion(),
            signal_date=date(2026, 3, 10),
            signal_dates={"D": date(2026, 3, 10), "W": date(2026, 3, 7), "M": date(2026, 3, 7)},
            intraday_ts=None,
            market_data_by_symbol={
                "000300": pd.DataFrame([{"date": "2026-03-10", "close": 3800.0}] * 120),
                "159611": pd.DataFrame(),
                "510300": pd.DataFrame([{"date": "2026-03-10", "close": 4.56}] * 200),
            },
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            exported = export_data_gap_artifacts(
                frames=frames,
                signal_date=date(2026, 3, 10),
                intraday_ts=None,
                signal_dates={"D": date(2026, 3, 10), "W": date(2026, 3, 7), "M": date(2026, 3, 7)},
                output_dir=temp_dir,
            )
            self.assertTrue(exported["csv_path"].exists())
            self.assertTrue(exported["status_csv_path"].exists())
            self.assertTrue(exported["json_path"].exists())
            self.assertTrue(exported["xlsx_path"].exists())
            with zipfile.ZipFile(exported["xlsx_path"], "r") as archive:
                workbook_xml = archive.read("xl/workbook.xml")
            root = ElementTree.fromstring(workbook_xml)
            namespace = {"ns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            sheet_names = [sheet.attrib.get("name", "") for sheet in root.findall("ns:sheets/ns:sheet", namespace)]

        self.assertEqual(sheet_names[0], "Data_Gaps")
        self.assertIn("Overview", sheet_names)
        self.assertIn("Universe_Status", sheet_names)


if __name__ == "__main__":
    unittest.main()
