from __future__ import annotations

import io
from contextlib import redirect_stdout
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import unittest
from unittest.mock import patch

from main import command_run_preclose_analysis


class MainCommandTests(unittest.TestCase):
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
            command_run_preclose_analysis(use_intraday_snapshot=True)

        mock_run_preclose_analysis_pipeline.assert_called_once_with(signal_ts=current, use_intraday_snapshot=True)
        self.assertEqual(json.loads(output.getvalue()), {"signal_date": "2026-03-09"})

    @patch("scheduler.jobs.run_preclose_analysis_pipeline")
    def test_command_run_preclose_analysis_uses_none_ts_for_post_close_mode(self, mock_run_preclose_analysis_pipeline):
        mock_run_preclose_analysis_pipeline.return_value = {"signal_date": "2026-03-06"}

        output = io.StringIO()
        with redirect_stdout(output):
            command_run_preclose_analysis(use_intraday_snapshot=False)

        mock_run_preclose_analysis_pipeline.assert_called_once_with(signal_ts=None, use_intraday_snapshot=False)
        self.assertEqual(json.loads(output.getvalue()), {"signal_date": "2026-03-06"})


if __name__ == "__main__":
    unittest.main()
