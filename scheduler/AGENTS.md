# SCHEDULER NOTES

## OVERVIEW
- 这里编排运行模式入口；`jobs.py` 负责收盘批处理，`intraday_runner.py` 负责盘中低频循环。

## WHERE TO LOOK
- 收盘批任务：`jobs.py`
- APScheduler 启动：`run_daily.py`
- 盘中循环：`intraday_runner.py`

## CONVENTIONS
- `run-and-analyze` 保持旧日频语义；新能力优先扩到 `run-eod-analyze` 和 `run-intraday`。
- `run_eod_and_analyze_pipeline()` 现在必须同时返回 `analysis`、`secondary_validation`、`summary_path`、`push_path`。
- `run_intraday_iteration()` 输出应保持脚本友好的 JSON，并显式返回导出路径。
- 盘中循环只在交易时段执行；时段判断统一走 `core.trading_calendar.is_trading_session()`。

## ANTI-PATTERNS
- 不要在调度层重写业务规则；调度只编排，不承载策略/验证/打分细节。
- 不要让 `run_intraday_iteration()` 因单个 symbol 抓取失败整体中断。
- 不要新增返回字段却不更新对应 CLI、README 和测试。
