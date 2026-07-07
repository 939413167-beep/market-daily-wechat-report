from datetime import date

from market_daily_wechat_report.models import MarketItem, MarketSnapshot
from market_daily_wechat_report.report import render_report


def test_render_report_contains_core_sections():
    snapshot = MarketSnapshot(
        market="a",
        session_date=date(2026, 7, 7),
        indexes=[MarketItem("上证指数", "000001", 3200, 1.23, 500_000_000_000)],
        breadth={"上涨家数": 3000, "下跌家数": 2000},
        summary="市场震荡走强。",
    )

    markdown = render_report(snapshot)

    assert "# A股收盘报告 - 2026-07-07" in markdown
    assert "上证指数" in markdown
    assert "市场宽度" in markdown
    assert "市场震荡走强。" in markdown
