from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import os

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


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

    interval_minutes = int(intraday.get("interval_minutes", 5))
    if interval_minutes < 1:
        interval_minutes = 1

    lookback_bars = int(intraday.get("lookback_bars", 120))
    if lookback_bars < 20:
        lookback_bars = 20

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
    )
