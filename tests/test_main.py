from datetime import date

from market_daily_wechat_report.main import _is_push_blocked_by_market_timing
from market_daily_wechat_report.models import DataSourceStatus, MarketSnapshot


def test_us_push_is_blocked_when_close_data_is_not_ready():
    snapshot = MarketSnapshot(
        market="us",
        session_date=date(2026, 7, 7),
        data_sources=[
            DataSourceStatus(
                "美股-收盘数据就绪判断",
                success=False,
                error="2026-07-07 美股收盘数据可能尚未完全更新",
            )
        ],
    )

    assert _is_push_blocked_by_market_timing(snapshot)


def test_a_share_push_is_not_blocked_by_us_close_gate():
    snapshot = MarketSnapshot(
        market="a",
        session_date=date(2026, 7, 7),
        data_sources=[
            DataSourceStatus(
                "美股-收盘数据就绪判断",
                success=False,
                error="not relevant",
            )
        ],
    )

    assert not _is_push_blocked_by_market_timing(snapshot)
