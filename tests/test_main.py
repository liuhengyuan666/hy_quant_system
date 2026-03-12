from __future__ import annotations

import io
from contextlib import redirect_stdout
from datetime import date, datetime
from zoneinfo import ZoneInfo
import json
import unittest
from unittest.mock import patch

from main import (
    _parse_signal_date,
    _resolve_report_reference,
    command_export_daily_conclusion,
    command_export_data_gaps,
    command_export_strategy_matrix,
    command_run_preclose_analysis,
)


class MainCommandTests(unittest.TestCase):
    def test_parse_signal_date_supports_compact_and_iso(self):
        self.assertEqual(_parse_signal_date("20260311"), date(2026, 3, 11))
        self.assertEqual(_parse_signal_date("2026-03-11"), date(2026, 3, 11))

    @patch("core.trading_calendar.latest_closed_trading_date")
    @patch("core.trading_calendar.is_trading_session")
    @patch("core.clock.now_shanghai")
    def test_resolve_report_reference_uses_realtime_when_session_open(
        self,
        mock_now_shanghai,
        mock_is_trading_session,
        mock_latest_closed_trading_date,
    ):
        current = datetime(2026, 3, 11, 14, 11, tzinfo=ZoneInfo("Asia/Shanghai"))
        mock_now_shanghai.return_value = current
        mock_is_trading_session.return_value = True
        mock_latest_closed_trading_date.return_value = date(2026, 3, 10)

        signal_date, intraday_ts = _resolve_report_reference(None)

        self.assertEqual(signal_date, date(2026, 3, 11))
        self.assertEqual(intraday_ts, current)

    @patch("core.trading_calendar.latest_closed_trading_date")
    @patch("core.trading_calendar.is_trading_session")
    @patch("core.clock.now_shanghai")
    def test_resolve_report_reference_uses_latest_closed_day_when_session_closed(
        self,
        mock_now_shanghai,
        mock_is_trading_session,
        mock_latest_closed_trading_date,
    ):
        current = datetime(2026, 3, 11, 16, 5, tzinfo=ZoneInfo("Asia/Shanghai"))
        mock_now_shanghai.return_value = current
        mock_is_trading_session.return_value = False
        mock_latest_closed_trading_date.return_value = date(2026, 3, 11)

        signal_date, intraday_ts = _resolve_report_reference(None)

        self.assertEqual(signal_date, date(2026, 3, 11))
        self.assertIsNone(intraday_ts)

    @patch("core.clock.now_shanghai")
    @patch("scheduler.jobs.run_preclose_analysis_pipeline")
    def test_command_run_preclose_analysis_passes_current_ts_for_intraday_snapshot(
        self,
        mock_run_preclose_analysis_pipeline,
        mock_now_shanghai,
    ):
        current = datetime(2026, 3, 9, 14, 50, tzinfo=ZoneInfo("Asia/Shanghai"))
        mock_now_shanghai.return_value = current
        mock_run_preclose_analysis_pipeline.return_value = {"signal_date": "2026-03-09"}

        output = io.StringIO()
        with redirect_stdout(output):
            command_run_preclose_analysis(use_intraday_snapshot=True, signal_date_text=None)

        mock_run_preclose_analysis_pipeline.assert_called_once_with(signal_ts=current, signal_date=None, use_intraday_snapshot=True)
        self.assertEqual(json.loads(output.getvalue()), {"signal_date": "2026-03-09"})

    @patch("main._resolve_report_reference")
    @patch("scheduler.jobs.run_preclose_analysis_pipeline")
    def test_command_run_preclose_analysis_uses_none_ts_for_post_close_mode(self, mock_run_preclose_analysis_pipeline, mock_resolve_report_reference):
        mock_run_preclose_analysis_pipeline.return_value = {"signal_date": "2026-03-06"}
        mock_resolve_report_reference.return_value = (date(2026, 3, 6), None)

        output = io.StringIO()
        with redirect_stdout(output):
            command_run_preclose_analysis(use_intraday_snapshot=False, signal_date_text=None)

        mock_run_preclose_analysis_pipeline.assert_called_once_with(signal_ts=None, signal_date=date(2026, 3, 6), use_intraday_snapshot=False)
        self.assertEqual(json.loads(output.getvalue()), {"signal_date": "2026-03-06"})

    @patch("scheduler.jobs.run_preclose_analysis_pipeline")
    def test_command_run_preclose_analysis_passes_explicit_signal_date(self, mock_run_preclose_analysis_pipeline):
        mock_run_preclose_analysis_pipeline.return_value = {"signal_date": "2026-03-11"}

        output = io.StringIO()
        with redirect_stdout(output):
            command_run_preclose_analysis(use_intraday_snapshot=False, signal_date_text="20260311")

        mock_run_preclose_analysis_pipeline.assert_called_once_with(signal_ts=None, signal_date=date(2026, 3, 11), use_intraday_snapshot=False)
        self.assertEqual(json.loads(output.getvalue()), {"signal_date": "2026-03-11"})

    @patch("core.trading_calendar.latest_closed_trading_date")
    @patch("core.clock.now_shanghai")
    def test_resolve_report_reference_clamps_future_requested_date_to_latest_closed_day(self, mock_now_shanghai, mock_latest_closed_trading_date):
        current = datetime(2026, 3, 12, 14, 11, tzinfo=ZoneInfo("Asia/Shanghai"))
        mock_now_shanghai.return_value = current
        mock_latest_closed_trading_date.return_value = date(2026, 3, 11)

        signal_date, intraday_ts = _resolve_report_reference("20260312")

        self.assertEqual(signal_date, date(2026, 3, 11))
        self.assertIsNone(intraday_ts)

    def test_command_run_preclose_analysis_rejects_signal_date_with_intraday_snapshot(self):
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            command_run_preclose_analysis(use_intraday_snapshot=True, signal_date_text="20260311")

    @patch("scheduler.jobs.export_daily_conclusion_report_pipeline")
    def test_command_export_daily_conclusion_passes_signal_date(self, mock_pipeline):
        mock_pipeline.return_value = {"signal_date": "2026-03-11"}

        output = io.StringIO()
        with redirect_stdout(output):
            command_export_daily_conclusion(signal_date_text="20260311")

        mock_pipeline.assert_called_once_with(signal_date=date(2026, 3, 11), intraday_ts=None)
        self.assertEqual(json.loads(output.getvalue()), {"signal_date": "2026-03-11"})

    @patch("main._resolve_report_reference")
    @patch("scheduler.jobs.export_strategy_matrix_report_pipeline")
    def test_command_export_strategy_matrix_uses_realtime_reference_by_default(self, mock_pipeline, mock_resolve_report_reference):
        current = datetime(2026, 3, 11, 14, 11, tzinfo=ZoneInfo("Asia/Shanghai"))
        mock_resolve_report_reference.return_value = (date(2026, 3, 11), current)
        mock_pipeline.return_value = {"signal_date": "2026-03-11", "intraday_ts": current.isoformat()}

        output = io.StringIO()
        with redirect_stdout(output):
            command_export_strategy_matrix(signal_date_text=None)

        mock_pipeline.assert_called_once_with(signal_date=date(2026, 3, 11), intraday_ts=current)
        self.assertEqual(json.loads(output.getvalue())["signal_date"], "2026-03-11")

    @patch("main._resolve_report_reference")
    @patch("scheduler.jobs.export_data_gap_report_pipeline")
    def test_command_export_data_gaps_uses_latest_closed_day_by_default(self, mock_pipeline, mock_resolve_report_reference):
        mock_resolve_report_reference.return_value = (date(2026, 3, 10), None)
        mock_pipeline.return_value = {"signal_date": "2026-03-10"}

        output = io.StringIO()
        with redirect_stdout(output):
            command_export_data_gaps(signal_date_text=None)

        mock_pipeline.assert_called_once_with(signal_date=date(2026, 3, 10), intraday_ts=None)
        self.assertEqual(json.loads(output.getvalue()), {"signal_date": "2026-03-10"})


if __name__ == "__main__":
    unittest.main()
