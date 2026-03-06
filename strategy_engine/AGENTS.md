# STRATEGY ENGINE NOTES

## OVERVIEW
- 这里是策略定义与注册中心；单标的策略实现 `Strategy.generate_signal()`，横截面策略实现 `CrossSectionalStrategy.generate_signals()`。

## WHERE TO LOOK
- 公共协议：`base.py`
- 简单双均线：`ma_trend.py`
- RSRS：`rsrs_timing.py`
- ETF 轮动：`etf_rotation.py`
- 多因子轮动：`multifactor.py`
- 全量策略注册：`library.py`

## CONVENTIONS
- 新策略必须先满足最小样本要求；复用 `has_minimum_rows()`。
- 输入默认是按 `date` 可排序的 DataFrame；若算法依赖时序，先显式 `sort_values("date")`。
- 单标的策略返回 `BUY/SELL/HOLD` 三态；横截面策略返回 `symbol -> Signal` 映射。
- 新策略要在 `library.py` 的 `build_strategy_specs()` 注册，否则 CLI/信号生成不会发现它。
- 若策略暴露分数，沿用 `last_scores` 或类似字典属性，便于信号层抽取 `score`。

## ANTI-PATTERNS
- 不要在策略里访问数据库、文件系统或网络。
- 不要让策略返回字符串以外的私有协议；统一使用 `Signal`。
- 不要只新增策略类却漏掉测试与注册表更新。
