# DATA STORAGE NOTES

## OVERVIEW
- 这里维护数据库连接、表模型、upsert 仓储与指标落库；是运行时状态的唯一真源。

## WHERE TO LOOK
- 会话与引擎：`database.py`
- ORM 模型：`models.py`
- upsert/load：`repository.py`
- 指标刷新：`indicators.py`

## CONVENTIONS
- 保持 `session_scope()` 事务边界；业务层通过它进入数据库。
- 新表优先补 `UniqueConstraint` 和高频查询索引，风格参考现有三个模型。
- 批量写入沿用 PostgreSQL `pg_insert(...).on_conflict_do_update(...)` 模式。
- 日期与数值清洗统一走仓储层辅助函数；不要在上层重复实现。

## ANTI-PATTERNS
- 不要在模型层写业务逻辑。
- 不要绕过仓储层直接手写重复的 upsert 清洗。
- 不要让指标刷新依赖单个 symbol 的异常中断整批执行。
