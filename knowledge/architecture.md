# 架构知识基线 (Architecture Baseline)

> 本文件记录 Quant System 当前真实采用的技术栈、组件通信与全局约束。
> 更新原则：仅追加/定向修改，禁止全量重写。

---

## 1. 技术栈概览

| 层级 | 技术选型 | 版本约束 |
|------|----------|----------|
| 语言 | Python | 3.11+（依赖标准库 `tomllib`） |
| 数据科学 | Pandas, NumPy | pandas>=2.1.0, numpy>=1.26.0 |
| 技术指标 | TA-Lib（优先）+ Pandas 兜底 | TA-Lib>=0.4.28 |
| 数据库 | PostgreSQL (Docker) | SQLAlchemy>=2.0.0, psycopg2-binary>=2.9.0 |
| Web 框架 | FastAPI + Uvicorn | fastapi>=0.115.0, uvicorn>=0.30.0 |
| 调度 | APScheduler | >=3.10.4 |
| 回测 | Backtrader | >=1.9.78.123 |
| 数据源 | AKShare, pytdx, futu-api | akshare>=1.17.0, pytdx>=1.72, futu-api>=10.0.6008 |
| 报告导出 | xlsxwriter | >=3.2.0 |
| 配置格式 | TOML | tomllib (标准库) / tomli (py<3.11) |

---

## 2. 系统拓扑

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI / Dashboard                       │
│  (main.py / FastAPI / static/dashboard.html)                 │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                      Scheduler (APScheduler)                 │
│  run_daily.py / intraday_runner.py / jobs.py                 │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────┐
│ data_service│  │data_storage │  │      strategy_engine         │
│ (抓取/归一)  │  │(ORM/仓储/指标)│  │   (策略协议/注册表/实现)      │
└─────────────┘  └─────────────┘  └─────────────────────────────┘
       │                │                    │
       └────────────────┴────────────────────┘
                          │
┌─────────────────────────────────────────────────────────────┐
│                   signal_service (信号/报告)                │
│  eod_generator / intraday_generator / secondary_validation  │
│  summary_view / preclose_decision / daily_conclusion_report │
│  data_gap_report / strategy_matrix_report                  │
└─────────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────────────┐
│                     PostgreSQL (Docker)                      │
│  market_price / technical_indicator / signal_record          │
│  (plus 实时表: realtime_bar / realtime_signal)               │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 核心组件通信

### 3.1 数据流

```
AKShare/pytdx/futu → data_service.normalize → data_storage.repository (upsert)
                                                          ↓
                                              data_storage.indicators (刷新)
                                                          ↓
                                              strategy_engine.library (策略注册表)
                                                          ↓
                                              signal_service.*_generator (信号生成)
                                                          ↓
                                              signal_service.secondary_validation (二次验证)
                                                          ↓
                                              signal_service.summary_view / *report (报告导出)
                                                          ↓
                                              web_ui.dashboard_service (Dashboard 拼装)
```

### 3.2 配置流

```
config/*.toml → config.settings (统一装配入口) → 各模块 load_*_config()
```

- `br_db.toml`：数据库连接
- `universe.toml`：标的池
- `symbol_meta.toml`：中文名/展示代码映射
- `runtime.toml`：运行时参数（时段、频率、分组权重）

### 3.3 调度流

```
APScheduler → scheduler.jobs (收盘批处理)
            → scheduler.intraday_runner (盘中循环)
            → scheduler.run_daily.py (启动入口)
```

---

## 4. 数据库模型

| 表名 | 用途 | 关键约束 |
|------|------|----------|
| `market_price` | 日频 OHLCV | `uq_market_price_symbol_date` |
| `technical_indicator` | 技术指标 | `uq_technical_indicator_symbol_date` |
| `signal_record` | 策略信号 | `uq_signal_record_scope` (date+symbol+strategy+mode+frequency) |
| `realtime_bar` | 盘中 bars | 实时数据读写 |
| `realtime_signal` | 盘中信号 | 实时信号记录 |

---

## 5. 全局约束

### 5.1 时区约束

- 所有时间逻辑统一基于 `Asia/Shanghai`
- 禁止混用 naive datetime 与时区 datetime
- `core/clock.py` 提供 `now_shanghai()` 统一入口

### 5.2 数据格式约束

- 层间交换格式：`pandas.DataFrame`
- 默认列名：`date/open/high/low/close/volume/symbol`
- EOD 与 INTRADAY 分表、分入口、分输出，禁止混用

### 5.3 错误处理约束

- 单个 symbol 失败不拖垮整批任务
- 抓取层必须保留可追踪上下文（错误列表）
- 指标刷新异常不中断整批执行

### 5.4 依赖约束

- `backtrader` / `TA-Lib` 为可选依赖，缺省时保持可导入、运行时再报错
- `futu-api` 仅在启用港股实时时生效

---

## 6. 部署拓扑

```
开发/本地：
  Docker Compose (PostgreSQL) + Python 虚拟环境
  
调度运行：
  python main.py run-scheduler  (长期进程)
  或 Windows 任务计划程序

Dashboard：
  python main.py run-dashboard --host 127.0.0.1 --port 8000
```

---

*最后更新：2026-06-12 — 初始化架构基线*
