from datetime import date

from market_daily_wechat_report.dedupe import DedupeStore


def test_dedupe_marks_market_date_as_sent(tmp_path):
    store = DedupeStore(tmp_path / "push_log.json")

    assert not store.has_sent("a", date(2026, 7, 7))

    store.mark_sent("a", date(2026, 7, 7))

    assert store.has_sent("a", date(2026, 7, 7))
    assert not store.has_sent("us", date(2026, 7, 7))
