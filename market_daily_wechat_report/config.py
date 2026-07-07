from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    push_channel: str
    serverchan_sendkey: str | None
    pushplus_token: str | None
    timezone: str
    dedup_state_file: Path
    reports_dir: Path


def load_settings() -> Settings:
    load_dotenv(BASE_DIR / ".env")

    state_file = Path(os.getenv("DEDUP_STATE_FILE", "state/push_log.json"))
    reports_dir = Path(os.getenv("REPORTS_DIR", "reports"))
    if not state_file.is_absolute():
        state_file = BASE_DIR / state_file
    if not reports_dir.is_absolute():
        reports_dir = BASE_DIR / reports_dir

    return Settings(
        push_channel=os.getenv("PUSH_CHANNEL", "none").strip().lower(),
        serverchan_sendkey=os.getenv("SERVERCHAN_SENDKEY") or None,
        pushplus_token=os.getenv("PUSHPLUS_TOKEN") or None,
        timezone=os.getenv("TIMEZONE", "Asia/Shanghai"),
        dedup_state_file=state_file,
        reports_dir=reports_dir,
    )
