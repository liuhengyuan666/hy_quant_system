from __future__ import annotations

import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from web_ui.app import create_app


class DashboardAppTests(unittest.TestCase):
    def test_dashboard_routes_return_expected_payloads(self):
        market_overview = {
            "quote_status": "实时数据库 / Live DB",
            "quote_error": None,
            "quote_bar_frequency": "5",
            "index_quotes": [{"symbol": "000300", "name": "沪深300", "current_level": 3812.12, "change_value": 46.21, "change_pct": 0.0123}],
            "etf_quotes": [{"symbol": "510300", "name": "沪深300ETF", "current_price": 4.52, "change_value": 0.03, "change_pct": 0.0067}],
            "index_quote_gainers": [{"symbol": "000300", "name": "沪深300", "current_level": 3812.12, "change_value": 46.21, "change_pct": 0.0123}],
            "index_quote_losers": [],
            "index_quote_flat": [],
            "index_quote_stale": [],
            "index_quote_missing": [],
            "etf_quote_gainers": [{"symbol": "510300", "name": "沪深300ETF", "current_price": 4.52, "change_value": 0.03, "change_pct": 0.0067}],
            "etf_quote_losers": [],
            "etf_quote_flat": [],
            "etf_quote_stale": [],
            "etf_quote_missing": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "web_ui.dashboard_service._build_market_overview_tables",
            return_value=market_overview,
        ):
            report_root = Path(temp_dir) / "reports"
            (report_root / "summary").mkdir(parents=True)
            (report_root / "intraday").mkdir(parents=True)
            (report_root / "daily_conclusion").mkdir(parents=True)
            (report_root / "summary" / "signal_summary_20260309_1102.csv").write_text(
                "conviction_rank,symbol,name,intraday,dashboard_action,composite_score\n"
                "1,510300,沪深300ETF,BUY,PRIORITY_BUY,7.0\n",
                encoding="utf-8-sig",
            )
            (report_root / "daily_conclusion" / "daily_conclusion_20260309.csv").write_text(
                "conviction_rank,symbol,name,overall_action,hypothesis_consensus_action,hypothesis_tiebreak_applied,hypothesis_summary_text\n"
                "1,510300,沪深300ETF,BUY,BUY,True,分组共识改判为 BUY（2 组；趋势跟随@long_term | 动量@short_term）\n",
                encoding="utf-8-sig",
            )

            client = TestClient(create_app(report_root=report_root))
            health = client.get("/api/health")
            snapshot = client.get("/api/dashboard")
            html = client.get("/")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        self.assertEqual(snapshot.status_code, 200)
        self.assertEqual(snapshot.json()["metrics"]["summary_rows"], 1)
        self.assertEqual(snapshot.json()["metrics"]["index_quote_rows"], 1)
        self.assertEqual(snapshot.json()["metrics"]["hypothesis_focus_rows"], 1)
        self.assertEqual(html.status_code, 200)
        self.assertIn("盘中监控仪表盘", html.text)
        self.assertIn("Index Pool｜指数池行情", html.text)
        self.assertEqual(html.text.count('class="panel full-row"'), 7)
        self.assertIn("Hypothesis Focus｜分组共识", html.text)
        self.assertIn("旧快照", html.text)
        self.assertIn("无数据", html.text)
        self.assertIn('["ts", "symbol", "name", "strategy", "signal", "score"]', html.text)
        self.assertIn("const QUOTE_COLUMN_LABELS", html.text)
        self.assertIn("Top Gainers｜涨幅榜", html.text)
        self.assertIn("Top Losers｜跌幅榜", html.text)
        self.assertIn("涨跌点/额 / Change", html.text)

    def test_refresh_route_returns_refresh_snapshot(self):
        client = TestClient(create_app())
        payload = {"metrics": {"summary_rows": 3}, "tables": {"action_focus": [], "push_candidates": [], "latest_intraday": [], "summary": []}}
        with patch("web_ui.app.refresh_dashboard_snapshot", return_value=payload):
            response = client.post("/api/dashboard/refresh")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["metrics"]["summary_rows"], 3)


if __name__ == "__main__":
    unittest.main()
