from __future__ import annotations


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def fmt_number(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}"


def fmt_amount_cny(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value / 100_000_000:.2f} 亿"
