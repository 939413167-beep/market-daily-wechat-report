from market_daily_wechat_report.watchlist import DEFAULT_US_TICKERS, load_watchlist


def test_watchlist_falls_back_to_defaults_when_file_is_missing(tmp_path):
    watchlist = load_watchlist(tmp_path / "missing.yml")

    assert watchlist.a_share_themes
    assert watchlist.us_tickers == DEFAULT_US_TICKERS
