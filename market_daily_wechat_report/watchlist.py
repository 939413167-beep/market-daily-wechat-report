from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import BASE_DIR


@dataclass(frozen=True)
class WatchTheme:
    name: str
    keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Watchlist:
    a_share_themes: list[WatchTheme]
    us_tickers: list[str]


DEFAULT_A_SHARE_THEMES = [
    WatchTheme("半导体", ["半导体", "芯片", "集成电路"]),
    WatchTheme("CPO / 光模块", ["CPO", "光模块", "光通信"]),
    WatchTheme("AI算力", ["算力", "AI", "服务器", "液冷"]),
    WatchTheme("机器人", ["机器人", "减速器", "伺服"]),
    WatchTheme("通信设备", ["通信设备", "5G", "光通信"]),
    WatchTheme("消费电子", ["消费电子", "苹果产业链", "端侧AI"]),
]

DEFAULT_US_TICKERS = ["NVDA", "AMD", "AVGO", "TSM", "ASML", "MSFT", "AAPL", "GOOGL", "META", "TSLA"]


def load_watchlist(path: Path | None = None) -> Watchlist:
    path = path or BASE_DIR / "config" / "watchlist.yml"
    try:
        import yaml

        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        themes = [
            WatchTheme(str(item["name"]), [str(keyword) for keyword in item.get("keywords", [])])
            for item in payload.get("a_share", {}).get("themes", [])
            if item.get("name")
        ]
        tickers = [str(ticker).upper() for ticker in payload.get("us", {}).get("tickers", []) if ticker]
        return Watchlist(
            a_share_themes=themes or DEFAULT_A_SHARE_THEMES,
            us_tickers=tickers or DEFAULT_US_TICKERS,
        )
    except Exception as exc:
        print(f"[watchlist] using built-in defaults: {exc}")
        return Watchlist(a_share_themes=DEFAULT_A_SHARE_THEMES, us_tickers=DEFAULT_US_TICKERS)
