# 模块知识基线 (Modules Baseline)

> 本文件记录 Quant System 的物理目录拓扑与模块职责边界。
> 更新原则：仅追加/定向修改，禁止全量重写。

---

## 1. 根目录结构

```
quant-system/
├── config/              # 配置装配入口
├── core/                # 时区、模式、交易日历
├── analysis/            # EOD 重采样等纯分析辅助
├── data_service/        # 历史/实时行情抓取与字段归一化
├── data_storage/        # ORM 模型、会话、仓储、指标刷新
├── strategy_engine/     # 策略协议、20 个策略实现、注册表
├── signal_service/      # 信号生成、二次验证、汇总看板、报告导出
├── scheduler/           # 收盘批处理、盘中循环、调度入口
├── web_ui/              # FastAPI Dashboard、静态页面
├── backtest_engine/     # Backtrader 适配与 HTML 报告
├── tests/               # unittest 测试套件
├── reports/             # 导出产物目录
├── docker/              # Docker 初始化脚本
├── notebooks/           # Jupyter 笔记本（可选）
├── main.py              # 统一 CLI 入口
├── requirements.txt     # Python 依赖
├── docker-compose.yml   # PostgreSQL 服务定义
├── README.md            # 项目说明
├── 使用说明.md           # 详细使用文档
└── AGENTS.md            # 项目知识指引（本系统消费）
```

---

## 2. 一级模块职责

### 2.1 `config/` — 配置层

| 文件 | 职责 |
|------|------|
| `settings.py` | 唯一配置装配入口；TOML 解析、环境变量覆盖、dataclass 装配 |
| `br_db.toml` | PostgreSQL 连接配置 |
| `universe.toml` | 标的池：index_symbols + etf_symbols |
| `symbol_meta.toml` | 标的中文名与展示代码映射 |
| `runtime.toml` | 运行时参数：时段、频率、分组权重、港股实时配置 |

**边界**：只负责配置加载与装配，不写业务逻辑。

### 2.2 `core/` — 基础设施层

| 文件 | 职责 |
|------|------|
| `clock.py` | 上海时区当前时间 `now_shanghai()` |
| `modes.py` | 分析模式枚举：`EOD` / `INTRADAY` / `PRE_CLOSE` |
| `trading_calendar.py` | 交易日判断、最近闭市日、交易时段、收盘前窗口 |

**边界**：纯函数优先，无数据库/网络依赖，便于单元测试。

### 2.3 `analysis/` — 分析辅助层

| 文件 | 职责 |
|------|------|
| `eod_resampler.py` | 日频 → 周频/月频 OHLCV 重采样；频率归一化 |

**边界**：纯 DataFrame 转换，无状态。

### 2.4 `data_service/` — 数据抓取层

| 文件 | 职责 |
|------|------|
| `fetch_index.py` | 指数历史行情抓取（AKShare，含港股） |
| `fetch_etf.py` | ETF 历史行情抓取（Eastmoney，需 disable proxy） |
| `normalize.py` | 原始数据 → 统一 OHLCV 格式 |
| `sync_market.py` | 批量同步入口：指数 + ETF |
| `realtime_index.py` | 指数盘中实时抓取（pytdx 优先） |
| `realtime_etf.py` | ETF 盘中实时抓取 |
| `normalize_realtime.py` | 实时数据字段归一化 |
| `akshare_runtime.py` | AKShare 运行时兼容辅助 |
| `tdx_realtime.py` | pytdx 实时接口封装 |
| `futu_realtime.py` | Futu OpenAPI 实时接口（港股可选） |

**边界**：只负责获取原始数据并归一化，不写数据库。

### 2.5 `data_storage/` — 数据持久化层

| 文件 | 职责 |
|------|------|
| `database.py` | SQLAlchemy 引擎、会话工厂、`session_scope()` 上下文管理器 |
| `models.py` | ORM 模型：`MarketPrice`、`TechnicalIndicator`、`SignalRecord` |
| `repository.py` | 仓储层：upsert、load、日期查询辅助 |
| `realtime_repository.py` | 实时表仓储：realtime_bar / realtime_signal |
| `indicators.py` | 技术指标计算与批量刷新 |

**边界**：数据库交互的唯一真源；业务层通过 `session_scope()` 进入。

### 2.6 `strategy_engine/` — 策略引擎层

| 文件 | 职责 |
|------|------|
| `base.py` | 策略协议：`Strategy`（单标的）、`CrossSectionalStrategy`（横截面）、`Signal` 枚举 |
| `library.py` | 策略注册表：`build_strategy_specs()`、20 个策略实例化、分组元数据 |
| `ma_trend.py` | 双均线策略 |
| `rsrs_timing.py` | RSRS 择时策略 |
| `etf_rotation.py` | ETF 轮动策略（横截面） |
| `multifactor.py` | 多因子轮动策略（横截面） |

**边界**：策略只接收 DataFrame，返回 `Signal`；不访问数据库/网络/文件。

### 2.7 `signal_service/` — 信号服务层

| 文件 | 职责 |
|------|------|
| `signal_generator.py` | 兼容旧日频信号入口 |
| `eod_generator.py` | 多周期 EOD 信号生成（D/W/M） |
| `intraday_generator.py` | 盘中低频信号生成 |
| `secondary_validation.py` | 二次验证闸门：7 条经验规则量化检查 |
| `summary_view.py` | 汇总看板：summary / group / top / push 四类产物 |
| `preclose_decision.py` | 收盘前决策分析 |
| `daily_conclusion_report.py` | 每日长线/短线简明结论 |
| `data_gap_report.py` | 数据缺口诊断报告 |
| `strategy_matrix_report.py` | 全量策略矩阵 Excel 报告 |
| `symbol_meta.py` | 信号表中文名补全 |
| `analysis.py` | 旧版信号分析辅助 |

**边界**：接收信号表和市场数据，输出报告；不直接访问调度状态。

### 2.8 `scheduler/` — 调度层

| 文件 | 职责 |
|------|------|
| `jobs.py` | 收盘批任务与导出管线编排 |
| `intraday_runner.py` | 盘中低频循环执行器 |
| `run_daily.py` | APScheduler 启动入口 |

**边界**：只编排，不承载策略/验证/打分细节。

### 2.9 `web_ui/` — Web 展示层

| 文件 | 职责 |
|------|------|
| `app.py` | FastAPI 路由：/、/api/health、/api/dashboard、/api/dashboard/refresh |
| `dashboard_service.py` | 快照拼装、行情回退、refresh 行为 |
| `static/dashboard.html` | 前端页面：双列面板、表格、状态翻译 |

**边界**：消费 `reports/` 下的产物，不直接查询数据库。

### 2.10 `backtest_engine/` — 回测层

| 文件 | 职责 |
|------|------|
| `backtest_runner.py` | 回测主入口：数据准备、Cerebro 运行、指标提取 |
| `strategy_adapter.py` | Backtrader 策略适配器（当前仅 MA） |
| `report.py` | HTML 报告生成 |

**边界**：离线回测，独立于实时/调度主链路。

### 2.11 `tests/` — 测试层

| 文件模式 | 覆盖范围 |
|----------|----------|
| `test_strategies.py` | 策略库行为 |
| `test_strategy_library.py` | 注册表与分组 |
| `test_signal_summary.py` | 汇总看板 |
| `test_secondary_validation.py` | 二次验证规则 |
| `test_scheduler_jobs.py` | 调度管线 |
| `test_runtime_config.py` | 配置加载 |
| `test_trading_calendar.py` | 交易日历语义 |
| `test_preclose_decision.py` | 收盘前决策 |
| `test_intraday_runner.py` | 盘中循环 |
| `test_daily_conclusion_report.py` | 每日结论 |
| `test_data_gap_report.py` | 数据缺口 |
| `test_strategy_matrix_report.py` | 策略矩阵 |
| `test_dashboard_service.py` | Dashboard 服务 |
| `test_dashboard_app.py` | Dashboard API |
| `test_fetch_etf.py` | ETF 抓取兼容 |
| `test_main.py` | CLI 命令与日期解析 |

---

## 3. 模块依赖关系

```
config → core → data_service → data_storage → strategy_engine → signal_service → scheduler/web_ui
         ↑___________________________________________________________↑
         (trading_calendar 被 signal_service / scheduler 广泛使用)

backtest_engine ← data_storage (只读，数据由调用方准备)
```

**关键原则**：
- 上层可依赖下层，下层不依赖上层
- `core/` 可被任何层依赖，但 `core/` 不依赖任何业务层
- `config/` 被所有层依赖

---

*最后更新：2026-06-12 — 初始化模块基线*
