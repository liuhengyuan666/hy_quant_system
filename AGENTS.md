# PROJECT KNOWLEDGE BASE

## OVERVIEW
- Python 量化分析平台；当前同时维护 `EOD(日/周/月)` 与 `INTRADAY(低频盘中巡检)` 两条运行模式。
- 主链路已扩展为 `AKShare -> normalize -> PostgreSQL -> indicators/strategies -> secondary validation -> summary dashboard -> reports`。

## STRUCTURE
- `main.py`：统一 CLI 入口；分发初始化、同步、指标、信号、回测、调度命令。
- `config/`：数据库与标的池配置；优先读取环境变量，再读 TOML。
- `core/`：模式、时区、交易时段判断；为 `EOD/INTRADAY` 共享。
- `analysis/`：`EOD` 周/月重采样等纯分析辅助模块。
- `data_service/`：外部行情抓取与字段归一化。
- `data_storage/`：SQLAlchemy 模型、会话、upsert 仓储、指标刷新。
- `strategy_engine/`：20 个策略实现与策略注册表。
- `signal_service/`：`EOD`/盘中信号生成、二次验证、汇总看板、Top 候选与变化推送。
- `backtest_engine/`：Backtrader 适配与 HTML 报告。
- `scheduler/`：收盘批处理、`run-eod-analyze`、盘中循环执行器。
- `tests/`：以 `unittest` 为主，覆盖策略库与信号分析核心行为。

## WHERE TO LOOK
- 新增 CLI 命令：`main.py`
- 改数据库连接或标的池：`config/settings.py`、`config/*.toml`
- 改运行时频率、交易时段：`config/runtime.toml`、`core/trading_calendar.py`
- 改行情抓取：`data_service/fetch_index.py`、`data_service/fetch_etf.py`、`data_service/normalize.py`
- 改盘中抓取：`data_service/realtime_index.py`、`data_service/realtime_etf.py`、`data_service/normalize_realtime.py`
- 改表结构或 upsert：`data_storage/models.py`、`data_storage/repository.py`
- 改实时表或盘中写入：`data_storage/realtime_repository.py`
- 改指标算法：`data_storage/indicators.py`
- 新增或调整策略：`strategy_engine/library.py` + 对应策略模块
- 改 `EOD` 信号流水线：`signal_service/eod_generator.py`
- 改盘中信号流水线：`signal_service/intraday_generator.py`
- 改二次验证与汇总看板：`signal_service/secondary_validation.py`、`signal_service/summary_view.py`
- 改日调度流程：`scheduler/jobs.py`、`scheduler/run_daily.py`
- 改盘中循环：`scheduler/intraday_runner.py`
- 改回测行为：`backtest_engine/backtest_runner.py`、`backtest_engine/strategy_adapter.py`

## CONVENTIONS
- 保持模块边界清晰：抓取在 `data_service`，持久化在 `data_storage`，策略逻辑在 `strategy_engine`。
- 继续用 `pandas.DataFrame` 作为层间交换格式；默认列名是 `date/open/high/low/close/volume/symbol`。
- `EOD` 与 `INTRADAY` 要继续分表、分入口、分输出；不要把 `datetime` 级数据混入日频表。
- 配置优先级：环境变量覆盖 `config/br_db.toml`；不要把敏感值硬编码到新模块。
- CLI 输出偏脚本友好：成功结果打印 JSON 或简洁文本；不要混入大量调试输出。
- 看板导出约定：`summary/group/top_candidates/push_candidates` 同目录生成，且保持文件名前缀稳定。
- 优先保留“单个 symbol 失败不拖垮整批任务”的风格，但吞错时至少保留可追踪上下文。

## ANTI-PATTERNS
- 不要把策略实现直接耦合到数据库会话或 AKShare 调用。
- 不要改动 `normalize_ohlcv` 输出契约却不同时更新仓储、指标、测试。
- 不要把盘中逻辑塞回旧的 `run-and-analyze` 单链路；新功能优先挂到 `run-eod-analyze`、`run-intraday`、`summary_view`。
- 不要在 `main.py` 写复杂业务；复杂逻辑下沉到对应模块。
- 不要新增只在一个地方使用、但破坏统一列名约定的数据格式。
- 不要把研究型脚本逻辑直接塞进调度任务；先抽成纯函数。

## COMMANDS
- 安装依赖：`python -m pip install -r requirements.txt`
- 启动数据库：`docker compose up -d`
- 初始化表：`python main.py init-db`
- 同步数据：`python main.py sync-data`
- 计算指标：`python main.py calc-indicators`
- 生成信号：`python main.py gen-signals`
- 生成多周期 `EOD` 信号：`python main.py gen-eod-signals --frequencies D,W,M`
- 跑全流程：`python main.py run-and-analyze`
- 跑 `EOD` 多周期分析：`python main.py run-eod-analyze`
- 跑盘中一次巡检：`python main.py run-intraday-once`
- 导出统一看板：`python main.py export-signal-summary`
- 启动调度：`python main.py run-scheduler`
- 运行测试：`python -m unittest discover -s tests -p "test_*.py"`

## NOTES
- 当前回测入口只正式支持 `strategy=ma`，见 `main.py`。
- `TA-Lib` 不可用时会退回 `pandas` 计算；涉及指标结果时要注意两套实现一致性。
- 仓储层使用 PostgreSQL `ON CONFLICT DO UPDATE`；若换库，相关 SQLAlchemy 方言代码要一起处理。
- `secondary_validation` 当前本质上是 `EOD` 后处理规则层；汇总看板已吸收其标的级结果，但规则本体仍以日频上下文为准。
- 变化推送当前落为 `reports/summary/signal_push_candidates_*.csv`，默认只保留前三个变化最大的候选。
