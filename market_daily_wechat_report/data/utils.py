from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import TypeVar

from ..models import DataSourceStatus


T = TypeVar("T")
DEFAULT_DELAYS = (3, 8, 15)
YFINANCE_RATE_LIMIT_DELAYS = (10, 20, 35)


def summarize_error(exc: BaseException, max_length: int = 240) -> str:
    text = str(exc).replace("\n", " ").strip() or exc.__class__.__name__
    return text[:max_length]


def fetch_with_retry(
    name: str,
    func: Callable[[], T],
    delays: tuple[int, ...] = DEFAULT_DELAYS,
    rate_limit_delays: tuple[int, ...] | None = None,
) -> tuple[T | None, DataSourceStatus]:
    attempts = len(delays) + 1
    last_error: BaseException | None = None
    for attempt in range(attempts):
        try:
            return func(), DataSourceStatus(name=name, success=True)
        except Exception as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            wait = delays[attempt]
            if rate_limit_delays and _is_rate_limited(exc):
                wait = rate_limit_delays[min(attempt, len(rate_limit_delays) - 1)]
            print(f"[data] {name} failed on attempt {attempt + 1}/{attempts}: {summarize_error(exc)}")
            print(f"[data] retrying {name} after {wait}s")
            time.sleep(wait)

    assert last_error is not None
    return None, DataSourceStatus(name=name, success=False, error=summarize_error(last_error))


def log_proxy_status() -> None:
    http_proxy = bool(os.getenv("HTTP_PROXY") or os.getenv("http_proxy"))
    https_proxy = bool(os.getenv("HTTPS_PROXY") or os.getenv("https_proxy"))
    print(f"[env] HTTP_PROXY set: {http_proxy}; HTTPS_PROXY set: {https_proxy}")
    if http_proxy or https_proxy:
        print("[env] 当前环境存在代理设置，AKShare/东方财富接口可能受影响。")


def _is_rate_limited(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "too many requests" in text or "rate limit" in text or "rate limited" in text
