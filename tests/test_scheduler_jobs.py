from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from scheduler.jobs import export_daily_conclusion_report_pipeline, export_data_gap_report_pipeline, export_strategy_matrix_report_pipeline, run_eod_and_analyze_pipeline


class SchedulerJobsTests(unittest.TestCase):
    @patch("scheduler.jobs.export_daily_conclusion_report")
    @patch("scheduler.jobs.export_data_gap_report")
    @patch("scheduler.jobs.export_strategy_matrix_report")
    @patch("scheduler.jobs.run_preclose_analysis")
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
        mock_run_preclose,
        mock_strategy_matrix,
        mock_data_gap,
        mock_daily_conclusion,
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
        mock_run_preclose.return_value = {
            "csv_path": "reports/preclose/preclose_decision_post_close_20260309.csv",
            "json_path": "reports/preclose/preclose_decision_post_close_20260309.json",
        }
        mock_daily_conclusion.return_value = {
            "csv_path": "reports/daily_conclusion/daily_conclusion_20260309.csv",
            "operation_csv_path": "reports/daily_conclusion/daily_conclusion_operation_20260309.csv",
            "json_path": "reports/daily_conclusion/daily_conclusion_20260309.json",
            "xlsx_path": "reports/daily_conclusion/daily_conclusion_20260309.xlsx",
        }
        mock_data_gap.return_value = {
            "csv_path": "reports/data_gaps/data_gaps_20260309.csv",
            "xlsx_path": "reports/data_gaps/data_gaps_20260309.xlsx",
        }
        mock_strategy_matrix.return_value = {
            "xlsx_path": "reports/strategy_matrix/strategy_matrix_20260309.xlsx",
        }

        result = run_eod_and_analyze_pipeline(bar_frequencies=("D", "W"))
        self.assertIsInstance(result, dict)
        analysis = result.get("analysis")
        secondary_validation = result.get("secondary_validation")
        self.assertIsInstance(analysis, dict)
        self.assertIsInstance(secondary_validation, dict)
        if not isinstance(analysis, dict):
            self.fail("analysis should be a dict")
        if not isinstance(secondary_validation, dict):
            self.fail("secondary_validation should be a dict")
        analysis_d = analysis.get("D")
        secondary_w = secondary_validation.get("W")
        self.assertIsInstance(analysis_d, dict)
        self.assertIsInstance(secondary_w, dict)
        if not isinstance(analysis_d, dict):
            self.fail("analysis['D'] should be a dict")
        if not isinstance(secondary_w, dict):
            self.fail("secondary_validation['W'] should be a dict")
        source = analysis_d.get("source")
        gate = secondary_w.get("gate")

        self.assertIn("analysis", result)
        self.assertIn("secondary_validation", result)
        self.assertEqual(str(source), "signals_d_20260309")
        self.assertEqual(str(gate), "signals_w_20260309")
        self.assertEqual(Path(str(result["summary_path"])), Path("reports/summary/signal_summary_20260309.csv"))
        self.assertEqual(Path(str(result["push_path"])), Path("reports/summary/signal_push_candidates_20260309.csv"))
        self.assertEqual(Path(str(result["preclose_path"])), Path("reports/preclose/preclose_decision_post_close_20260309.csv"))
        self.assertEqual(Path(str(result["daily_conclusion_path"])), Path("reports/daily_conclusion/daily_conclusion_20260309.csv"))
        self.assertEqual(Path(str(result["daily_conclusion_operation_path"])), Path("reports/daily_conclusion/daily_conclusion_operation_20260309.csv"))
        self.assertEqual(Path(str(result["daily_conclusion_xlsx_path"])), Path("reports/daily_conclusion/daily_conclusion_20260309.xlsx"))
        self.assertEqual(Path(str(result["data_gap_path"])), Path("reports/data_gaps/data_gaps_20260309.csv"))
        self.assertEqual(Path(str(result["data_gap_xlsx_path"])), Path("reports/data_gaps/data_gaps_20260309.xlsx"))
        self.assertEqual(Path(str(result["strategy_matrix_path"])), Path("reports/strategy_matrix/strategy_matrix_20260309.xlsx"))

    @patch("scheduler.jobs.export_daily_conclusion_report")
    def test_export_daily_conclusion_report_pipeline_returns_payload(self, mock_export_daily_conclusion):
        mock_export_daily_conclusion.return_value = {
            "csv_path": "reports/daily_conclusion/daily_conclusion_20260309.csv",
            "operation_csv_path": "reports/daily_conclusion/daily_conclusion_operation_20260309.csv",
            "sheet_names": ["Overview", "Daily_Conclusion"],
        }

        result = export_daily_conclusion_report_pipeline()

        self.assertEqual(str(result["csv_path"]), "reports/daily_conclusion/daily_conclusion_20260309.csv")
        self.assertEqual(str(result["operation_csv_path"]), "reports/daily_conclusion/daily_conclusion_operation_20260309.csv")
        self.assertEqual(result["sheet_names"], ["Overview", "Daily_Conclusion"])

    @patch("scheduler.jobs.export_strategy_matrix_report")
    def test_export_strategy_matrix_report_pipeline_returns_payload(self, mock_export_strategy_matrix):
        mock_export_strategy_matrix.return_value = {
            "xlsx_path": "reports/strategy_matrix/strategy_matrix_20260309.xlsx",
            "sheet_names": ["Overview", "EOD_D_Matrix"],
        }

        result = export_strategy_matrix_report_pipeline()

        self.assertEqual(str(result["xlsx_path"]), "reports/strategy_matrix/strategy_matrix_20260309.xlsx")
        self.assertEqual(result["sheet_names"], ["Overview", "EOD_D_Matrix"])

    @patch("scheduler.jobs.export_data_gap_report")
    def test_export_data_gap_report_pipeline_returns_payload(self, mock_export_data_gap):
        mock_export_data_gap.return_value = {
            "csv_path": "reports/data_gaps/data_gaps_20260309.csv",
            "status_csv_path": "reports/data_gaps/data_gap_status_20260309.csv",
            "sheet_names": ["Overview", "Data_Gaps", "Universe_Status"],
        }

        result = export_data_gap_report_pipeline()

        self.assertEqual(str(result["csv_path"]), "reports/data_gaps/data_gaps_20260309.csv")
        self.assertEqual(str(result["status_csv_path"]), "reports/data_gaps/data_gap_status_20260309.csv")
        self.assertEqual(result["sheet_names"], ["Overview", "Data_Gaps", "Universe_Status"])



if __name__ == "__main__":
    unittest.main()
