from pathlib import Path

import pytest

from market_daily_wechat_report.config import Settings
from market_daily_wechat_report.push import PushError, push_markdown


def test_none_channel_rejects_real_push():
    settings = Settings(
        push_channel="none",
        serverchan_sendkey=None,
        pushplus_token=None,
        timezone="Asia/Shanghai",
        dedup_state_file=Path("state/push_log.json"),
        reports_dir=Path("reports"),
    )

    with pytest.raises(PushError):
        push_markdown("title", "# report", settings)
