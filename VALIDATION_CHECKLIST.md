# 本地验证清单

## 0. 目标

验证以下改造是否在本地生效：

- `EOD` 多周期分析：`D / W / M`
- `INTRADAY` 低频盘中巡检
- `secondary_validation` 二次验证
- `summary / group / top / push` 看板导出
- `push candidates` 仅保留变化最大的前 `3` 个

---

## 1. 环境准备

### 1.1 进入项目目录

```powershell
cd F:\ai_area\quant-system
```

**预期结果**

- 当前目录为 `F:\ai_area\quant-system`

### 1.2 启动数据库

```powershell
docker compose up -d
```

**预期结果**

- PostgreSQL 容器正常启动
- `docker compose ps` 可看到相关服务为 `Up`

### 1.3 安装依赖

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**预期结果**

- 依赖安装完成
- 不出现缺失 `akshare`、`sqlalchemy`、`pandas`、`apscheduler` 等核心包的报错

### 1.4 检查配置

重点确认：

- 数据库配置：`config/br_db.toml`
- 标的池：`config/universe.toml`
- 名称映射：`config/symbol_meta.toml`
- 盘中参数：`config/runtime.toml`

**预期结果**

- 数据库连接信息可用
- `runtime.toml` 中盘中参数合理，例如：
  - `enabled = true`
  - `interval_minutes = 5`
  - `bar_frequency = "5"`

---

## 2. 初始化数据库

### 2.1 初始化表结构

```powershell
.\.venv\Scripts\python.exe main.py init-db
```

**预期结果**

- 控制台输出 `database initialized`
- 数据库中存在或已补齐以下表：
  - `market_price`
  - `technical_indicator`
  - `signal_record`
  - `realtime_bar`
  - `intraday_signal_record`
- 若数据库是旧版本，`init-db` 会自动为 `signal_record` 补齐 `mode`、`bar_frequency` 等兼容字段，并升级对应唯一索引/约束

> 建议：如本地数据库里已经有旧版本表结构，优先使用新库验证，避免旧表缺列。

---

## 3. 历史数据准备

### 3.1 拉取历史数据

```powershell
.\.venv\Scripts\python.exe main.py sync-data --start-date 20240101
```

**预期结果**

- 控制台返回 JSON
- 至少包含类似以下信息：
  - `rows`
  - 或按指数 / ETF 分组的写入统计
- 数据库 `market_price` 表中有最新日频行情数据

### 3.2 计算技术指标

```powershell
.\.venv\Scripts\python.exe main.py calc-indicators
```

**预期结果**

- 控制台输出形如：

```json
{"rows": 1234}
```

- `technical_indicator` 表中有新增或更新记录

---

## 4. 验证盘后多周期分析（推荐先做）

### 4.1 执行盘后分析主流程

```powershell
.\.venv\Scripts\python.exe main.py run-eod-analyze
```

**预期结果**

- 控制台返回 JSON
- 返回字段应至少包含：
  - `market_rows`
  - `indicator_rows`
  - `signal_counts`
  - `analysis`
  - `secondary_validation`
  - `summary_path`
  - `push_path`

### 4.2 检查 `signal_counts`

**预期结果**

- `signal_counts` 中应包含：
  - `D`
  - `W`
  - `M`

例如：

```json
"signal_counts": {"D": 20, "W": 20, "M": 20}
```

### 4.3 检查二次验证输出

**预期结果**

- `secondary_validation` 是按频率分组的对象
- 每个频率下应包含：
  - `review_score`
  - `review_gate`
  - `rule_evaluations`
  - `symbol_reviews`

### 4.4 检查生成文件

应存在：

- `reports\eod\signals_d_*.csv`
- `reports\eod\signals_w_*.csv`
- `reports\eod\signals_m_*.csv`
- `reports\summary\signal_summary_*.csv`
- `reports\summary\signal_group_summary_*.csv`
- `reports\summary\signal_top_candidates_*.csv`
- `reports\summary\signal_push_candidates_*.csv`

**预期结果**

- 文件均存在
- `signal_push_candidates_*.csv` 最多只包含 `3` 条候选

---

## 5. 验证统一看板导出

### 5.1 单独导出看板

```powershell
.\.venv\Scripts\python.exe main.py export-signal-summary
```

**预期结果**

- 控制台输出 JSON
- 至少包含：
  - `summary_path`
  - `push_path`

例如：

```json
{
  "summary_path": "reports\\summary\\signal_summary_20260307_1035.csv",
  "push_path": "reports\\summary\\signal_push_candidates_20260307_1035.csv"
}
```

### 5.2 检查主看板列

打开 `signal_summary_*.csv`，确认至少存在以下列：

- `conviction_rank`
- `symbol`
- `display_symbol`
- `name`
- `asset_type`
- `bucket`
- `eod_d`
- `eod_w`
- `eod_m`
- `intraday`
- `eod_bias`
- `alignment`
- `primary_action`
- `secondary_action`
- `secondary_confidence`
- `review_gate`
- `review_score`
- `eod_score`
- `intraday_score`
- `secondary_score`
- `composite_score`
- `dashboard_action`

### 5.3 检查分组看板列

打开 `signal_group_summary_*.csv`，确认至少存在：

- `bucket`
- `asset_type`
- `count`
- `avg_composite_score`
- `avg_secondary_confidence`
- `aligned_count`
- `priority_buy_count`
- `priority_sell_count`
- `top_symbol`

### 5.4 检查候选榜单列

打开 `signal_top_candidates_*.csv`，确认至少存在：

- `direction`
- `conviction_rank`
- `symbol`
- `display_symbol`
- `name`
- `bucket`
- `composite_score`
- `dashboard_action`
- `alignment`
- `eod_bias`
- `intraday`
- `secondary_action`
- `secondary_confidence`
- `review_gate`

### 5.5 检查推送清单是否只保留前三个

打开 `signal_push_candidates_*.csv`

**预期结果**

- 行数 `<= 3`
- 至少包含：
  - `push_rank`
  - `symbol`
  - `dashboard_action`
  - `previous_dashboard_action`
  - `score_delta`
  - `change_score`
  - `change_reason`

---

## 6. 验证盘中模式

> 建议在北京时间交易时段内验证：`09:30-11:30`、`13:00-15:00`

### 6.1 单次盘中巡检

```powershell
.\.venv\Scripts\python.exe main.py run-intraday-once
```

**预期结果**

- 控制台返回 JSON
- 至少包含：
  - `ts`
  - `bar_frequency`
  - `bar_rows`
  - `signal_rows`
  - `export_path`
  - `summary_path`
  - `push_path`

### 6.2 连续盘中巡检

```powershell
.\.venv\Scripts\python.exe main.py run-intraday --iterations 3
```

**预期结果**

- 连续打印 `3` 次 JSON 结果
- 每次结果都有 `summary_path` 和 `push_path`
- `reports\summary\` 下出现新的 `signal_summary_*` 和 `signal_push_candidates_*`

### 6.3 检查实时表

**预期结果**

- `realtime_bar` 表中有新数据
- `intraday_signal_record` 表中有新数据

---

## 7. 验证旧链路兼容性

### 7.1 执行旧入口

```powershell
.\.venv\Scripts\python.exe main.py run-and-analyze
```

**预期结果**

- 旧链路仍可运行
- 返回结果中包含：
  - `analysis`
  - `secondary_validation`

> 说明：旧链路仍然是日频单链路；新能力主要集中在 `run-eod-analyze`、`run-intraday` 和 `summary` 导出。

---

## 8. 自动化回归验证

### 8.1 运行单元测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

**预期结果**

- 全部测试通过
- 当前基线应为 `31` 项测试通过

### 8.2 运行编译检查

```powershell
.\.venv\Scripts\python.exe -m compileall main.py signal_service scheduler tests
```

**预期结果**

- 编译成功
- 无语法错误

---

## 9. 最终验收标准

当以下条件全部满足时，可认为本地验证通过：

- `run-eod-analyze` 成功返回 `analysis + secondary_validation + summary_path + push_path`
- `run-intraday-once` 成功返回 `summary_path + push_path`
- `signal_summary / group / top / push` 四类 CSV 都能生成
- `signal_push_candidates_*.csv` 最多只保留 `3` 条
- 单元测试全绿
- 编译检查通过

---

## 10. 如果验证失败，优先排查

1. 数据库未初始化或旧表结构未迁移
2. `config/br_db.toml` 连接错误
3. `config/runtime.toml` 的盘中参数不合理
4. 不在交易时段内执行 `run-intraday`
5. AKShare 接口临时不可用或返回字段变化
6. `reports/summary/` 中没有上一轮 `summary`，导致 `push candidates` 首次只能生成快照型结果
