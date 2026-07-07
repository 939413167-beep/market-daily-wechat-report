from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path


class DedupeStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, dict[str, str]]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _save(self, data: dict[str, dict[str, str]]) -> None:
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    @staticmethod
    def key(market: str, session_date: date) -> str:
        return f"{market}:{session_date.isoformat()}"

    def has_sent(self, market: str, session_date: date) -> bool:
        data = self._load()
        return self.key(market, session_date) in data

    def mark_sent(self, market: str, session_date: date) -> None:
        data = self._load()
        data[self.key(market, session_date)] = {
            "market": market,
            "session_date": session_date.isoformat(),
            "sent_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        self._save(data)
