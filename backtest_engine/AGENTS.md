# BACKTEST ENGINE NOTES

## OVERVIEW
- 这里封装 Backtrader 适配、绩效指标提取与 HTML 报告导出；当前是独立于实时/调度主链路的离线回测层。

## WHERE TO LOOK
- 跑回测主入口：`backtest_runner.py`
- Backtrader 策略适配：`strategy_adapter.py`
- HTML 报告生成：`report.py`

## CONVENTIONS
- 输入数据以 `pandas.DataFrame` 传入，最少包含 `date/open/high/low/close/volume`。
- `strategy_adapter.py` 负责隔离 `backtrader` 可选依赖；缺依赖时保持可导入、在运行时再报错。
- 报告输出继续落到 `reports/`，保持单文件 HTML 可直接打开查看。
- 当前正式支持的 CLI 回测策略仍是 `strategy=ma`；扩展策略时同步改 `main.py`、测试与说明。

## ANTI-PATTERNS
- 不要在回测层直接访问数据库会话；数据准备应在调用方完成。
- 不要把盘中实时逻辑、调度循环或 AKShare 抓取塞进 `backtest_engine/`。
- 不要修改输入列契约却不同时更新报告、适配器与测试。
