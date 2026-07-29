"""Create reusable log excerpts around an incident time."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from engine.analysis.material_scan import MAX_ANALYSIS_FILE_BYTES
from engine.analysis.routing import log_priority_rank, normalize_log_name, prioritize_analysis_files
from engine.analysis.timeline import parse_line_time


MAX_WINDOW_LARGE_FILES = 1
MAX_WINDOW_SMALL_FILES = 4


def safe_relative_text(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def window_file_name(path: Path, date_stamp: str, start: datetime, end: datetime) -> str:
    base = normalize_log_name(path).replace("/", "_").replace("\\", "_")
    stem = base[:-4] if base.endswith(".log") else Path(base).stem
    return f"{stem}-{date_stamp or 'nodate'}-{start:%H%M%S}-{end:%H%M%S}.log"


def extract_window_evidence(
    *,
    source_path: Path,
    case_dir: Path,
    target_time: datetime,
    date_stamp: str,
    minutes: int = 5,
    max_bytes: int = 50 * 1024 * 1024,
) -> dict[str, Any]:
    window_dir = case_dir / "extracted" / "log-windows"
    window_dir.mkdir(parents=True, exist_ok=True)
    start = target_time - timedelta(minutes=minutes)
    end = target_time + timedelta(minutes=minutes)
    output_path = window_dir / window_file_name(source_path, date_stamp, start, end)
    if output_path.exists() and output_path.stat().st_size > 0:
        with output_path.open("r", encoding="utf-8", errors="replace") as existing:
            matched_lines = sum(1 for line in existing if not line.startswith("#"))
        return {
            "source_file": safe_relative_text(source_path, case_dir),
            "window_file": safe_relative_text(output_path, case_dir),
            "window_minutes": minutes,
            "start": start.strftime("%H:%M:%S"),
            "end": end.strftime("%H:%M:%S"),
            "matched_lines": matched_lines,
            "first_source_line": 0,
            "last_source_line": 0,
            "truncated": False,
            "reused": True,
        }

    matched_lines = written_bytes = first_line = last_line = 0
    truncated = False
    with source_path.open("r", encoding="utf-8", errors="replace") as source, output_path.open("w", encoding="utf-8") as out:
        out.write(f"# source: {safe_relative_text(source_path, case_dir)}\n# window: {start:%H:%M:%S} ~ {end:%H:%M:%S}\n")
        for line_no, line in enumerate(source, start=1):
            line_time = parse_line_time(line)
            if not line_time:
                continue
            normalized_target = target_time
            if target_time.year != line_time.year and target_time.year == 2000:
                normalized_target = target_time.replace(year=line_time.year, month=line_time.month, day=line_time.day)
            if line_time > normalized_target + timedelta(minutes=minutes) and matched_lines:
                break
            if abs((line_time - normalized_target).total_seconds()) > minutes * 60:
                continue
            encoded = line.encode("utf-8", errors="replace")
            if written_bytes + len(encoded) > max_bytes:
                truncated = True
                break
            first_line = first_line or line_no
            last_line = line_no
            matched_lines += 1
            written_bytes += len(encoded)
            out.write(line)
    return {
        "source_file": safe_relative_text(source_path, case_dir),
        "window_file": safe_relative_text(output_path, case_dir),
        "window_minutes": minutes,
        "start": start.strftime("%H:%M:%S"),
        "end": end.strftime("%H:%M:%S"),
        "matched_lines": matched_lines,
        "first_source_line": first_line,
        "last_source_line": last_line,
        "truncated": truncated,
    }


def build_window_evidence(
    *,
    case_dir: Path,
    files: list[Path],
    target_time: datetime | None,
    date_stamp: str,
    route_spec: dict[str, Any],
    minutes: int = 5,
) -> list[dict[str, Any]]:
    if not target_time:
        return []
    selected_large: list[Path] = []
    selected_small: list[Path] = []
    for path in prioritize_analysis_files(files, route_spec):
        if log_priority_rank(path, route_spec)[0] > 1 or (date_stamp and date_stamp not in path.name):
            continue
        try:
            is_large = path.stat().st_size > MAX_ANALYSIS_FILE_BYTES
        except OSError:
            is_large = True
        if is_large and len(selected_large) < MAX_WINDOW_LARGE_FILES:
            selected_large.append(path)
        elif not is_large and len(selected_small) < MAX_WINDOW_SMALL_FILES:
            selected_small.append(path)
        if len(selected_large) >= MAX_WINDOW_LARGE_FILES and len(selected_small) >= MAX_WINDOW_SMALL_FILES:
            break

    windows: list[dict[str, Any]] = []
    for path in [*selected_large, *selected_small]:
        try:
            windows.append(extract_window_evidence(source_path=path, case_dir=case_dir, target_time=target_time, date_stamp=date_stamp, minutes=minutes))
        except OSError as exc:
            windows.append({"source_file": safe_relative_text(path, case_dir), "window_file": "", "window_minutes": minutes, "matched_lines": 0, "error": str(exc)})
    return windows
