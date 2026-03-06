from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from scheduler.jobs import run_eod_and_analyze_pipeline


class SchedulerJobsTests(unittest.TestCase):
    @patch("scheduler.jobs.resolve_summary_artifact_paths")
    @patch("scheduler.jobs.export_signal_summary")
    @patch("scheduler.jobs.secondary_validate_signals_csv")
    @patch("scheduler.jobs.analyze_signals_csv")
    @patch("scheduler.jobs.run_eod_pipeline")
    def test_run_eod_and_analyze_pipeline_includes_secondary_validation(
        self,
        mock_run_eod_pipeline,
        mock_analyze,
        mock_secondary,
        mock_export_summary,
        mock_resolve_artifacts,
    ):
        mock_run_eod_pipeline.return_value = {
            "market_rows": 10,
            "indicator_rows": 20,
            "signal_counts": {"D": 2, "W": 2, "M": 2},
            "export_paths": [
                "reports/eod/signals_d_20260309.csv",
                "reports/eod/signals_w_20260309.csv",
            ],
        }
        mock_analyze.side_effect = lambda path: {"source": Path(path).stem}
        mock_secondary.side_effect = lambda path: {"gate": Path(path).stem}
        mock_export_summary.return_value = Path("reports/summary/signal_summary_20260309.csv")
        mock_resolve_artifacts.return_value = {
            "summary_path": Path("reports/summary/signal_summary_20260309.csv"),
            "group_summary_path": Path("reports/summary/signal_group_summary_20260309.csv"),
            "top_candidates_path": Path("reports/summary/signal_top_candidates_20260309.csv"),
            "push_candidates_path": Path("reports/summary/signal_push_candidates_20260309.csv"),
        }

        result = run_eod_and_analyze_pipeline(bar_frequencies=("D", "W"))

        self.assertIn("analysis", result)
        self.assertIn("secondary_validation", result)
        self.assertEqual(result["analysis"]["D"]["source"], "signals_d_20260309")
        self.assertEqual(result["secondary_validation"]["W"]["gate"], "signals_w_20260309")
        self.assertEqual(Path(result["summary_path"]), Path("reports/summary/signal_summary_20260309.csv"))
        self.assertEqual(Path(result["push_path"]), Path("reports/summary/signal_push_candidates_20260309.csv"))


if __name__ == "__main__":
    unittest.main()
