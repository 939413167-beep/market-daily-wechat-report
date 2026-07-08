from datetime import date

from market_daily_wechat_report.models import MarketItem, MarketSnapshot, TechObservation, ThemeTracking
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


def test_render_report_contains_phase2_sections():
    snapshot = MarketSnapshot(
        market="a",
        session_date=date(2026, 7, 7),
        theme_tracking=[
            ThemeTracking(
                name="半导体",
                matched_boards=[MarketItem("半导体", "BK0001", change_pct=1.5)],
                average_change_pct=1.5,
                strongest=MarketItem("半导体", "BK0001", change_pct=1.5),
                weakest=MarketItem("芯片", "BK0002", change_pct=0.4),
                status="偏强",
            )
        ],
        tech_observation=TechObservation(
            top_gainers=[MarketItem("NVDA", "NVDA", change_pct=2.0)],
            top_losers=[MarketItem("TSLA", "TSLA", change_pct=-1.0)],
            ai_compute=[MarketItem("NVDA", "NVDA", change_pct=2.0)],
            mega_tech=[MarketItem("AAPL", "AAPL", change_pct=0.5)],
        ),
        tomorrow_observation="科技成长方向出现共振，明日关注成交额能否继续放大。",
    )

    markdown = render_report(snapshot)

    assert "重点方向跟踪" in markdown
    assert "科技龙头观察" in markdown
    assert "明日观察" in markdown
    assert "偏强" in markdown
