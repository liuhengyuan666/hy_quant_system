# SIGNAL SERVICE NOTES

## OVERVIEW
- 这里负责 `EOD` / 盘中信号生成、二次验证、汇总看板，以及面向投资者的收盘前决策、日报、数据缺口、策略矩阵导出。

## WHERE TO LOOK
- 兼容旧日频入口：`signal_generator.py`
- 多周期 `EOD`：`eod_generator.py`
- 盘中信号：`intraday_generator.py`
- 二次验证规则：`secondary_validation.py`
- 汇总看板 / 分组 / Top / Push：`summary_view.py`
- 收盘前决策：`preclose_decision.py`
- 每日长短线结论：`daily_conclusion_report.py`
- 数据缺口诊断：`data_gap_report.py`
- 全量策略矩阵：`strategy_matrix_report.py`
- 符号名补全：`symbol_meta.py`

## CONVENTIONS
- `EOD` 逻辑默认基于最近交易日；`D/W/M` 信号日期解析优先走仓储层 `load_latest_signal_date*` helper。
- 盘中默认只跑 `supported_mode="intraday"` 的轻量策略；不要在这里绕过注册表筛选。
- `secondary_validation` 是后处理层；它接收信号表和市场数据，不直接访问调度状态。
- `summary_view` 导出必须保持四类产物同步：`signal_summary`、`signal_group_summary`、`signal_top_candidates`、`signal_push_candidates`。
- `push_candidates` 是“本轮相对上一轮变化最大的前三个”；改排序逻辑时要一起更新测试。
- `preclose` / `daily_conclusion` / `data_gaps` / `strategy_matrix` 默认覆盖完整 `universe`；缺失标的用 fallback rows 补齐，不靠“有信号才显示”。
- `daily_conclusion_report.py` 现在同时支持“最近闭市日版”和“显式 `intraday_ts` 的当天盘中版”；改日期解析时要保护这两种语义。
- 策略分组共识走 `market_hypothesis` 元数据；改注册表分类、分组权重或 tie-break 规则时要同步看 `daily_conclusion`、`strategy_matrix`、dashboard 和文档。
- 缺少行情时，报告层输出必须显式中性化：例如 `NO_DATA`、`INSUFFICIENT_DATA`、`HOLD_OBSERVE`、`NEUTRAL`，不要泄露旧 summary 残留值。
- Excel 导出依赖 `xlsxwriter`；缺依赖时抛明确错误，不做静默降级。

## ANTI-PATTERNS
- 不要在 `summary_view.py` 里重新实现数据库查询协议；读数仍通过仓储层或现有 helper。
- 不要让 `secondary_validation` 依赖盘中 `datetime` 粒度假设；它目前主要面向日频上下文。
- 不要只改 `summary` 主表而漏掉 `group/top/push` 三份导出。
- 不要新增自由格式信号值；仍然使用 `BUY/SELL/HOLD` 和受控的 `dashboard_action` / `secondary_action`。
- 不要让历史 CSV 读回来的 `symbol` dtype 与当前汇总表不一致；涉及 merge/concat 时统一为字符串。
- 不要让新报告只覆盖“当前有信号的 symbol”；导出面向配置标的池时必须确认完整覆盖行数。
- 不要把 `daily_conclusion` 的 `signal_date` 强制绑定到最新 EOD D 日期；盘中版需要允许 `signal_date=今天` 同时 `signal_date_d=最近闭市日`。
