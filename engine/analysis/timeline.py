"""Time parsing, evidence-window ranking, and chronological finding order."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any


def extract_minutes(text: str) -> list[int]:
    return [int(hour) * 60 + int(minute) for hour, minute in re.findall(r"\b([01]?\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?\b", text or "")]


def extract_time_prefixes(text: str) -> list[str]:
    prefixes: list[str] = []
    for hour, minute in re.findall(r"\b([01]?\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?\b", text or ""):
        prefix = f"{int(hour):02d}:{minute}"
        if prefix not in prefixes:
            prefixes.append(prefix)
    return prefixes


def extract_date_stamp(*texts: str) -> str:
    combined = "\n".join(texts)
    for year, month, day in re.findall(r"\b(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?\b", combined):
        return f"{int(year):04d}{int(month):02d}{int(day):02d}"
    return next(iter(re.findall(r"\b(20\d{6})\b", combined)), "")


def parse_target_time(text: str) -> datetime | None:
    date_stamp = extract_date_stamp(text)
    match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?\b", text or "")
    if not match:
        return None
    hour, minute, second = int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)
    if date_stamp:
        return datetime.strptime(f"{date_stamp}{hour:02d}{minute:02d}{second:02d}", "%Y%m%d%H%M%S")
    return datetime(2000, 1, 1, hour, minute, second)


def parse_line_time(line: str) -> datetime | None:
    match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d):([0-5]\d)(?:[.,]\d+)?\b", line)
    if not match:
        return None
    date_match = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", line)
    year, month, day = (int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))) if date_match else (2000, 1, 1)
    return datetime(year, month, day, int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _normalize_target(target: datetime, line_time: datetime) -> datetime:
    return target.replace(year=line_time.year, month=line_time.month, day=line_time.day) if target.year == 2000 and target.year != line_time.year else target


def time_distance_seconds(line: str, target: datetime | None) -> int:
    line_time = parse_line_time(line)
    return int(abs((line_time - _normalize_target(target, line_time)).total_seconds())) if target and line_time else 999999


def in_time_window(line: str, target: datetime, minutes: int) -> bool:
    return time_distance_seconds(line, target) <= minutes * 60


def sort_findings(findings: list[dict[str, Any]], time_window: str) -> list[dict[str, Any]]:
    target_minutes = extract_minutes(time_window)
    severity = {"fatal": 0, "error": 1, "code": 2, "warn": 3, "context": 4}

    def score(item: dict[str, Any]) -> tuple[int, int, str, int]:
        text_minutes = extract_minutes(str(item.get("text", "")))
        distance = min((abs(value - target) for value in text_minutes for target in target_minutes), default=9999)
        return distance, severity.get(str(item.get("level", "")), 9), str(item.get("file", "")), int(item.get("line", 0))

    return sorted(findings, key=score)
