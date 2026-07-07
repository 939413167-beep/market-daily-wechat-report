from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date

from .config import Settings, load_settings
from .data.a_share import fetch_a_share_snapshot
from .data.us_market import fetch_us_market_snapshot
from .dedupe import DedupeStore
from .models import DataSourceStatus, MarketSnapshot
from .push import push_markdown
from .report import MARKET_NAMES, render_degraded_report, render_report, save_report, with_push_status


@dataclass(frozen=True)
class RunResult:
    market: str
    success: bool
    pushed: bool
    report_path: str | None
    data_sources: list[DataSourceStatus]
    snapshot: MarketSnapshot | None = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate and push daily market close reports.")
    parser.add_argument("--market", choices=["a", "ashare", "us", "auto"], default="auto")
    parser.add_argument("--no-push", action="store_true", help="Generate report without sending WeChat push.")
    parser.add_argument("--dry-run", action="store_true", help="Generate and save reports without sending push or writing dedupe state.")
    parser.add_argument("--test-push", action="store_true", help="Only send a short push-channel test message.")
    args = parser.parse_args(argv)

    settings = load_settings()
    if args.test_push:
        return _run_test_push(settings)

    markets = _resolve_markets(args.market)
    dry_run = args.dry_run or args.no_push

    if args.market == "auto" and len(markets) > 1:
        return _run_auto_combined(markets, settings, dry_run=dry_run)

    results: list[RunResult] = []

    for market in markets:
        result = _run_market(market, settings, dry_run=dry_run)
        results.append(result)

    if len(markets) > 1 and all(not result.success for result in results):
        results.append(_run_combined_degraded_report(results, settings, dry_run=dry_run))

    return 0 if any(result.success or result.pushed or result.report_path for result in results) else 1


def _run_market(market: str, settings: Settings, dry_run: bool = False) -> RunResult:
    snapshot = _fetch_snapshot(market)
    dedupe = DedupeStore(settings.dedup_state_file)
    has_data = _has_successful_market_data(snapshot)
    report_path = None
    pushed = False

    if not dry_run and has_data and dedupe.has_sent(snapshot.market, snapshot.session_date):
        print(f"[dedupe] skipped {snapshot.market} {snapshot.session_date}: already sent")
        return RunResult(snapshot.market, True, False, None, snapshot.data_sources, snapshot)

    title = f"{MARKET_NAMES.get(snapshot.market, snapshot.market)}收盘报告 {snapshot.session_date}"
    push_status = "dry-run 模式：已跳过微信推送" if dry_run else "推送中"
    markdown_for_push = render_report(with_push_status(snapshot, push_status))

    if dry_run:
        final_snapshot = with_push_status(snapshot, "dry-run 模式：已跳过微信推送")
        report_path = save_report(final_snapshot, render_report(final_snapshot), settings.reports_dir)
        print("dry-run 模式：已跳过微信推送")
        print(f"[report] generated without push: {report_path}")
        return RunResult(snapshot.market, has_data, False, str(report_path), snapshot.data_sources, final_snapshot)

    try:
        push_markdown(title, markdown_for_push, settings)
        pushed = True
        final_snapshot = with_push_status(snapshot, "微信推送成功")
        if has_data:
            dedupe.mark_sent(snapshot.market, snapshot.session_date)
        print(f"[report] pushed: {snapshot.market} {snapshot.session_date}")
    except Exception as exc:
        final_snapshot = with_push_status(snapshot, f"微信推送失败: {exc}")
        print(f"[push] failed for {snapshot.market}: {exc}", file=sys.stderr)

    final_markdown = render_report(final_snapshot)
    report_path = save_report(final_snapshot, final_markdown, settings.reports_dir)
    print(f"[report] saved: {report_path}")
    return RunResult(snapshot.market, has_data, pushed, str(report_path), snapshot.data_sources, final_snapshot)


def _fetch_snapshot(market: str) -> MarketSnapshot:
    try:
        if market == "a":
            return fetch_a_share_snapshot()
        return fetch_us_market_snapshot()
    except Exception as exc:
        status = DataSourceStatus(f"{MARKET_NAMES.get(market, market)}-数据获取", success=False, error=str(exc)[:240])
        return MarketSnapshot(
            market=market,
            session_date=date.today(),
            summary=f"{MARKET_NAMES.get(market, market)}数据源暂不可用，已生成降级报告，建议稍后手动重试。",
            notes=["数据获取异常已被捕获，不会影响其他市场报告生成。"],
            data_sources=[status],
        )


def _run_auto_combined(markets: list[str], settings: Settings, dry_run: bool = False) -> int:
    results: list[RunResult] = []
    snapshots: list[MarketSnapshot] = []
    for market in markets:
        snapshot = _fetch_snapshot(market)
        has_data = _has_successful_market_data(snapshot)
        final_snapshot = with_push_status(
            snapshot,
            "dry-run 模式：已跳过微信推送" if dry_run else "默认综合推送模式：单市场报告不单独推送",
        )
        path = save_report(final_snapshot, render_report(final_snapshot), settings.reports_dir)
        print(f"[report] saved: {path}")
        snapshots.append(final_snapshot)
        results.append(RunResult(snapshot.market, has_data, False, str(path), snapshot.data_sources, final_snapshot))

    if dry_run:
        print("dry-run 模式：已跳过微信推送")
        return 0

    title = f"市场综合收盘报告 {date.today().isoformat()}"
    markdown_for_push = _render_combined_report(snapshots, "推送中")
    pushed = False
    push_status = "微信推送成功"
    try:
        push_markdown(title, markdown_for_push, settings)
        pushed = True
        dedupe = DedupeStore(settings.dedup_state_file)
        for result in results:
            if result.snapshot and result.success:
                dedupe.mark_sent(result.snapshot.market, result.snapshot.session_date)
        print(f"[report] pushed: auto combined {date.today().isoformat()}")
    except Exception as exc:
        push_status = f"微信推送失败: {exc}"
        print(f"[push] failed for auto combined report: {exc}", file=sys.stderr)

    path = settings.reports_dir / f"all_{date.today().isoformat()}_report.md"
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_combined_report(snapshots, push_status), encoding="utf-8")
    print(f"[report] saved: {path}")

    if all(not result.success for result in results):
        _run_combined_degraded_report(results, settings, dry_run=False, skip_push=True, push_status=push_status)
    return 0 if pushed or any(result.success for result in results) else 1


def _run_combined_degraded_report(
    results: list[RunResult],
    settings: Settings,
    dry_run: bool = False,
    skip_push: bool = False,
    push_status: str | None = None,
) -> RunResult:
    data_sources = [status for result in results for status in result.data_sources]
    push_status = push_status or ("dry-run 模式：已跳过微信推送" if dry_run else "推送中")
    markdown_for_push = render_degraded_report(date.today(), data_sources, push_status=push_status)
    path = settings.reports_dir / f"all_{date.today().isoformat()}_degraded.md"
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    pushed = False

    if dry_run:
        print("dry-run 模式：已跳过微信推送")
    elif not skip_push:
        try:
            push_markdown(f"市场收盘报告降级提醒 {date.today().isoformat()}", markdown_for_push, settings)
            pushed = True
            push_status = "微信推送成功"
        except Exception as exc:
            push_status = f"微信推送失败: {exc}"
            print(f"[push] failed for combined degraded report: {exc}", file=sys.stderr)

    final_markdown = render_degraded_report(date.today(), data_sources, push_status=push_status)
    path.write_text(final_markdown, encoding="utf-8")
    print(f"[report] saved: {path}")
    return RunResult("all", False, pushed, str(path), data_sources)


def _run_test_push(settings: Settings) -> int:
    message = "market-daily-wechat-report 推送通道测试成功"
    try:
        push_markdown(message, message, settings)
        print("[push] test message accepted")
        return 0
    except Exception as exc:
        print(f"[push] test failed: {exc}", file=sys.stderr)
        return 1


def _render_combined_report(snapshots: list[MarketSnapshot], push_status: str) -> str:
    parts = [
        f"# 市场综合收盘报告 - {date.today().isoformat()}",
        "",
        "## 推送状态",
        f"- {push_status}",
    ]
    for snapshot in snapshots:
        section = render_report(snapshot).replace("# ", "## ", 1).strip()
        parts.extend(["", section])
    return "\n".join(parts).strip() + "\n"


def _has_successful_market_data(snapshot: MarketSnapshot) -> bool:
    ignored = ("交易日", "收盘数据就绪判断", "解析")
    return any(status.success and not any(token in status.name for token in ignored) for status in snapshot.data_sources)


def _resolve_markets(market: str) -> list[str]:
    if market == "auto":
        return ["a", "us"]
    if market == "ashare":
        return ["a"]
    return [market]


if __name__ == "__main__":
    raise SystemExit(main())
