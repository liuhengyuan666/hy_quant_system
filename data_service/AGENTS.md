# DATA SERVICE NOTES

## OVERVIEW
- 这里负责外部行情抓取与字段标准化；输出必须是可直接入库的统一 OHLCV 表。

## WHERE TO LOOK
- 指数抓取：`fetch_index.py`
- ETF 抓取：`fetch_etf.py`
- 字段归一：`normalize.py`
- 批量同步入口：`sync_market.py`

## CONVENTIONS
- 对外部源保持薄封装；抓取函数只负责获取原始数据并交给 `normalize_ohlcv`。
- 统一返回列：`date/open/high/low/close/volume/symbol`。
- `fetch_*_batch` 允许跳过失败标的；保持批处理可继续执行。
- 归一化函数必须兼容中英文列名与索引日期场景。

## ANTI-PATTERNS
- 不要在抓取函数里直接写数据库。
- 不要返回未标准化列名。
- 不要默默改 `volume` 语义；当前可能来自成交量或成交额候选，改动前先统一全链路。
