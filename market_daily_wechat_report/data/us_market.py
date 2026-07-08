from __future__ import annotations

import time
from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd

from ..models import DataSourceStatus, MarketItem, MarketSnapshot, TechObservation
from ..watchlist import load_watchlist
from .utils import YFINANCE_RATE_LIMIT_DELAYS, fetch_with_retry, summarize_error


INDEX_SYMBOLS = {
    "道琼斯": "^DJI",
    "纳斯达克": "^IXIC",
    "标普500": "^GSPC",
}

AI_COMPUTE_TICKERS = {"NVDA", "AMD", "AVGO", "TSM", "ASML"}
MEGA_TECH_TICKERS = {"MSFT", "AAPL", "GOOGL", "META", "TSLA"}


def fetch_us_market_snapshot() -> MarketSnapshot:
    import yfinance as yf

    watchlist = load_watchlist()
    statuses: list[DataSourceStatus] = []
    indexes = [_fetch_yahoo_item(yf, name, symbol, statuses) for name, symbol in INDEX_SYMBOLS.items()]
    focus_items = [_fetch_yahoo_item(yf, ticker, ticker, statuses) for ticker in watchlist.us_tickers]
    tech_observation = _build_tech_observation(focus_items)

    session_date = _latest_session_date(indexes + focus_items) or date.today()
    close_status = _close_status(session_date)
    statuses.append(close_status)

    summary = _build_summary(indexes, focus_items, statuses)
    notes = [
        "观察提示：若纳指和重点科技股延续强势，次日A股半导体、CPO、AI、机器人方向更容易获得情绪映射；若VIX上行或科技股回落，注意高位题材分歧。",
    ]

    return MarketSnapshot(
        market="us",
        session_date=session_date,
        indexes=indexes,
        focus_items=focus_items,
        breadth={
            "重点科技股上涨数量": sum(1 for item in focus_items if (item.change_pct or 0) > 0),
            "重点科技股下跌数量": sum(1 for item in focus_items if (item.change_pct or 0) < 0),
        },
        summary=summary,
        notes=notes,
        tech_observation=tech_observation,
        data_sources=statuses,
    )


def is_probable_us_close_ready(session_date: date) -> bool:
    now_ny = pd.Timestamp.now(tz=ZoneInfo("America/New_York"))
    if session_date < now_ny.date():
        return True
    if session_date == now_ny.date() and now_ny.hour >= 16:
        return True
    return False


def _fetch_yahoo_item(yf: object, name: str, symbol: str, statuses: list[DataSourceStatus]) -> MarketItem:
    data, status = fetch_with_retry(
        f"美股-yfinance-{symbol}",
        lambda: _fetch_history_item(yf, name, symbol),
        rate_limit_delays=YFINANCE_RATE_LIMIT_DELAYS,
    )
    statuses.append(status)
    time.sleep(2)
    if data is None:
        return MarketItem(name=name, symbol=symbol, extra="数据暂不可用")
    return data


def _fetch_history_item(yf: object, name: str, symbol: str) -> MarketItem:
    history = yf.Ticker(symbol).history(period="7d", interval="1d", auto_adjust=False, timeout=10)
    if history.empty:
        raise RuntimeError("无可用数据")

    closes = history["Close"].dropna()
    if closes.empty:
        raise RuntimeError("无收盘价")

    price = float(closes.iloc[-1])
    previous = float(closes.iloc[-2]) if len(closes) >= 2 else None
    change_pct = ((price - previous) / previous * 100) if previous else None
    session_date = pd.Timestamp(closes.index[-1]).date()
    return MarketItem(
        name=name,
        symbol=symbol,
        price=price,
        change_pct=change_pct,
        extra=f"交易日 {session_date.isoformat()}",
    )


def _latest_session_date(items: list[MarketItem]) -> date | None:
    dates: list[date] = []
    for item in items:
        try:
            if item.extra and "交易日 " in item.extra:
                dates.append(date.fromisoformat(item.extra.split("交易日 ", 1)[1]))
        except ValueError:
            continue
    return max(dates) if dates else None


def _close_status(session_date: date) -> DataSourceStatus:
    if is_probable_us_close_ready(session_date):
        return DataSourceStatus("美股-收盘数据就绪判断", success=True)
    return DataSourceStatus(
        "美股-收盘数据就绪判断",
        success=False,
        error=f"{session_date} 美股收盘数据可能尚未完全更新",
    )


def _build_summary(
    indexes: list[MarketItem],
    focus_items: list[MarketItem],
    statuses: list[DataSourceStatus],
) -> str:
    if not any(status.success for status in statuses if status.name.startswith("美股-yfinance")):
        return "美股数据源暂不可用，已生成降级报告，建议稍后手动重试。"
    index_text = "，".join(f"{item.name}{_signed(item.change_pct)}" for item in indexes)
    tech_up = [item.name for item in focus_items if (item.change_pct or 0) > 0]
    tech_down = [item.name for item in focus_items if (item.change_pct or 0) < 0]
    tone = "偏强" if len(tech_up) > len(tech_down) else "偏弱" if len(tech_up) < len(tech_down) else "分化"
    return f"{index_text}。重点科技股表现{tone}，上涨包括{_join_or_none(tech_up)}，下跌包括{_join_or_none(tech_down)}。"


def _build_tech_observation(items: list[MarketItem]) -> TechObservation:
    valid = [item for item in items if item.change_pct is not None]
    top_gainers = sorted(valid, key=lambda item: item.change_pct or 0, reverse=True)[:3]
    top_losers = sorted(valid, key=lambda item: item.change_pct or 0)[:3]
    if not top_gainers:
        top_gainers = [MarketItem(name="数据不足", symbol="-", extra="yfinance 数据暂不可用")]
    if not top_losers:
        top_losers = [MarketItem(name="数据不足", symbol="-", extra="yfinance 数据暂不可用")]
    return TechObservation(
        top_gainers=top_gainers,
        top_losers=top_losers,
        ai_compute=[item for item in items if item.symbol in AI_COMPUTE_TICKERS],
        mega_tech=[item for item in items if item.symbol in MEGA_TECH_TICKERS],
    )


def _signed(value: float | None) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def _join_or_none(values: list[str]) -> str:
    return "、".join(values) if values else "暂无"
