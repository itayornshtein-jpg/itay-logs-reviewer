"""Identify and categorize errors from log sources."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List

from .reader import LogSource

ERROR_PATTERNS = [
    ("traceback", re.compile(r"Traceback \(most recent call last\)", re.IGNORECASE)),
    (
        "exception",
        re.compile(r"\b[a-zA-Z_.]+(?:Exception|Error)\b", re.IGNORECASE),
    ),
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
class ResizeAction:
    line_no: int
    status: str
    line: str


@dataclass
class AnalysisReport:
    findings: List[LogFinding]
    totals_by_category: Dict[str, int]
    top_messages: List[tuple[str, int]]
    scanned_sources: int
    resize_actions: Dict[str, List[ResizeAction]] = field(default_factory=dict)
    collector_tail: List[str] = field(default_factory=list)
    agent_tail: List[str] = field(default_factory=list)
    unique_errors: List[LogFinding] = field(default_factory=list)

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
    resize_actions: Dict[str, List[ResizeAction]] = defaultdict(list)
    collector_tail: List[str] = []
    agent_tail: List[str] = []

    scanned_sources = 0
    for source in sources:
        scanned_sources += 1
        lowered_name = source.name.lower()
        is_resize_log = lowered_name.endswith("resizeactions.log")

        for idx, line in enumerate(source.lines, start=1):
            if is_resize_log:
                uuid_match = re.search(
                    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
                    line,
                )
                if uuid_match:
                    status_match = re.search(r"status[:=\s\"]*(?P<status>[\w-]+)", line, re.IGNORECASE)
                    status = status_match.group("status") if status_match else "unknown"
                    resize_actions[uuid_match.group(0)].append(
                        ResizeAction(line_no=idx, status=status, line=line.strip())
                    )

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

        if lowered_name.endswith("collectorhc.log"):
            collector_tail = source.lines[-5:]
        if lowered_name.endswith("agent.log"):
            agent_tail = source.lines[-15:]

    unique_errors: List[LogFinding] = []
    seen_messages = set()
    for finding in findings:
        if finding.normalized_message in seen_messages:
            continue
        seen_messages.add(finding.normalized_message)
        unique_errors.append(finding)

    top_messages = message_counter.most_common(5)
    return AnalysisReport(
        findings=findings,
        totals_by_category=dict(totals),
        top_messages=top_messages,
        scanned_sources=scanned_sources,
        resize_actions={key: value[-5:] for key, value in resize_actions.items()},
        collector_tail=collector_tail[-5:],
        agent_tail=agent_tail[-15:],
        unique_errors=unique_errors,
    )
