"""Identify and categorize errors from log sources."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List

from .reader import LogSource

ERROR_PATTERNS = [
    ("traceback", re.compile(r"Traceback \(most recent call last\)", re.IGNORECASE)),
    ("exception", re.compile(r"\b[a-zA-Z_.]*Exception\b", re.IGNORECASE)),
    ("error", re.compile(r"\bERROR\b", re.IGNORECASE)),
    ("critical", re.compile(r"\bCRITICAL\b", re.IGNORECASE)),
]


@dataclass
class LogFinding:
    source: str
    line_no: int
    line: str
    category: str
    suggestion: str

    @property
    def normalized_message(self) -> str:
        return re.sub(r"\s+", " ", self.line.strip().lower())


@dataclass
class AnalysisReport:
    findings: List[LogFinding]
    totals_by_category: Dict[str, int]
    top_messages: List[tuple[str, int]]
    scanned_sources: int

    @property
    def total_findings(self) -> int:
        return len(self.findings)


SUGGESTION_HINTS = [
    (re.compile(r"connection refused|failed to connect|connection reset", re.IGNORECASE),
     "Verify service availability and network/firewall settings."),
    (re.compile(r"timeout", re.IGNORECASE), "Investigate upstream slowness or increase timeout settings."),
    (re.compile(r"not found|no such file|FileNotFound", re.IGNORECASE), "Confirm the path or resource exists and permissions are correct."),
    (re.compile(r"permission denied|access denied", re.IGNORECASE), "Check user permissions or run with elevated privileges."),
    (re.compile(r"out of memory|oom", re.IGNORECASE), "Reduce workload, increase memory limits, or enable paging."),
]


def _suggest_for_line(line: str) -> str:
    for pattern, suggestion in SUGGESTION_HINTS:
        if pattern.search(line):
            return suggestion
    return "Review surrounding context for the root cause and retry the failing action."


def _match_category(line: str) -> str | None:
    for category, pattern in ERROR_PATTERNS:
        if pattern.search(line):
            return category
    return None


def analyze_logs(sources: Iterable[LogSource]) -> AnalysisReport:
    findings: List[LogFinding] = []
    totals: Dict[str, int] = defaultdict(int)
    message_counter: Counter[str] = Counter()

    scanned_sources = 0
    for source in sources:
        scanned_sources += 1
        for idx, line in enumerate(source.lines, start=1):
            category = _match_category(line)
            if not category:
                continue
            suggestion = _suggest_for_line(line)
            finding = LogFinding(
                source=source.name,
                line_no=idx,
                line=line,
                category=category,
                suggestion=suggestion,
            )
            findings.append(finding)
            totals[category] += 1
            message_counter[finding.normalized_message] += 1

    top_messages = message_counter.most_common(5)
    return AnalysisReport(
        findings=findings,
        totals_by_category=dict(totals),
        top_messages=top_messages,
        scanned_sources=scanned_sources,
    )
