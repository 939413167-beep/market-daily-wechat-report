from __future__ import annotations

from datetime import date

import pandas as pd

from ..models import DataSourceStatus, MarketItem, MarketSnapshot
from .utils import fetch_with_retry, log_proxy_status, summarize_error


INDEX_KEYWORDS = {
    "上证指数": "000001",
    "深证成指": "399001",
    "创业板指": "399006",
    "科创50": "000688",
}

FOCUS_KEYWORDS = ["半导体", "CPO", "人工智能", "AI", "机器人"]


def fetch_a_share_snapshot(session_date: date | None = None) -> MarketSnapshot:
    import akshare as ak

    log_proxy_status()
    session_date = session_date or date.today()
    statuses: list[DataSourceStatus] = []

    is_trade_day, trade_status = _safe_is_a_share_trade_day(ak, session_date)
    statuses.append(trade_status)
    if not is_trade_day:
        return MarketSnapshot(
            market="a",
            session_date=session_date,
            summary=f"{session_date} 不是A股交易日，未生成正式收盘数据。",
            notes=["非交易日不会影响其他市场报告生成。"],
            data_sources=statuses,
        )

    index_df, status = fetch_with_retry("A股-主要指数-东方财富", ak.stock_zh_index_spot_em)
    statuses.append(status)
    stock_df, status = fetch_with_retry("A股-市场宽度-东方财富", ak.stock_zh_a_spot_em)
    statuses.append(status)
    board_df, status = fetch_with_retry("A股-行业板块-东方财富", ak.stock_board_industry_name_em)
    statuses.append(status)

    indexes = _safe_extract(
        "A股-主要指数解析",
        statuses,
        lambda: _extract_indexes(index_df) if index_df is not None else _missing_indexes(),
        _missing_indexes(),
    )
    breadth = _safe_extract(
        "A股-市场宽度解析",
        statuses,
        lambda: _build_breadth(stock_df) if stock_df is not None else {},
        {},
    )
    leaders, laggards = _safe_extract(
        "A股-板块涨跌解析",
        statuses,
        lambda: _extract_board_movers(board_df) if board_df is not None else ([], []),
        ([], []),
    )
    focus_items = _safe_extract(
        "A股-重点方向解析",
        statuses,
        lambda: _extract_focus_boards(board_df) if board_df is not None else _missing_focus_items(),
        _missing_focus_items(),
    )
    summary = _build_summary(indexes, breadth, leaders, laggards, statuses)

    return MarketSnapshot(
        market="a",
        session_date=session_date,
        indexes=indexes,
        focus_items=focus_items,
        leaders=leaders,
        laggards=laggards,
        breadth=breadth,
        summary=summary,
        data_sources=statuses,
    )


def is_a_share_trade_day(day: date) -> bool:
    if day.weekday() >= 5:
        return False
    try:
        import akshare as ak

        trade_df = ak.tool_trade_date_hist_sina()
        trade_dates = set(pd.to_datetime(trade_df["trade_date"]).dt.date)
        return day in trade_dates
    except Exception:
        return True


def _safe_is_a_share_trade_day(ak, day: date) -> tuple[bool, DataSourceStatus]:
    if day.weekday() >= 5:
        return False, DataSourceStatus("A股-交易日判断", success=True)
    trade_df, status = fetch_with_retry("A股-交易日历-Sina", ak.tool_trade_date_hist_sina)
    if trade_df is None:
        return True, status
    try:
        trade_dates = set(pd.to_datetime(trade_df["trade_date"]).dt.date)
        return day in trade_dates, status
    except Exception as exc:
        return True, DataSourceStatus("A股-交易日历解析", success=False, error=summarize_error(exc))


def _safe_extract(name: str, statuses: list[DataSourceStatus], func, fallback):
    try:
        result = func()
        statuses.append(DataSourceStatus(name, success=True))
        return result
    except Exception as exc:
        statuses.append(DataSourceStatus(name, success=False, error=summarize_error(exc)))
        return fallback


def _extract_indexes(df: pd.DataFrame) -> list[MarketItem]:
    items: list[MarketItem] = []
    for name, code in INDEX_KEYWORDS.items():
        try:
            row = _find_row(df, name=name, code=code)
            if row is None:
                items.append(MarketItem(name=name, symbol=code, extra="数据暂不可用"))
                continue
            items.append(
                MarketItem(
                    name=name,
                    symbol=str(row.get("代码", code)),
                    price=_to_float(row.get("最新价")),
                    change_pct=_to_float(row.get("涨跌幅")),
                    amount=_to_float(row.get("成交额")),
                )
            )
        except Exception as exc:
            items.append(MarketItem(name=name, symbol=code, extra=f"数据暂不可用: {summarize_error(exc)}"))
    return items


def _build_breadth(df: pd.DataFrame) -> dict[str, int | float | str]:
    pct = pd.to_numeric(df.get("涨跌幅"), errors="coerce")
    return {
        "上涨家数": int((pct > 0).sum()),
        "下跌家数": int((pct < 0).sum()),
        "平盘家数": int((pct == 0).sum()),
        "涨停数量": int((pct >= 9.8).sum()),
        "跌停数量": int((pct <= -9.8).sum()),
        "全市场成交额": f"{pd.to_numeric(df.get('成交额'), errors='coerce').sum() / 100_000_000:.2f} 亿",
    }


def _extract_board_movers(df: pd.DataFrame) -> tuple[list[MarketItem], list[MarketItem]]:
    frame = df.copy()
    frame["涨跌幅"] = pd.to_numeric(frame.get("涨跌幅"), errors="coerce")
    frame = frame.dropna(subset=["涨跌幅"])
    leaders = [_board_item(row) for _, row in frame.nlargest(5, "涨跌幅").iterrows()]
    laggards = [_board_item(row) for _, row in frame.nsmallest(5, "涨跌幅").iterrows()]
    return leaders, laggards


def _extract_focus_boards(df: pd.DataFrame) -> list[MarketItem]:
    frame = df.copy()
    name_col = "板块名称" if "板块名称" in frame.columns else "名称"
    frame["涨跌幅"] = pd.to_numeric(frame.get("涨跌幅"), errors="coerce")
    items: list[MarketItem] = []
    for keyword in FOCUS_KEYWORDS:
        try:
            matched = frame[frame[name_col].astype(str).str.contains(keyword, case=False, na=False)]
            if matched.empty:
                items.append(MarketItem(name=keyword, symbol="-", extra="数据暂不可用"))
                continue
            row = matched.sort_values("涨跌幅", ascending=False).iloc[0]
            items.append(_board_item(row))
        except Exception as exc:
            items.append(MarketItem(name=keyword, symbol="-", extra=f"数据暂不可用: {summarize_error(exc)}"))
    return items


def _build_summary(
    indexes: list[MarketItem],
    breadth: dict[str, int | float | str],
    leaders: list[MarketItem],
    laggards: list[MarketItem],
    statuses: list[DataSourceStatus],
) -> str:
    if not any(status.success for status in statuses if status.name.startswith("A股-") and "解析" not in status.name):
        return "A股数据源暂不可用，已生成降级报告，建议稍后手动重试。"
    index_text = "，".join(f"{item.name}{_signed(item.change_pct)}" for item in indexes)
    up = int(breadth.get("上涨家数", 0) or 0)
    down = int(breadth.get("下跌家数", 0) or 0)
    leader_text = "、".join(item.name for item in leaders[:3]) or "暂无"
    laggard_text = "、".join(item.name for item in laggards[:3]) or "暂无"
    tone = "偏强" if up > down else "偏弱" if up < down else "均衡"
    return f"{index_text}。市场宽度{tone}，上涨{up}家、下跌{down}家。领涨方向集中在{leader_text}，领跌方向主要为{laggard_text}。"


def _find_row(df: pd.DataFrame, name: str, code: str) -> pd.Series | None:
    for col in ("名称", "name"):
        if col in df.columns:
            matched = df[df[col].astype(str).str.contains(name, na=False)]
            if not matched.empty:
                return matched.iloc[0]
    for col in ("代码", "code"):
        if col in df.columns:
            matched = df[df[col].astype(str) == code]
            if not matched.empty:
                return matched.iloc[0]
    return None


def _board_item(row: pd.Series) -> MarketItem:
    name = str(row.get("板块名称", row.get("名称", "-")))
    symbol = str(row.get("板块代码", row.get("代码", "-")))
    return MarketItem(
        name=name,
        symbol=symbol,
        price=_to_float(row.get("最新价")),
        change_pct=_to_float(row.get("涨跌幅")),
        amount=_to_float(row.get("成交额")),
    )


def _missing_indexes() -> list[MarketItem]:
    return [MarketItem(name=name, symbol=code, extra="数据暂不可用") for name, code in INDEX_KEYWORDS.items()]


def _missing_focus_items() -> list[MarketItem]:
    return [MarketItem(name=name, symbol="-", extra="数据暂不可用") for name in FOCUS_KEYWORDS]


def _to_float(value: object) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _signed(value: float | None) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"
