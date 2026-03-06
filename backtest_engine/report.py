from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def _line_points(values: list[float], width: int = 900, height: int = 280, pad: int = 20) -> str:
    if not values:
        return ""

    min_v = min(values)
    max_v = max(values)
    span = max(max_v - min_v, 1e-12)
    step = (width - (2 * pad)) / max(len(values) - 1, 1)
    points: list[str] = []

    for idx, value in enumerate(values):
        x = pad + (idx * step)
        y = height - pad - ((value - min_v) / span) * (height - (2 * pad))
        points.append(f"{x:.2f},{y:.2f}")

    return " ".join(points)


def _drawdown_series(equity: list[float]) -> list[float]:
    if not equity:
        return []
    values = np.asarray(equity, dtype=float)
    peak = np.maximum.accumulate(values)
    drawdown = (values / peak) - 1
    return drawdown.tolist()


def generate_html_report(metrics: dict[str, float], equity_curve: pd.DataFrame, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    curve = equity_curve.copy()
    if curve.empty:
        curve = pd.DataFrame(columns=["date", "equity"])

    curve["date"] = pd.to_datetime(curve["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    curve["equity"] = pd.to_numeric(curve["equity"], errors="coerce")
    curve = curve.dropna(subset=["date", "equity"]).reset_index(drop=True)

    equity_values = curve["equity"].astype(float).tolist()
    drawdown_values = _drawdown_series(equity_values)
    equity_points = _line_points(equity_values)
    drawdown_points = _line_points(drawdown_values)

    metric_rows = "".join(
        [
            f"<tr><td>{key}</td><td>{value:.6f}</td></tr>"
            for key, value in metrics.items()
            if isinstance(value, (float, int))
        ]
    )

    raw_curve = json.dumps(curve.to_dict("records"), ensure_ascii=False)

    html = f"""
<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <title>Quant Backtest Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    table {{ border-collapse: collapse; margin-bottom: 24px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
    th {{ background: #f3f5f7; }}
    .chart {{ margin: 16px 0; }}
    svg {{ width: 900px; height: 280px; border: 1px solid #ddd; background: #fff; }}
    .label {{ margin-bottom: 6px; font-weight: 600; }}
  </style>
</head>
<body>
  <h1>Backtest Report</h1>
  <h2>Metrics</h2>
  <table>
    <thead><tr><th>Metric</th><th>Value</th></tr></thead>
    <tbody>{metric_rows}</tbody>
  </table>

  <div class=\"chart\">
    <div class=\"label\">收益曲线</div>
    <svg viewBox=\"0 0 900 280\" preserveAspectRatio=\"none\">
      <polyline fill=\"none\" stroke=\"#2f80ed\" stroke-width=\"2\" points=\"{equity_points}\" />
    </svg>
  </div>

  <div class=\"chart\">
    <div class=\"label\">回撤曲线</div>
    <svg viewBox=\"0 0 900 280\" preserveAspectRatio=\"none\">
      <polyline fill=\"none\" stroke=\"#eb5757\" stroke-width=\"2\" points=\"{drawdown_points}\" />
    </svg>
  </div>

  <h2>Raw Curve Data</h2>
  <pre>{raw_curve}</pre>
</body>
</html>
"""

    output_path.write_text(html, encoding="utf-8")
    return output_path
