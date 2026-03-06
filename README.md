# Quant System

基于 **AKShare + Pandas + TA-Lib + Backtrader + PostgreSQL(Docker)** 的量化分析平台，当前已经形成：

- `EOD` 多周期分析：`D / W / M`
- `INTRADAY` 低频盘中巡检：默认 `3-10` 分钟节奏
- `secondary_validation` 二次验证闸门
- `summary / group / top / push` 四层看板导出
- `push candidates` 变化推送：默认只保留前 `3` 个

## 当前阶段能力

- 历史数据抓取与入库
- 技术指标计算
- 20 个策略统一注册与筛选
- `EOD` 多周期信号、盘中低频信号
- 趋势评分、分组看板、Top 候选、变化推送
- 盘后 `run-eod-analyze` 与盘中 `run-intraday-once` 双模式运行

## 本地验证

- 详细验证步骤见：`VALIDATION_CHECKLIST.md`
- 最常用验证命令：

```bash
python main.py init-db
python main.py run-eod-analyze
python main.py run-intraday-once
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

12) 启动调度服务（08:30 / 15:30 / 15:35 / 15:40）

```bash
python main.py run-scheduler
```

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
