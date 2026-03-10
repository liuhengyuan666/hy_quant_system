# WEB UI NOTES

## OVERVIEW
- 这里负责 FastAPI dashboard：读取最新报告快照、行情概览、分组共识面板，以及浏览器刷新接口。

## WHERE TO LOOK
- 路由与静态页挂载：`app.py`
- 快照拼装、行情回退、refresh 行为：`dashboard_service.py`
- 页面布局、双列面板、表格列名与状态翻译：`static/dashboard.html`

## CONVENTIONS
- dashboard 优先展示最新快照，但会混合消费 `summary`、`intraday`、`preclose`、`daily_conclusion` 四类产物；改文件名前缀或目录时必须同步更新服务层。
- 行情面板允许使用 `preclose` 快照覆盖时间更旧的 `realtime_bar`；如果仍是旧盘中数据，source 必须明确标成 `Stale Intraday` 类语义。
- `Hypothesis Focus` 依赖 `daily_conclusion_*.csv`；refresh 链路必须保证导出链同步产出日报，否则该面板会空。
- 页面文案继续保持中英对照；新增字段时同步补 `COLUMN_LABELS` / `VALUE_LABELS`。
- 桌面端主网格默认最多两列；除非明确需要，不要再回退成三列挤压表格。

## ANTI-PATTERNS
- 不要只改前端 HTML 而不更新 `dashboard_service.py`；数据契约不一致会直接出现空表。
- 不要把昨天的行情继续标成 `实时快照 / Intraday`。
- 不要让 refresh 只更新 `summary` 而漏掉 `daily_conclusion`；否则分组共识面板会失真或为空。
- 不要随意删除 `quote_source`、`updated_at`、`hypothesis_summary_text` 这类解释字段；它们是看板可读性的核心。

## COMMANDS
- 本地启动：`python main.py run-dashboard --host 127.0.0.1 --port 8000`
- API 健康检查：`http://127.0.0.1:8000/api/health`
- 快照接口：`http://127.0.0.1:8000/api/dashboard`
- 手动刷新：`POST http://127.0.0.1:8000/api/dashboard/refresh`
