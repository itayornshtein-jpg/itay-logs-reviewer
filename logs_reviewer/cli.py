"""Command line interface for the log reviewer."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from .analyzer import analyze_logs
from .app import run_app
from .reader import collect_sources, LogSource


def format_report(report) -> str:
    lines = []
    lines.append("Log analysis report")
    lines.append("=" * 60)
    lines.append(f"Sources scanned : {report.scanned_sources}")
    lines.append(f"Total findings  : {report.total_findings}")
    if report.totals_by_category:
        lines.append("\nFindings by category:")
        for category, count in sorted(report.totals_by_category.items()):
            lines.append(f" - {category}: {count}")
    if report.top_messages:
        lines.append("\nTop repeated messages:")
        for message, count in report.top_messages:
            lines.append(f" - ({count}x) {message}")
    if report.findings:
        lines.append("\nSample findings:")
        for finding in report.findings[:10]:
            lines.append(
                f"[{finding.category}] {finding.source}:{finding.line_no} -> {finding.line}\n  Suggestion: {finding.suggestion}"
            )
    return "\n".join(lines)


def load_and_analyze(target: Path, sources: Iterable[LogSource] | None = None):
    sources = sources or collect_sources(target)
    return analyze_logs(sources)


def parse_args():
    parser = argparse.ArgumentParser(description="Summarize errors in log files or archives.")
    parser.add_argument("path", nargs="?", type=Path, help="Path to a log file, directory, or zip archive")
    parser.add_argument("--app", action="store_true", help="Launch the drag-and-drop web app")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind the web app to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind the web app to")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.app:
        run_app(host=args.host, port=args.port)
        return

    if not args.path:
        raise SystemExit("Path to a log file, directory, or zip archive is required unless --app is used.")

    report = load_and_analyze(args.path)
    print(format_report(report))


if __name__ == "__main__":
    main()
