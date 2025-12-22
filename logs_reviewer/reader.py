"""Utilities for loading log lines from files or archives."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List
import zipfile

# Allowed extensions for plain text logs
TEXT_SUFFIXES = {".log", ".txt", ".out", ".err"}


@dataclass
class LogSource:
    """Represents a log source with its name and lines."""

    name: str
    lines: List[str]


def _read_text_file(path: Path) -> List[str]:
    try:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except FileNotFoundError:
        raise


def _iter_zip_files(zip_path: Path) -> Iterator[LogSource]:
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            suffix = Path(info.filename).suffix.lower()
            if suffix and suffix not in TEXT_SUFFIXES:
                continue
            with archive.open(info) as file:
                try:
                    content = file.read().decode("utf-8", errors="ignore")
                except Exception:
                    continue
            lines = content.splitlines()
            yield LogSource(name=f"{zip_path.name}:{info.filename}", lines=lines)


def _iter_directory(path: Path) -> Iterator[LogSource]:
    for child in path.rglob("*"):
        if child.is_dir():
            continue
        suffix = child.suffix.lower()
        if suffix and suffix not in TEXT_SUFFIXES:
            continue
        yield LogSource(name=str(child.relative_to(path)), lines=_read_text_file(child))


def collect_sources(target: Path) -> Iterable[LogSource]:
    """Collect log sources from a file, directory, or zip archive."""

    target = target.expanduser().resolve()
    if target.is_dir():
        yield from _iter_directory(target)
    elif zipfile.is_zipfile(target):
        yield from _iter_zip_files(target)
    elif target.is_file():
        yield LogSource(name=target.name, lines=_read_text_file(target))
    else:
        raise FileNotFoundError(f"Path not found: {target}")
