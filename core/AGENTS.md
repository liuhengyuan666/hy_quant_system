# CORE NOTES

## OVERVIEW
- 这里放 `EOD` / `INTRADAY` 共用的时间、模式与交易日历辅助；应保持轻量、纯函数优先。

## WHERE TO LOOK
- 改上海时区当前时间：`clock.py`
- 改模式枚举或共享模式语义：`modes.py`
- 改交易日、交易时段、收盘前窗口判断：`trading_calendar.py`

## CONVENTIONS
- 所有时区相关逻辑统一基于 `Asia/Shanghai`；不要在调用侧重复创建时区常量。
- `trading_calendar.py` 负责回答“什么时候运行”，不负责“运行什么业务”。
- 新增时间窗口判断时，优先补纯 helper，再由 `scheduler/` 编排调用。
- 日期与时间辅助尽量保持无数据库依赖、无 AKShare 依赖，便于单元测试。

## ANTI-PATTERNS
- 不要在 `core/` 引入 `data_service`、`data_storage`、策略评分等重业务依赖。
- 不要把盘中/盘后特定规则写死在调度层，先抽到这里的通用时间 helper。
- 不要混用 naive datetime 与上海时区 datetime。
