# 模式知识基线 (Patterns Baseline)

> 本文件记录 Quant System 团队固化的编码范式与设计模式。
> 更新原则：仅追加/定向修改，禁止全量重写。

---

## 1. 项目通用范式

### 1.1 配置加载模式

```python
# config/settings.py 为唯一装配入口
from config.settings import load_runtime_config, load_universe_config

# 使用时直接调用，不自行拼 TOML 路径
runtime = load_runtime_config()
universe = load_universe_config()
```

**约束**：
- 业务模块不直接拼 TOML 路径或环境变量名
- 新增配置项必须同步补 `RuntimeConfig` dataclass、`load_runtime_config()`、测试

### 1.2 数据库会话模式

```python
from data_storage.database import session_scope

with session_scope() as session:
    data = load_market_prices(session, symbol=symbol, limit=limit)
```

**约束**：
- 业务层通过 `session_scope()` 进入数据库
- 不在模型层写业务逻辑
- 批量写入用 PostgreSQL `pg_insert(...).on_conflict_do_update(...)`

### 1.3 DataFrame 层间交换模式

```python
# 默认列名契约
columns = ["date", "open", "high", "low", "close", "volume", "symbol"]

# 归一化函数统一处理中英文列名与索引日期
from data_service.normalize import normalize_ohlcv
```

**约束**：
- 层间交换格式统一为 `pandas.DataFrame`
- 改动 `normalize_ohlcv` 输出契约时，同步更新仓储、指标、测试

---

## 2. 策略引擎范式

### 2.1 单标的策略模式

```python
from strategy_engine.base import Strategy, Signal, has_minimum_rows

class MyStrategy(Strategy):
    name = "my_strategy"

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        if not has_minimum_rows(data, rows=20):
            return Signal.HOLD
        # ... 计算逻辑 ...
        return Signal.BUY  # or SELL / HOLD
```

**约束**：
- 必须满足最小样本要求（复用 `has_minimum_rows()`）
- 输入默认按 `date` 可排序；若依赖时序，先显式 `sort_values("date")`
- 只返回 `Signal` 枚举，不返回字符串或其他私有协议
- 不访问数据库、文件系统或网络

### 2.2 横截面策略模式

```python
from strategy_engine.base import CrossSectionalStrategy, Signal

class MyCrossStrategy(CrossSectionalStrategy):
    name = "my_cross_strategy"

    def generate_signals(self, data_by_symbol: Mapping[str, pd.DataFrame]) -> dict[str, Signal]:
        # ... 跨标的比较逻辑 ...
        return {symbol: Signal.BUY for symbol in selected}
```

**约束**：
- 返回 `symbol -> Signal` 映射
- 同样禁止访问外部资源

### 2.3 策略注册模式

```python
# 必须在 library.py 的 build_strategy_specs() 中注册
# 否则 CLI/信号生成不会发现它
from strategy_engine.library import StrategySpec

specs = [
    StrategySpec(name="MA_strategy", engine=MATrendStrategy(), mode="single", ...),
    StrategySpec(name="ETF_rotation_strategy", engine=ETFRotationStrategy(), mode="cross", universe="etf"),
]
```

**约束**：
- 新策略必须补测试与注册表更新
- 若策略暴露分数，沿用 `last_scores` 或类似字典属性

---

## 3. 信号服务范式

### 3.1 EOD 信号生成模式

```python
from signal_service.eod_generator import generate_eod_signals

signals = generate_eod_signals(
    symbols=symbols,
    etf_symbols=etf_symbols,
    bar_frequencies=("D", "W", "M"),
    save=True,
)
```

**约束**：
- `D/W/M` 信号日期解析优先走仓储层 `load_latest_signal_date*` helper
- 盘中只跑 `supported_mode="intraday"` 的轻量策略

### 3.2 报告导出模式

```python
# 所有主要报告默认覆盖完整 universe
# 缺失标的用 fallback rows 补齐，不靠"有信号才显示"

# 日期语义：
# - 带 --signal-date：历史参考日
# - 不带参数：盘中当天 / 非盘中最近闭市日
```

**约束**：
- `preclose` / `daily_conclusion` / `data_gaps` / `strategy_matrix` 必须完整覆盖
- 缺少行情时，报告输出必须显式中性化：`NO_DATA`、`INSUFFICIENT_DATA`、`HOLD_OBSERVE`
- 不要泄露旧 summary 残留结论

### 3.3 二次验证模式

```python
from signal_service.secondary_validation import secondary_validate_signals_csv

# 接收信号表和市场数据，不直接访问调度状态
result = secondary_validate_signals_csv(signals_path, market_data)
```

**约束**：
- 后处理层，面向日频上下文
- 不依赖盘中 `datetime` 粒度假设

---

## 4. 调度范式

### 4.1 批处理管线模式

```python
# scheduler/jobs.py
# 只编排，不承载业务细节

def run_eod_pipeline(bar_frequencies=("D", "W", "M")):
    market_result = update_market_job()
    indicator_rows = calc_indicators_job()
    signal_rows = generate_eod_signals_job(bar_frequencies)
    # ... 导出 ...
```

**约束**：
- 调度层只编排，不写策略/验证/打分细节
- 新增独立导出命令时，同步更新 `main.py`、README、说明文档与测试

### 4.2 盘中循环模式

```python
# scheduler/intraday_runner.py
# 只在交易时段执行，时段判断统一走 core.trading_calendar.is_trading_session()
```

**约束**：
- 输出保持脚本友好的 JSON
- 单个 symbol 抓取失败不整体中断

---

## 5. Dashboard 范式

### 5.1 快照消费模式

```python
# web_ui/dashboard_service.py
# 混合消费 summary / intraday / preclose / daily_conclusion 四类产物
```

**约束**：
- 改任一导出文件名或字段时，同步核对 `dashboard_service.py`
- 行情面板允许 `preclose` 覆盖更旧的 `realtime_bar`，但 source 必须明确标注
- 收盘后榜单按最近闭市日 `daily close` 排序，不让 `preclose snapshot` 继续覆盖
- refresh 必须同时更新 `summary` 与 `daily_conclusion`

---

## 6. 测试范式

### 6.1 单元测试模式

```python
# 继续使用 test_*.py 命名
# 适配 python -m unittest discover -s tests -p "test_*.py"

# 优先写小而确定的单元测试
# 大量使用合成 DataFrame，避免依赖外部行情网络
```

**约束**：
- 改排序、推送数量、返回字段、时间窗口时，同步更新对应测试
- 涉及导出链路时，断言关键行数、sheet 名称或路径字段
- 涉及 dashboard refresh 时，同时断言 `summary` 与 `daily_conclusion` 侧效应
- 涉及 CLI 日期参数时，同时断言历史模式与无参数默认语义

---

## 7. 错误处理模式

### 7.1 批量容错模式

```python
# 单个 symbol 失败不拖垮整批
errors = []
for symbol in symbols:
    try:
        result = process(symbol)
    except Exception as e:
        errors.append(f"{symbol}: {e}")
        continue
```

**约束**：
- 吞错时至少保留可追踪上下文（错误列表）
- 不要在抓取层直接写数据库（异常时数据不完整）

---

*最后更新：2026-06-12 — 初始化模式基线*
