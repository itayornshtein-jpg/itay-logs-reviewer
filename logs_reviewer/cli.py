"""Command line interface for the log reviewer."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from .analyzer import analyze_logs
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
    parser.add_argument("path", type=Path, help="Path to a log file, directory, or zip archive")
    return parser.parse_args()


def main():
    args = parse_args()
    report = load_and_analyze(args.path)
    print(format_report(report))


if __name__ == "__main__":
    main()
