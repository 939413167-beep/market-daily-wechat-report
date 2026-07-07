from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class DataSourceStatus:
    name: str
    success: bool
    error: str | None = None


@dataclass(frozen=True)
class MarketItem:
    name: str
    symbol: str
    price: float | None = None
    change_pct: float | None = None
    amount: float | None = None
    extra: str | None = None


@dataclass(frozen=True)
class MarketSnapshot:
    market: str
    session_date: date
    indexes: list[MarketItem] = field(default_factory=list)
    focus_items: list[MarketItem] = field(default_factory=list)
    leaders: list[MarketItem] = field(default_factory=list)
    laggards: list[MarketItem] = field(default_factory=list)
    breadth: dict[str, int | float | str] = field(default_factory=dict)
    summary: str = ""
    notes: list[str] = field(default_factory=list)
    data_sources: list[DataSourceStatus] = field(default_factory=list)
    push_status: str = "未推送"
