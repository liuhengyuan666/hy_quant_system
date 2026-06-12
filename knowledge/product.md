# 产品知识基线 (Product Baseline)

> 本文件记录 Quant System 的核心业务定位、领域规则与价值主张。
> 更新原则：仅追加/定向修改，禁止全量重写。

---

## 1. 系统定位

**Quant System** 是一个面向 A 股指数 / ETF 的量化分析与信号平台，基于 Python 技术栈构建，核心目标是为投资者提供：

- **盘后多周期分析**（日 / 周 / 月）
- **盘中低频巡检**（默认 5 分钟 bars）
- **收盘前决策辅助**（14:45 自动触发）
- **策略矩阵与每日结论报告**
- **本地实时 Dashboard**

---

## 2. 核心业务领域

### 2.1 分析链路

系统维护三条独立分析链路：

| 链路 | 频率 | 触发时机 | 输出 |
|------|------|----------|------|
| `EOD` | 日 / 周 / 月 | 盘后批处理 | 多周期信号、策略矩阵、每日结论 |
| `INTRADAY` | 5 分钟 bars | 盘中循环（09:30-15:00） | 实时信号、推送候选 |
| `PRE-CLOSE` | 盘中快照 | 14:45 触发 | 收盘前决策建议 |

### 2.2 信号体系

- **核心信号值**：`BUY` / `SELL` / `HOLD`（三态枚举，严禁自由扩展）
- **策略数量**：20 个已注册策略，分短线（12 个）与长线（8 个）
- **分组共识**：按策略哲学分组（趋势跟随、均值回归、动量、波动突破、成交量、资产配置、未分类），通过权重配置影响最终结论

### 2.3 报告体系

| 报告 | 目录 | 核心用途 |
|------|------|----------|
| Signal Summary | `reports/summary/` | 汇总看板、分组、Top 候选、推送 |
| Preclose | `reports/preclose/` | 收盘前买卖点判断 |
| Strategy Matrix | `reports/strategy_matrix/` | 标的 × 策略 全量矩阵 Excel |
| Daily Conclusion | `reports/daily_conclusion/` | 每日长线/短线简明结论 |
| Data Gaps | `reports/data_gaps/` | 数据缺口诊断 |

---

## 3. 关键业务规则

### 3.1 标的池规则

- 分析范围由 `config/universe.toml` 严格定义
- 指数代码 + ETF 代码双列表维护
- 所有主要报告必须覆盖完整 universe，缺失标的用 `NO_DATA` 补齐

### 3.2 日期语义规则

- **历史模式**：`--signal-date YYYYMMDD` 明确指定参考日
- **实时模式**：无参数时，盘中用当天，盘后回退到最近闭市日
- `--signal-date` 与 `--use-intraday-snapshot` 互斥

### 3.3 数据状态规则

| 状态 | 含义 | 处理 |
|------|------|------|
| `NO_DATA` | 无历史行情 | 策略无法运行，结论中性化 |
| `MISSING` | 应有信号但缺失 | 排查生成链路 |
| `NOT_RUN` | 该模式未运行策略 | 正常 |
| `N/A` | 策略不适用于该标的 | 正常 |

### 3.4 分组共识 Tie-break 规则

- 仅作用于两类场景：**长短线冲突** 或 **长短线都 HOLD**
- 需满足最小分组数（`min_groups=2`）、最小分数、最小置信度阈值
- 改判结果输出到 `hypothesis_consensus_action` / `hypothesis_tiebreak_applied`

---

## 4. 数据源策略

| 数据类型 | 优先源 | 兜底源 |
|----------|--------|--------|
| 大陆指数日线 | AKShare | - |
| 大陆 ETF 日线 | Eastmoney (AKShare) | - |
| 大陆指数/ETF 盘中 5min | pytdx | AKShare |
| 港股指数日线 | AKShare (Sina/EM) | - |
| 港股指数盘中 | Futu OpenAPI / OpenD | 无（保持空 bars） |

---

## 5. 用户价值主张

> "每天收盘后快速知道该看什么、怎么操作"

推荐日常流程：
1. `run-eod-analyze --frequencies D,W,M`
2. 查看 `daily_conclusion_operation_YYYYMMDD.csv`（最简操作视图）
3. 查看 `data_gaps_YYYYMMDD.csv`（排除数据问题）
4. 按需查看 `strategy_matrix_YYYYMMDD.xlsx`（策略细节）

---

*最后更新：2026-06-12 — 初始化产品基线*
