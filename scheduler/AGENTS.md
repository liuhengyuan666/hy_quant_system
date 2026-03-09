# SCHEDULER NOTES

## OVERVIEW
- 这里编排运行模式入口；`jobs.py` 负责收盘批处理与各类报告导出，`intraday_runner.py` 负责盘中低频循环。

## WHERE TO LOOK
- 收盘批任务与导出管线：`jobs.py`
- APScheduler 启动：`run_daily.py`
- 盘中循环：`intraday_runner.py`

## CONVENTIONS
- `run-and-analyze` 保持旧日频语义；新能力优先扩到 `run-eod-analyze`、`run-preclose-analysis`、独立导出命令。
- `run_eod_and_analyze_pipeline()` 现在是统一日常出口；除 `analysis`、`secondary_validation`、`summary_path`、`push_path` 外，还编排 `preclose`、`daily_conclusion`、`data_gaps`、`strategy_matrix`。
- `run_intraday_iteration()` 输出应保持脚本友好的 JSON，并显式返回导出路径。
- 盘中循环只在交易时段执行；时段判断统一走 `core.trading_calendar.is_trading_session()`。
- 新增独立导出或分析命令时，同步更新 `main.py`、README、说明文档与测试。

## ANTI-PATTERNS
- 不要在调度层重写业务规则；调度只编排，不承载策略/验证/打分细节。
- 不要让 `run_intraday_iteration()` 因单个 symbol 抓取失败整体中断。
- 不要新增返回字段却不更新对应 CLI、README 和测试。
- 不要把“完整 universe 覆盖”这种报告语义偷偷改回调度层过滤；过滤/补齐属于 `signal_service`。
