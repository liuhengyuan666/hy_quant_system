from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import os

import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_CONFIG_PATH = PROJECT_ROOT / "config" / "br_db.toml"
UNIVERSE_CONFIG_PATH = PROJECT_ROOT / "config" / "universe.toml"
SYMBOL_META_CONFIG_PATH = PROJECT_ROOT / "config" / "symbol_meta.toml"
RUNTIME_CONFIG_PATH = PROJECT_ROOT / "config" / "runtime.toml"


@dataclass(frozen=True)
class PostgresConfig:
    mode: str
    hostname: str
    hostport: int
    database: str
    username: str
    userpass: str
    params: list[str]
    charset: str
    prefix: str
    debug: bool

    @property
    def sqlalchemy_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.username}:{self.userpass}"
            f"@{self.hostname}:{self.hostport}/{self.database}"
        )


@dataclass(frozen=True)
class UniverseConfig:
    index_symbols: list[str]
    etf_symbols: list[str]


@dataclass(frozen=True)
class SymbolMeta:
    name: str
    display_symbol: str


@dataclass(frozen=True)
class RuntimeConfig:
    timezone: str
    intraday_enabled: bool
    intraday_interval_minutes: int
    intraday_bar_frequency: str
    intraday_lookback_bars: int
    intraday_window_am_start: str
    intraday_window_am_end: str
    intraday_window_pm_start: str
    intraday_window_pm_end: str
    preclose_enabled: bool
    preclose_trigger_time: str
    preclose_decision_time: str
    preclose_output_dir: str
    hk_realtime_provider: str = "none"
    hk_realtime_futu_host: str = "127.0.0.1"
    hk_realtime_futu_port: int = 11111
    hk_realtime_futu_is_encrypt: bool = False
    hk_realtime_futu_symbol_map: dict[str, str] | None = None


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as file:
        return tomllib.load(file)


def load_postgres_config(config_path: Path | None = None) -> PostgresConfig:
    path = config_path or DB_CONFIG_PATH
    raw = _load_toml(path)
    section = raw.get("br_db", {}).get("connections", {}).get("pgsql", {})

    hostname = os.getenv("QUANT_DB_HOST", section.get("hostname", "127.0.0.1"))
    hostport = int(os.getenv("QUANT_DB_PORT", str(section.get("hostport", "5432"))))
    database = os.getenv("QUANT_DB_NAME", section.get("database", "custom_client"))
    username = os.getenv("QUANT_DB_USER", section.get("username", "root"))
    userpass = os.getenv("QUANT_DB_PASS", section.get("userpass", "111111"))
    debug = os.getenv("QUANT_DB_DEBUG", str(section.get("debug", False))).lower() == "true"

    return PostgresConfig(
        mode=section.get("mode", "Pgsql"),
        hostname=str(hostname),
        hostport=hostport,
        database=str(database),
        username=str(username),
        userpass=str(userpass),
        params=list(section.get("params", [])),
        charset=str(section.get("charset", "Utf8mb4")),
        prefix=str(section.get("prefix", "")),
        debug=debug,
    )


def load_universe_config(config_path: Path | None = None) -> UniverseConfig:
    path = config_path or UNIVERSE_CONFIG_PATH
    raw = _load_toml(path)
    section = raw.get("universe", {})
    return UniverseConfig(
        index_symbols=list(
            section.get(
                "index_symbols",
                [
                    "000300",
                    "000905",
                    "000001",
                    "399006",
                    "399673",
                    "000698",
                    "000688",
                    "000016",
                    "000852",
                    "HSCEI",
                    "HSTECH",
                    "HSAHP",
                ],
            )
        ),
        etf_symbols=list(
            section.get(
                "etf_symbols",
                [
                    "510300",
                    "159915",
                    "513130",
                    "512800",
                    "512000",
                    "512400",
                    "515880",
                    "159611",
                    "515070",
                    "159851",
                ],
            )
        ),
    )


def load_symbol_meta_map(config_path: Path | None = None) -> dict[str, SymbolMeta]:
    path = config_path or SYMBOL_META_CONFIG_PATH
    if not path.exists():
        return {}

    raw = _load_toml(path)
    section = raw.get("symbol_meta", {})

    mapping: dict[str, SymbolMeta] = {}
    for symbol, payload in section.items():
        key = str(symbol)
        if isinstance(payload, dict):
            name = str(payload.get("name", key))
            display_symbol = str(payload.get("display_symbol", key))
        else:
            name = str(payload)
            display_symbol = key
        mapping[key] = SymbolMeta(name=name, display_symbol=display_symbol)

    return mapping


def load_runtime_config(config_path: Path | None = None) -> RuntimeConfig:
    path = config_path or RUNTIME_CONFIG_PATH
    raw = _load_toml(path) if path.exists() else {}
    section = raw.get("runtime", {})
    intraday = section.get("intraday", {})
    preclose = section.get("preclose", {})
    hk_realtime = section.get("hk_realtime", {})
    futu = hk_realtime.get("futu", {})

    interval_minutes = int(intraday.get("interval_minutes", 5))
    if interval_minutes < 1:
        interval_minutes = 1

    lookback_bars = int(intraday.get("lookback_bars", 120))
    if lookback_bars < 20:
        lookback_bars = 20

    hk_provider = str(os.getenv("QUANT_HK_REALTIME_PROVIDER", hk_realtime.get("provider", "none"))).strip().lower() or "none"
    futu_host = str(os.getenv("QUANT_FUTU_HOST", futu.get("host", "127.0.0.1"))).strip() or "127.0.0.1"
    futu_port = int(os.getenv("QUANT_FUTU_PORT", str(futu.get("port", 11111))))
    futu_is_encrypt = str(os.getenv("QUANT_FUTU_IS_ENCRYPT", str(futu.get("is_encrypt", False)))).strip().lower() == "true"

    raw_symbol_map = futu.get("symbol_map", {})
    hk_symbol_map = {
        str(symbol).strip(): str(code).strip()
        for symbol, code in raw_symbol_map.items()
        if str(symbol).strip() and str(code).strip()
    }

    return RuntimeConfig(
        timezone=str(section.get("timezone", "Asia/Shanghai")),
        intraday_enabled=bool(intraday.get("enabled", True)),
        intraday_interval_minutes=interval_minutes,
        intraday_bar_frequency=str(intraday.get("bar_frequency", "5")).strip() or "5",
        intraday_lookback_bars=lookback_bars,
        intraday_window_am_start=str(intraday.get("window_am_start", "09:30")),
        intraday_window_am_end=str(intraday.get("window_am_end", "11:30")),
        intraday_window_pm_start=str(intraday.get("window_pm_start", "13:00")),
        intraday_window_pm_end=str(intraday.get("window_pm_end", "15:00")),
        preclose_enabled=bool(preclose.get("enabled", True)),
        preclose_trigger_time=str(preclose.get("trigger_time", "14:45")),
        preclose_decision_time=str(preclose.get("decision_time", "14:50")),
        preclose_output_dir=str(preclose.get("output_dir", "reports/preclose")),
        hk_realtime_provider=hk_provider,
        hk_realtime_futu_host=futu_host,
        hk_realtime_futu_port=futu_port,
        hk_realtime_futu_is_encrypt=futu_is_encrypt,
        hk_realtime_futu_symbol_map=hk_symbol_map,
    )
