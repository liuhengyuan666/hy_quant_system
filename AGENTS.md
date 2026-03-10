# PROJECT KNOWLEDGE BASE

## OVERVIEW
- Python 量化分析平台；当前维护 `EOD(日/周/月)`、`INTRADAY(低频盘中巡检)`、`PRE-CLOSE(收盘前决策)` 三条分析链路。
- 主链路已扩展为 `AKShare -> normalize -> PostgreSQL -> indicators/strategies -> secondary validation -> summary dashboard -> report exports`。

## STRUCTURE
- `main.py`：统一 CLI 入口；分发初始化、同步、指标、信号、报告、调度命令。
- `config/`：数据库、运行时、标的池、展示名配置。
- `core/`：时区、模式、交易日历与收盘前窗口判断。
- `analysis/`：`EOD` 周/月重采样等纯分析辅助。
- `data_service/`：历史/实时行情抓取与字段归一化。
- `data_storage/`：SQLAlchemy 模型、会话、upsert 仓储、指标刷新、实时数据读写。
- `strategy_engine/`：策略协议、20 个策略实现、策略注册表。
- `signal_service/`：`EOD`/盘中信号、二次验证、汇总看板、收盘前决策、日报、数据缺口、策略矩阵导出。
- `scheduler/`：收盘批处理、`run-eod-analyze`、盘中循环执行器。
- `web_ui/`：FastAPI dashboard；拼装前端快照、行情面板、分组共识面板与刷新接口。
- `backtest_engine/`：Backtrader 适配与 HTML 报告。
- `tests/`：以 `unittest` 为主，覆盖策略、导出、调度、时间语义与兼容行为。
- `reports/`：导出产物目录；包含 `summary`、`preclose`、`daily_conclusion`、`data_gaps`、`strategy_matrix`。

## WHERE TO LOOK
- 新增 CLI 命令或返回结构：`main.py`
- 改数据库连接或标的池：`config/settings.py`、`config/*.toml`
- 改运行时频率、交易时段、收盘前窗口：`config/runtime.toml`、`core/trading_calendar.py`
- 改历史行情抓取：`data_service/fetch_index.py`、`data_service/fetch_etf.py`、`data_service/normalize.py`
- 改盘中抓取：`data_service/realtime_index.py`、`data_service/realtime_etf.py`、`data_service/normalize_realtime.py`
- 改表结构、upsert、信号日期查询：`data_storage/models.py`、`data_storage/repository.py`
- 改实时表或盘中写入：`data_storage/realtime_repository.py`
- 改指标算法：`data_storage/indicators.py`
- 改 `EOD` 信号流水线：`signal_service/eod_generator.py`
- 改盘中信号流水线：`signal_service/intraday_generator.py`
- 改二次验证与汇总看板：`signal_service/secondary_validation.py`、`signal_service/summary_view.py`
- 改收盘前决策：`signal_service/preclose_decision.py`
- 改每日结论 / 数据缺口 / 策略矩阵：`signal_service/daily_conclusion_report.py`、`signal_service/data_gap_report.py`、`signal_service/strategy_matrix_report.py`
- 改调度编排：`scheduler/jobs.py`、`scheduler/intraday_runner.py`
- 改 dashboard 接口 / 快照读取：`web_ui/app.py`、`web_ui/dashboard_service.py`
- 改 dashboard 排版与表格展示：`web_ui/static/dashboard.html`
- 改回测行为：`backtest_engine/backtest_runner.py`、`backtest_engine/strategy_adapter.py`
- 改说明文档：`README.md`、`使用说明.md`

## CONVENTIONS
- 保持模块边界清晰：抓取在 `data_service`，持久化在 `data_storage`，策略逻辑在 `strategy_engine`，报告拼装在 `signal_service`，调度只在 `scheduler`。
- 继续用 `pandas.DataFrame` 作为层间交换格式；默认列名是 `date/open/high/low/close/volume/symbol`。
- `EOD` 与 `INTRADAY` 继续分表、分入口、分输出；不要把 `datetime` 级数据混入日频表。
- 收盘前 / 日报 / 策略矩阵 / 数据缺口 报告默认面向完整 `universe`，不是只覆盖当前有信号的标的。
- CLI 输出保持脚本友好：成功结果打印 JSON 或简洁文本；不要混入大量调试输出。
- 汇总导出约定：`summary/group/top/push` 四类产物同目录生成，文件名前缀稳定。
- dashboard 默认混合消费 `summary` / `intraday` / `preclose` / `daily_conclusion`；改任一导出文件名或字段时必须同步核对 `web_ui/dashboard_service.py`。
- `daily_conclusion` 在显式传入 `intraday_ts` 时允许生成“当天盘中版”；不要再把整份日报的目标日期强制回退到最近已闭市日。
- 单个 symbol 失败不应拖垮整批任务，但吞错时至少保留可追踪上下文。

## ANTI-PATTERNS
- 不要把策略实现直接耦合到数据库会话或 AKShare 调用。
- 不要改动 `normalize_ohlcv` 输出契约却不同时更新仓储、指标、测试。
- 不要把盘中逻辑塞回旧的 `run-and-analyze` 单链路；新功能优先挂到 `run-eod-analyze`、`run-intraday`、独立导出命令。
- 不要在 `main.py` 写复杂业务；复杂逻辑下沉到对应模块。
- 不要新增自由格式信号值；核心信号继续使用 `BUY/SELL/HOLD`，动作扩展走受控字段。
- 不要新增返回字段却不更新对应 CLI、README、说明文档和测试。
- 不要让报告对缺行情标的泄露旧 summary 残留结论；缺数据时明确标注 `NO_DATA` / 中性动作。
- 不要让 dashboard 把旧盘中快照伪装成今天实时；需要明确 source / updated_at 语义。

## COMMANDS
- 安装依赖：`python -m pip install -r requirements.txt`
- 启动数据库：`docker compose up -d`
- 初始化表：`python main.py init-db`
- 同步数据：`python main.py sync-data`
- 计算指标：`python main.py calc-indicators`
- 生成日频信号：`python main.py gen-signals`
- 生成多周期 `EOD` 信号：`python main.py gen-eod-signals --frequencies D,W,M`
- 跑旧日频全流程：`python main.py run-and-analyze`
- 跑 `EOD` 多周期分析：`python main.py run-eod-analyze --frequencies D,W,M`
- 跑盘中一次巡检：`python main.py run-intraday-once`
- 跑收盘前决策：`python main.py run-preclose-analysis [--use-intraday-snapshot]`
- 导出统一看板：`python main.py export-signal-summary`
- 导出每日结论：`python main.py export-daily-conclusion`
- 导出数据缺口：`python main.py export-data-gaps`
- 导出策略矩阵：`python main.py export-strategy-matrix`
- 启动 dashboard：`python main.py run-dashboard --host 127.0.0.1 --port 8000`
- 启动调度：`python main.py run-scheduler`
- 运行测试：`python -m unittest discover -s tests -p "test_*.py"`

## NOTES
- 当前回测入口只正式支持 `strategy=ma`，见 `main.py`。
- `TA-Lib` 不可用时会退回 `pandas` 计算；涉及指标结果时要注意两套实现一致性。
- 仓储层使用 PostgreSQL `ON CONFLICT DO UPDATE`；若换库，相关 SQLAlchemy 方言代码要一起处理。
- `secondary_validation` 仍是以后处理规则层为主；报告层只是消费其受控输出。
- `summary_view` 的 `push_candidates` 默认只保留前三个变化最大的候选。
