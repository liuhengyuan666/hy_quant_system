# Quant System

基于 **pytdx + AKShare + Pandas + TA-Lib + Backtrader + PostgreSQL(Docker)** 的量化分析平台，当前已经形成：

- `EOD` 多周期分析：`D / W / M`
- `INTRADAY` 低频盘中巡检：默认 `3-10` 分钟节奏
- `PRE-CLOSE` 收盘前决策分析：盘后按最近交易日收盘价分析，盘中可于 `14:45` 自动触发
- `secondary_validation` 二次验证闸门
- `summary / group / top / push` 四层看板导出
- `daily conclusion` 每日长线/短线简明结论报告
- `data gaps` 数据缺口诊断报告
- `strategy matrix` 全量策略矩阵 Excel 报告
- `push candidates` 变化推送：默认只保留前 `3` 个
- 本地 `dashboard`：浏览器实时查看 summary / intraday / push，并支持手动触发一次盘中刷新

## 当前阶段能力

- 历史数据抓取与入库
- 技术指标计算
- 20 个策略统一注册与筛选
- `EOD` 多周期信号、盘中低频信号
- 收盘前买卖点判断（指数/ETF 中长线视角）
- 每日长线/短线 `BUY/HOLD/SELL` 简明结论
- 数据缺口/缺信号诊断导出
- 趋势评分、分组看板、Top 候选、变化推送
- 标的 × 策略 对应关系 Excel 总报告
- 盘后 `run-eod-analyze` 与盘中 `run-intraday-once` 双模式运行

## 实时数据源说明

- 大陆数字代码的指数 / ETF 盘中 `5` 分钟 bars 当前优先使用 `pytdx`
- `AKShare` 仍保留为补充来源与非数字代码兜底路径
- 当前 `HSCEI` / `HSTECH` / `HSAHP` 这类港股指数代码已预留 **Futu OpenAPI / OpenD** 接入口；启用方式是运行本地 OpenD，并在 `config/runtime.toml` 的 `[runtime.hk_realtime]` / `[runtime.hk_realtime.futu]` 中配置 provider、端口和 symbol 映射
- 若未启用 OpenD，系统仍可继续跑大陆指数 / ETF 的实时巡检；港股指数会保持无盘中 bars，不影响大陆实时信号生成

## 本地验证

- 详细验证步骤见：`VALIDATION_CHECKLIST.md`
- 建议使用 **Python 3.11+**（当前配置加载依赖标准库 `tomllib`）
- 最常用验证命令：

```bash
python main.py init-db
python main.py run-eod-analyze
python main.py run-intraday-once
python main.py run-dashboard --host 127.0.0.1 --port 8000
python -m unittest discover -s tests -p "test_*.py"
```

## 1. 项目结构

```text
quant-system
├── config
├── data_service
├── data_storage
├── strategy_engine
├── backtest_engine
├── signal_service
├── scheduler
├── docker
├── reports
├── logs
└── notebooks
```

## 2. 快速开始

1) 启动数据库

```bash
docker compose up -d
```

2) 安装依赖

```bash
python -m pip install -r requirements.txt
```

3) 初始化数据库表

```bash
python main.py init-db
```

4) 拉取行情并入库

```bash
python main.py sync-data
```

5) 计算技术指标

```bash
python main.py calc-indicators
```

6) 查看已接入策略列表

```bash
python main.py list-strategies
```

7) 生成交易信号（默认运行全部策略）

```bash
python main.py gen-signals
```

8) 仅运行指定策略（逗号分隔）

```bash
python main.py gen-signals --strategies MA_strategy,RSRS_strategy,ETF_rotation_strategy
```

9) 运行回测（示例）

```bash
python main.py backtest --symbol 510300 --strategy ma
```

10) 一次调用：跑流程 + 自动分析信号

```bash
python main.py run-and-analyze
```

该命令输出中新增 `secondary_validation`，作为结论前二次考评，包含：

- 7条交易经验规则的量化检查结果（`rule_evaluations`）
- 标的级二次动作建议（`symbol_reviews`）
- 总体考评分数与闸门（`review_score`、`review_gate`）

11) 盘后多周期分析（`D/W/M`）+ 汇总看板

```bash
python main.py run-eod-analyze
```

该命令当前会同时输出：

- `analysis`：按 `D/W/M` 分频统计分析
- `secondary_validation`：按 `D/W/M` 分频的二次验证结果
- `summary_path`：统一趋势/盘中汇总看板 CSV 路径
- `push_path`：本轮变化最大的前3个候选推送清单 CSV 路径
- `preclose_path`：基于最近交易日收盘价的收盘前决策 CSV 路径
- `daily_conclusion_path`：每日简明结论 CSV 路径
- `daily_conclusion_operation_path`：每日最终操作版 CSV 路径
- `daily_conclusion_xlsx_path`：每日简明结论 Excel 路径
- `data_gap_path`：数据缺口诊断 CSV 路径
- `data_gap_xlsx_path`：数据缺口诊断 Excel 路径
- `strategy_matrix_path`：全量策略矩阵 Excel 报告路径

11.1) 单独运行收盘前决策分析

```bash
python main.py run-preclose-analysis
```

若需要基于当前盘中快照手动运行：

```bash
python main.py run-preclose-analysis --use-intraday-snapshot
```

输出包含：

- `csv_path`：`reports/preclose/` 下的收盘前决策明细
- `json_path`：本轮统计摘要

11.2) 导出整体策略矩阵报告

```bash
python main.py export-strategy-matrix
```

输出包含：

- `xlsx_path`：`reports/strategy_matrix/` 下的 Excel 工作簿
- `sheet_names`：工作簿内的 sheet 列表
- `symbol_rows`：本轮覆盖的标的数量

工作簿当前默认包含：

- `Action_Focus`：只保留非 `HOLD` 的重点动作视图
- `EOD_D/W/M_Matrix`：按指数/ETF分组后的策略矩阵
- `Symbol_Summary` / `PRE_CLOSE_View` / `Strategy_Stats`

11.3) 导出每日长线/短线简明结论

```bash
python main.py export-daily-conclusion
```

输出包含：

- `csv_path`：`reports/daily_conclusion/` 下的简明结论主表
- `operation_csv_path`：更短的最终操作版主表
- `json_path`：结构化 JSON 结论
- `xlsx_path`：包含 `Operation_View / Daily_Conclusion / Hypothesis_Summary / LongTerm_Evidence / ShortTerm_Evidence / Data_Gaps` 的 Excel 工作簿

`Daily_Conclusion` / `Operation_View` 当前还会额外给出：

- `hypothesis_consensus_action`：按策略哲学分组后的共识方向
- `hypothesis_summary_text`：更直观的分组共识摘要文本
- `hypothesis_tiebreak_applied`：是否真的用分组共识改判了最终动作

11.4) 导出数据缺口诊断报告

```bash
python main.py export-data-gaps
```

输出包含：

- `csv_path`：仅保留 `NO_DATA / PARTIAL` 问题标的的 CSV
- `status_csv_path`：全量标的状态 CSV
- `json_path`：结构化数据缺口诊断 JSON
- `xlsx_path`：包含 `Data_Gaps / Universe_Status / Overview` 的 Excel 工作簿

12) 启动调度服务（08:30 / 15:30 / 15:35 / 15:40）

```bash
python main.py run-scheduler
```

13) 启动本地实时 Dashboard

```bash
python main.py run-dashboard --host 127.0.0.1 --port 8000
```

打开浏览器访问：`http://127.0.0.1:8000/`

Dashboard 当前提供：

- 顶部指标卡：summary / intraday / push / priority action 数量
- `Action Focus`：优先动作与重点观察标的
- `Hypothesis Focus`：分组共识摘要与是否触发改判
- `Push Candidates`：最新变化推送候选
- `Latest Intraday Signals`：最近盘中信号
- `Latest Summary`：最新汇总结果
- 页面自动 `15s` 轮询最新 CSV 快照
- 手动按钮：触发一次 `run_intraday_iteration()` 并立即刷新页面数据

## 2.1 分组共识运行时配置

文件：`config/runtime.toml`

```toml
[runtime.hypothesis.weights]
trend_following = 1.0
mean_reversion = 1.0
momentum = 1.0
volatility_breakout = 1.0
volume_based = 1.0
cross_asset_allocation = 1.2
uncategorized = 0.5

[runtime.hypothesis.tiebreak]
conflict_min_score = 0.18
conflict_min_confidence = 0.55
hold_min_score = 0.28
hold_min_confidence = 0.60
min_groups = 2
```

说明：

- `weights` 控制不同策略哲学分组在共识中的相对权重
- `cross_asset_allocation` 默认略高，适合 ETF 轮动 / 多因子类策略
- `uncategorized` 默认较低，避免未分类策略过度影响最终结论
- `tiebreak` 只作用于两类场景：`长短线冲突` 或 `长短线都 HOLD`
- 其余情形仍优先沿用原来的 `long_term_action / short_term_action` 规则

## 3. 数据库连接配置

配置文件：`config/br_db.toml`

```toml
[br_db.connections.pgsql]
mode = "Pgsql"
hostname = "127.0.0.1"
hostport = "5432"
database = "custom_client"
username = "root"
userpass = "111111"
params = []
charset = "Utf8mb4"
prefix = ""
debug = false
```

## 4. 代码中文名映射（用于最终CSV输出）

配置文件：`config/symbol_meta.toml`

```toml
[symbol_meta]
"000001" = { name = "上证指数", display_symbol = "1A0001" }
"000300" = { name = "沪深300", display_symbol = "1A0300" }
"000905" = { name = "中证500", display_symbol = "1A0905" }
```

`reports/signals_YYYYMMDD.csv` 会新增两列：

- `display_symbol`
- `name`

## 5. 已接入策略库（20个）

- MA_strategy
- RSRS_strategy
- EMA_cross_strategy
- Triple_MA_strategy
- MACD_hist_strategy
- RSI_reversion_strategy
- Bollinger_breakout_strategy
- Bollinger_reversion_strategy
- Donchian_breakout_strategy
- Momentum_20_strategy
- Momentum_60_strategy
- ROC_20_strategy
- Volatility_breakout_strategy
- ATR_channel_strategy
- KDJ_cross_strategy
- CCI_reversion_strategy
- OBV_trend_strategy
- ADX_trend_strategy
- ETF_rotation_strategy
- MultiFactor_strategy

## 6. 说明

- 本工程为可扩展骨架，默认输出 HTML 回测报告到 `reports/`
- 若本机 TA-Lib 安装困难，系统会自动使用 Pandas 兜底计算指标
- Windows 可用任务计划程序或长期运行 `run-scheduler` 方式替代 cron
