# 术语知识基线 (Glossary Baseline)

> 本文件记录 Quant System 的项目专属领域黑话与统一术语表。
> 更新原则：仅追加/定向修改，禁止全量重写。

---

## 1. 分析模式术语

| 术语 | 英文 | 含义 |
|------|------|------|
| EOD | End of Day | 盘后/日频分析模式 |
| INTRADAY | Intraday | 盘中低频巡检模式 |
| PRE-CLOSE | Pre-Close | 收盘前决策分析模式 |
| 多周期 | Multi-Frequency | 同时分析 D(日)/W(周)/M(月) 三个周期 |

## 2. 信号与状态术语

| 术语 | 含义 |
|------|------|
| BUY | 倾向买入（信号值） |
| SELL | 倾向卖出（信号值） |
| HOLD | 倾向观望（信号值） |
| NO_DATA | 无历史行情，无法分析 |
| MISSING | 应有信号但缺失，需排查链路 |
| NOT_RUN | 该模式下策略未运行 |
| N/A | 策略不适用于该标的 |

## 3. 策略分组术语（Market Hypothesis）

| 术语 | 英文 | 含义 |
|------|------|------|
| 趋势跟随 | trend_following | 基于趋势判断的策略组 |
| 均值回归 | mean_reversion | 基于反转判断的策略组 |
| 动量 | momentum | 基于动量判断的策略组 |
| 波动突破 | volatility_breakout | 基于波动率突破的策略组 |
| 成交量 | volume_based | 基于量能判断的策略组 |
| 资产配置 | cross_asset_allocation | ETF轮动/多因子等组合策略组 |
| 未分类 | uncategorized | 未归入上述分组的策略 |

## 4. 报告产物术语

| 术语 | 含义 |
|------|------|
| Signal Summary | 信号汇总看板 |
| Signal Group Summary | 按分组聚合的信号统计 |
| Top Candidates | 趋势评分最高的标的 |
| Push Candidates | 本轮相对上一轮变化最大的前3个候选 |
| Strategy Matrix | 标的 × 策略 的全量对应矩阵 |
| Daily Conclusion | 每日长线/短线简明结论 |
| Operation View | 每日结论的简化操作视图 |
| Data Gaps | 数据缺口诊断报告 |
| Preclose | 收盘前决策报告 |

## 5. 数据源术语

| 术语 | 含义 |
|------|------|
| AKShare | 开源财经数据接口库 |
| pytdx | 通达信数据接口（优先用于盘中） |
| Futu OpenAPI | 富途证券开放接口（港股实时可选） |
| OpenD | 富途本地数据网关 |
| Eastmoney | 东方财富数据接口（ETF日线） |

## 6. 技术术语

| 术语 | 含义 |
|------|------|
| OHLCV | Open/High/Low/Close/Volume 标准行情字段 |
| Upsert | Insert or Update（PostgreSQL ON CONFLICT DO UPDATE） |
| session_scope | SQLAlchemy 事务上下文管理器 |
| bar_frequency | K线周期：D(日)/W(周)/M(月)/5(5分钟) |
| lookback_bars | 盘中策略回看的历史bar数量 |
| tiebreak | 长短线冲突或双HOLD时的分组共识改判机制 |

## 7. 运行时术语

| 术语 | 含义 |
|------|------|
| 最近闭市日 | latest_closed_trading_date |
| 交易时段 | trading_session（09:30-11:30, 13:00-15:00） |
| 收盘前窗口 | preclose_window（14:45-15:00） |
| 盘中版 | 基于当天实时数据的分析版本 |
| 盘后版 | 基于最近闭市日收盘价的分析版本 |

---

*最后更新：2026-06-12 — 初始化术语基线*
