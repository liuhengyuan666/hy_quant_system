# TESTS NOTES

## OVERVIEW
- 这里以 `unittest` 为主，覆盖策略库、汇总看板、调度返回结构、时间语义，以及收盘前/日报/数据缺口/策略矩阵等报告行为。

## WHERE TO LOOK
- 策略与注册表：`test_strategies.py`、`test_strategy_library.py`
- 汇总 / 推送 / 二次验证：`test_signal_summary.py`、`test_secondary_validation.py`
- 调度与运行时配置：`test_scheduler_jobs.py`、`test_runtime_config.py`、`test_trading_calendar.py`
- 收盘前 / 盘中 / 新报告：`test_preclose_decision.py`、`test_intraday_runner.py`、`test_daily_conclusion_report.py`、`test_data_gap_report.py`、`test_strategy_matrix_report.py`
- dashboard：`test_dashboard_service.py`、`test_dashboard_app.py`
- 日期解析与兼容场景：`test_strategy_matrix_date_resolution.py`、`test_database_schema_compat.py`

## CONVENTIONS
- 新测试文件继续使用 `test_*.py` 命名，适配 `python -m unittest discover -s tests -p "test_*.py"`。
- 优先写小而确定的单元测试；大量使用合成 `DataFrame`，避免依赖外部行情网络。
- 改排序、推送数量、返回字段、时间窗口、完整覆盖行数时，必须同步更新对应测试。
- 需要覆盖单个行为时先跑目标测试模块，再跑全量 `discover`。
- 涉及导出链路时，除了结构字段，也要断言关键行数、sheet 名称或路径字段，避免“命令成功但内容缺行”。
- 涉及 dashboard refresh 时，要同时断言 `summary` 与 `daily_conclusion` 侧效应；否则 `Hypothesis Focus` 这类面板容易空表。

## COMMANDS
- 全量：`python -m unittest discover -s tests -p "test_*.py"`
- 定向：`python -m unittest tests.test_scheduler_jobs tests.test_trading_calendar`
- 报告相关：`python -m unittest tests.test_preclose_decision tests.test_daily_conclusion_report tests.test_data_gap_report tests.test_strategy_matrix_report`

## ANTI-PATTERNS
- 不要为通过测试而删除断言或弱化关键返回字段校验。
- 不要引入依赖真实 AKShare/数据库在线状态的脆弱单元测试，除非该测试明确是兼容/集成场景。
- 不要只改实现不改测试，尤其是 `summary` / `push` / `scheduler` / `report export` 结构字段。
- 不要只看 API status code；dashboard 类变更还要断言关键 metrics（例如 `hypothesis_focus_rows`）和最新文件路径是否真的更新。
