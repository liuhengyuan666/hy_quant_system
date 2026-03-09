from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

from signal_service.strategy_matrix_report import _resolve_eod_signal_dates


class StrategyMatrixDateResolutionTests(unittest.TestCase):
    @patch("signal_service.strategy_matrix_report.load_latest_signal_date")
    @patch("signal_service.strategy_matrix_report.load_latest_signal_date_on_or_before")
    def test_resolve_eod_signal_dates_uses_frequency_specific_latest_dates(
        self,
        mock_latest_on_or_before,
        mock_latest,
    ):
        mock_latest.return_value = date(2026, 3, 7)
        mock_latest_on_or_before.side_effect = [date(2026, 3, 6), date(2026, 3, 6)]

        result = _resolve_eod_signal_dates(session=object(), requested_date=None)

        self.assertEqual(result["D"], date(2026, 3, 7))
        self.assertEqual(result["W"], date(2026, 3, 6))
        self.assertEqual(result["M"], date(2026, 3, 6))


if __name__ == "__main__":
    unittest.main()
