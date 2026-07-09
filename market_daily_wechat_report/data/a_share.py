from __future__ import annotations

from datetime import date

import pandas as pd
import requests

from ..models import DataSourceStatus, MarketItem, MarketSnapshot, ThemeTracking
from ..watchlist import WatchTheme, load_watchlist
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
    watchlist = load_watchlist()

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
    index_fallback_df = None
    if index_df is None or not _has_all_indexes(index_df):
        index_fallback_df, status = fetch_with_retry("A股-主要指数-Sina备用", _fetch_index_sina_direct)
        statuses.append(status)
    stock_df, status = fetch_with_retry("A股-市场宽度-东方财富", ak.stock_zh_a_spot_em)
    statuses.append(status)
    board_df, status = fetch_with_retry("A股-行业板块-东方财富", ak.stock_board_industry_name_em)
    statuses.append(status)

    indexes = _safe_extract(
        "A股-主要指数解析",
        statuses,
        lambda: _extract_indexes(index_df, index_fallback_df),
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
    theme_tracking = _safe_extract(
        "A股-重点方向跟踪解析",
        statuses,
        lambda: _extract_theme_tracking(board_df, watchlist.a_share_themes) if board_df is not None else _missing_theme_tracking(watchlist.a_share_themes),
        _missing_theme_tracking(watchlist.a_share_themes),
    )
    summary = _build_summary(indexes, breadth, leaders, laggards, statuses)
    tomorrow_observation = _build_tomorrow_observation(indexes, theme_tracking)

    return MarketSnapshot(
        market="a",
        session_date=session_date,
        indexes=indexes,
        focus_items=focus_items,
        leaders=leaders,
        laggards=laggards,
        breadth=breadth,
        summary=summary,
        theme_tracking=theme_tracking,
        tomorrow_observation=tomorrow_observation,
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


def _fetch_index_sina_direct() -> pd.DataFrame:
    symbols = {
        "000001": "s_sh000001",
        "399001": "s_sz399001",
        "399006": "s_sz399006",
        "000688": "s_sh000688",
    }
    url = "https://hq.sinajs.cn/list=" + ",".join(symbols.values())
    response = requests.get(
        url,
        headers={"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"},
        timeout=10,
    )
    response.raise_for_status()

    rows = []
    for code, symbol in symbols.items():
        marker = f'hq_str_{symbol}="'
        line = next((item for item in response.text.splitlines() if marker in item), "")
        payload = line.split(marker, 1)[-1].split('";', 1)[0] if line else ""
        parts = payload.split(",")
        if len(parts) < 6:
            continue
        rows.append(
            {
                "代码": code,
                "名称": parts[0],
                "最新价": _to_float(parts[1]),
                "涨跌幅": _to_float(parts[3]),
                "成交额": (_to_float(parts[5]) or 0) * 10_000,
            }
        )
    if not rows:
        raise ValueError("Sina 主要指数备用源无有效数据")
    return pd.DataFrame(rows)


def _extract_indexes(primary_df: pd.DataFrame | None, fallback_df: pd.DataFrame | None = None) -> list[MarketItem]:
    items: list[MarketItem] = []
    for name, code in INDEX_KEYWORDS.items():
        try:
            row = _find_row(primary_df, name=name, code=code)
            if row is None:
                row = _find_row(fallback_df, name=name, code=code)
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


def _has_all_indexes(df: pd.DataFrame | None) -> bool:
    if df is None:
        return False
    return all(_find_row(df, name=name, code=code) is not None for name, code in INDEX_KEYWORDS.items())


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


def _extract_theme_tracking(df: pd.DataFrame, themes: list[WatchTheme]) -> list[ThemeTracking]:
    frame = df.copy()
    name_col = "板块名称" if "板块名称" in frame.columns else "名称"
    frame["涨跌幅"] = pd.to_numeric(frame.get("涨跌幅"), errors="coerce")
    tracking: list[ThemeTracking] = []

    for theme in themes:
        matched = _match_theme_rows(frame, name_col, theme.keywords)
        if matched.empty:
            tracking.append(ThemeTracking(name=theme.name, status="数据不足"))
            continue

        boards = [_board_item(row) for _, row in matched.iterrows()]
        valid = [item for item in boards if item.change_pct is not None]
        if not valid:
            tracking.append(ThemeTracking(name=theme.name, matched_boards=boards, status="数据不足"))
            continue

        average = sum(item.change_pct or 0 for item in valid) / len(valid)
        strongest = max(valid, key=lambda item: item.change_pct or 0)
        weakest = min(valid, key=lambda item: item.change_pct or 0)
        tracking.append(
            ThemeTracking(
                name=theme.name,
                matched_boards=boards,
                average_change_pct=average,
                strongest=strongest,
                weakest=weakest,
                status=_theme_status(valid, average),
            )
        )
    return tracking


def _match_theme_rows(frame: pd.DataFrame, name_col: str, keywords: list[str]) -> pd.DataFrame:
    if not keywords or name_col not in frame.columns:
        return frame.iloc[0:0]
    mask = pd.Series(False, index=frame.index)
    for keyword in keywords:
        mask = mask | frame[name_col].astype(str).str.contains(keyword, case=False, na=False)
    return frame[mask].drop_duplicates(subset=[name_col]).sort_values("涨跌幅", ascending=False)


def _theme_status(items: list[MarketItem], average: float | None) -> str:
    if average is None or not items:
        return "数据不足"
    changes = [item.change_pct for item in items if item.change_pct is not None]
    if not changes:
        return "数据不足"
    if max(changes) >= 1 and min(changes) <= -1:
        return "分歧"
    if average >= 1:
        return "偏强"
    if average <= -1:
        return "偏弱"
    return "分歧"


def _build_tomorrow_observation(indexes: list[MarketItem], tracking: list[ThemeTracking]) -> str:
    if not tracking or any(item.status == "数据不足" for item in tracking):
        return "部分数据源不可用，明日观察模块仅供参考。"

    status_by_name = {item.name: item.status for item in tracking}
    core_statuses = [
        status_by_name.get("半导体"),
        status_by_name.get("CPO / 光模块"),
        status_by_name.get("AI算力"),
    ]
    if all(status == "偏强" for status in core_statuses):
        return "科技成长方向出现共振，明日关注成交额能否继续放大。"
    if any(item.status == "分歧" for item in tracking):
        return "科技方向内部出现分化，明日关注强势分支能否延续。"

    index_changes = [item.change_pct for item in indexes if item.change_pct is not None]
    index_positive = bool(index_changes) and sum(index_changes) / len(index_changes) > 0
    tech_weak = all(status in {"偏弱", "分歧", "数据不足"} for status in core_statuses)
    if index_positive and tech_weak:
        return "指数表现强于科技主线，明日关注资金是否轮动回科技方向。"

    return "重点方向表现仍需结合成交额和市场宽度观察，明日关注主线延续性。"


def _build_summary(
    indexes: list[MarketItem],
    breadth: dict[str, int | float | str],
    leaders: list[MarketItem],
    laggards: list[MarketItem],
    statuses: list[DataSourceStatus],
) -> str:
    has_index_data = any(item.change_pct is not None for item in indexes)
    if not has_index_data:
        return "A股实时行情数据暂不可用，已生成降级报告。建议稍后手动重试或查看交易所/行情软件确认收盘情况。"
    index_text = "，".join(f"{item.name}{_signed(item.change_pct)}" for item in indexes)
    up = int(breadth.get("上涨家数", 0) or 0)
    down = int(breadth.get("下跌家数", 0) or 0)
    if not breadth:
        return f"{index_text}。市场宽度、涨跌停和板块数据暂不可用，今日报告仅保留主要指数参考。"
    leader_text = "、".join(item.name for item in leaders[:3]) or "暂无"
    laggard_text = "、".join(item.name for item in laggards[:3]) or "暂无"
    tone = "偏强" if up > down else "偏弱" if up < down else "均衡"
    return f"{index_text}。市场宽度{tone}，上涨{up}家、下跌{down}家。领涨方向集中在{leader_text}，领跌方向主要为{laggard_text}。"


def _find_row(df: pd.DataFrame | None, name: str, code: str) -> pd.Series | None:
    if df is None:
        return None
    for col in ("名称", "name"):
        if col in df.columns:
            matched = df[df[col].astype(str).str.contains(name, na=False)]
            if not matched.empty:
                return matched.iloc[0]
    for col in ("代码", "code"):
        if col in df.columns:
            matched = df[df[col].astype(str).str.endswith(code)]
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


def _missing_theme_tracking(themes: list[WatchTheme]) -> list[ThemeTracking]:
    return [ThemeTracking(name=theme.name, status="数据不足") for theme in themes]


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
