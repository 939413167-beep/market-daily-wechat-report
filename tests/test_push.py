from pathlib import Path

from market_daily_wechat_report.config import Settings
from market_daily_wechat_report.push import push_markdown


def test_none_channel_skips_push():
    settings = Settings(
        push_channel="none",
        serverchan_sendkey=None,
        pushplus_token=None,
        timezone="Asia/Shanghai",
        dedup_state_file=Path("state/push_log.json"),
        reports_dir=Path("reports"),
    )

    push_markdown("title", "# report", settings)
