from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .formatting import fmt_amount_cny, fmt_number, fmt_pct
from .models import DataSourceStatus, MarketItem, MarketSnapshot, TechObservation, ThemeTracking


MARKET_NAMES = {
    "a": "A股",
    "us": "美股",
    "all": "市场",
}


def render_report(snapshot: MarketSnapshot) -> str:
    title = f"# {MARKET_NAMES.get(snapshot.market, snapshot.market)}收盘报告 - {snapshot.session_date}"
    parts = [title, ""]
    parts.append(_render_items("## 主要指数", snapshot.indexes, include_amount=True))

    if snapshot.breadth:
        parts.extend(["", "## 市场宽度"])
        for key, value in snapshot.breadth.items():
            parts.append(f"- {key}: {value}")

    if snapshot.leaders:
        parts.extend(["", _render_items("## 领涨方向", snapshot.leaders)])
    if snapshot.laggards:
        parts.extend(["", _render_items("## 领跌方向", snapshot.laggards)])
    if snapshot.focus_items:
        parts.extend(["", _render_items("## 重点观察", snapshot.focus_items)])
    if snapshot.theme_tracking:
        parts.extend(["", _render_theme_tracking(snapshot.theme_tracking)])
    if snapshot.tech_observation:
        parts.extend(["", _render_tech_observation(snapshot.tech_observation)])

    if snapshot.summary:
        parts.extend(["", "## 简短总结", snapshot.summary])
    if snapshot.tomorrow_observation:
        parts.extend(["", "## 明日观察", snapshot.tomorrow_observation])
    if snapshot.notes:
        parts.extend(["", "## 备注"])
        parts.extend(f"- {note}" for note in snapshot.notes)

    parts.extend(["", _render_data_sources(snapshot.data_sources)])
    parts.extend(["", "## 推送状态", f"- {snapshot.push_status}"])
    return "\n".join(parts).strip() + "\n"


def render_degraded_report(
    session_date,
    data_sources: list[DataSourceStatus],
    push_status: str = "推送前生成",
) -> str:
    a_status = _market_status(data_sources, "A股")
    us_status = _market_status(data_sources, "美股")
    errors = [f"- {status.name}: {status.error}" for status in data_sources if not status.success]
    if not errors:
        errors = ["- 暂无错误。"]

    parts = [
        f"# 市场收盘报告降级提醒 - {session_date}",
        "",
        f"- 报告日期: {session_date}",
        f"- A股数据状态: {a_status}",
        f"- 美股数据状态: {us_status}",
        f"- 微信推送状态: {push_status}",
        "",
        "## 错误摘要",
        *errors,
        "",
        "## 建议",
        "- 数据源暂时不可用，建议稍后手动重试。",
        "",
        _render_data_sources(data_sources),
    ]
    return "\n".join(parts).strip() + "\n"


def save_report(snapshot: MarketSnapshot, markdown: str, reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    suffix = "degraded" if _is_degraded(snapshot) else "report"
    path = reports_dir / f"{snapshot.market}_{snapshot.session_date.isoformat()}_{suffix}.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def with_push_status(snapshot: MarketSnapshot, push_status: str) -> MarketSnapshot:
    return replace(snapshot, push_status=push_status)


def _render_items(title: str, items: list[MarketItem], include_amount: bool = False) -> str:
    rows = [title]
    if not items or _all_items_missing(items):
        rows.append("- 数据暂不可用")
        return "\n".join(rows)

    for item in items:
        price = fmt_number(item.price) if item.price is not None else "数据暂不可用"
        text = f"- {item.name}({item.symbol}): {price}, {fmt_pct(item.change_pct)}"
        if include_amount:
            text += f", 成交额 {fmt_amount_cny(item.amount)}"
        if item.extra:
            text += f", {item.extra}"
        rows.append(text)
    return "\n".join(rows)


def _render_data_sources(statuses: list[DataSourceStatus]) -> str:
    rows = ["## 数据源状态"]
    if not statuses:
        rows.append("- 未记录数据源状态。")
        return "\n".join(rows)

    for status in statuses:
        if status.success:
            rows.append(f"- {status.name}: 成功")
        else:
            rows.append(f"- {status.name}: 失败，{_friendly_error(status.error)}")
    return "\n".join(rows)


def _render_theme_tracking(items: list[ThemeTracking]) -> str:
    rows = ["## 重点方向跟踪"]
    if all(item.status == "数据不足" and not item.matched_boards for item in items):
        names = "、".join(item.name for item in items)
        rows.append(f"- 数据不足: {names}")
        return "\n".join(rows)
    for item in items:
        rows.append(f"### {item.name}")
        matched = "、".join(board.name for board in item.matched_boards[:5]) or "数据不足"
        rows.append(f"- 相关板块: {matched}")
        rows.append(f"- 平均涨跌幅: {fmt_pct(item.average_change_pct)}")
        rows.append(f"- 最强相关板块: {_theme_board_text(item.strongest)}")
        rows.append(f"- 最弱相关板块: {_theme_board_text(item.weakest)}")
        rows.append(f"- 状态判断: {item.status}")
    return "\n".join(rows)


def _render_tech_observation(observation: TechObservation) -> str:
    return "\n".join(
        [
            "## 科技龙头观察",
            _render_items("### 涨幅前三", observation.top_gainers),
            "",
            _render_items("### 跌幅前三", observation.top_losers),
            "",
            _render_items("### AI算力相关", observation.ai_compute),
            "",
            _render_items("### 大型科技", observation.mega_tech),
        ]
    )


def _theme_board_text(item: MarketItem | None) -> str:
    if item is None:
        return "数据不足"
    return f"{item.name} {fmt_pct(item.change_pct)}"


def _all_items_missing(items: list[MarketItem]) -> bool:
    return all(
        item.price is None
        and item.change_pct is None
        and item.amount is None
        and (not item.extra or "数据暂不可用" in item.extra or "yfinance 数据暂不可用" in item.extra)
        for item in items
    )


def _friendly_error(error: str | None) -> str:
    if not error:
        return "数据暂不可用"
    lower = error.lower()
    hints = []
    if "too many requests" in lower or "rate limit" in lower:
        hints.append("数据源限流")
    if "remotedisconnected" in lower or "remote end closed" in lower:
        hints.append("连接被远端关闭")
    if "max retries exceeded" in lower:
        hints.append("多次重试后仍失败")
    if "jsondecodeerror" in lower or "no value to decode" in lower:
        hints.append("返回数据为空或格式异常")
    if "timeout" in lower or "timed out" in lower:
        hints.append("请求超时")
    return "，".join(dict.fromkeys(hints)) or error[:80]


def _market_status(statuses: list[DataSourceStatus], prefix: str) -> str:
    market_statuses = [status for status in statuses if status.name.startswith(prefix)]
    if not market_statuses:
        return "未运行"
    if any(status.success for status in market_statuses):
        return "部分可用" if any(not status.success for status in market_statuses) else "成功"
    return "失败"


def _is_degraded(snapshot: MarketSnapshot) -> bool:
    ignored = ("交易日", "收盘数据就绪判断", "解析")
    return bool(snapshot.data_sources) and not any(
        status.success and not any(token in status.name for token in ignored)
        for status in snapshot.data_sources
    )
