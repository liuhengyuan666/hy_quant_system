# CONFIG NOTES

## OVERVIEW
- 这里集中放运行时配置、数据库连接、标的池与符号展示映射；`settings.py` 负责“环境变量优先，其次 TOML”加载。

## WHERE TO LOOK
- 改数据库连接或默认值：`settings.py`、`br_db.toml`
- 改盘中/收盘前时段与频率：`runtime.toml`
- 改指数/ETF 标的范围：`universe.toml`
- 改 CSV 展示名称与代码映射：`symbol_meta.toml`

## CONVENTIONS
- 保持 `settings.py` 为唯一配置装配入口；其他模块优先调用 `load_*_config()`。
- `runtime.toml` 时间字段保持 `HH:MM` 字符串格式；交易时段语义交给 `core/trading_calendar.py`。
- 数据库敏感信息继续走环境变量覆盖，不把真实凭据写回仓库默认 TOML。
- `universe.toml` 以“指数 + ETF”双列表维护；新增标的时同步考虑 `symbol_meta.toml`。
- `symbol_meta.toml` 的 `display_symbol` 面向最终导出，保持稳定，不随临时分析需求频繁改名。

## ANTI-PATTERNS
- 不要在业务模块里直接拼 TOML 路径或环境变量名，统一下沉到 `settings.py`。
- 不要把运行时默认值散落到多个模块；默认值改动时同步更新 `settings.py` 与对应测试。
- 不要新增配置项却不补 `RuntimeConfig` / `load_runtime_config()` / 测试。
- 不要把策略、调度或导出逻辑塞进 `config/`。
