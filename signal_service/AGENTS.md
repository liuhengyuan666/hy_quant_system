# SIGNAL SERVICE NOTES

## OVERVIEW
- 这里负责 `EOD`/盘中信号生成、二次验证、汇总看板与候选导出；是“研究结果到可操作结论”的最后一层。

## WHERE TO LOOK
- 兼容旧日频入口：`signal_generator.py`
- 多周期 `EOD`：`eod_generator.py`
- 盘中信号：`intraday_generator.py`
- 二次验证规则：`secondary_validation.py`
- 看板/分组/Top/变化推送：`summary_view.py`
- 符号名补全：`symbol_meta.py`

## CONVENTIONS
- `EOD` 逻辑默认基于最近交易日；`D/W/M` 频率在 `summary_view` 合并后再做排序。
- 盘中默认只跑 `supported_mode="intraday"` 的轻量策略；不要在这里绕过注册表筛选。
- `secondary_validation` 是后处理层；它接收信号表和市场数据，不直接访问调度状态。
- `summary_view` 导出必须保持四类产物同步：`signal_summary`、`signal_group_summary`、`signal_top_candidates`、`signal_push_candidates`。
- `push_candidates` 当前是“本轮相对上一轮变化最大的前三个”；改排序逻辑时要一起更新测试。

## ANTI-PATTERNS
- 不要在 `summary_view.py` 里重新实现数据库查询协议；读数仍通过仓储层或现有 helper。
- 不要让 `secondary_validation` 依赖盘中 `datetime` 粒度假设；它目前面向日频上下文。
- 不要只改 `summary` 主表而漏掉 `group/top/push` 三份导出。
- 不要新增自由格式信号值；仍然使用 `BUY/SELL/HOLD` 和受控的 `dashboard_action` / `secondary_action`。
