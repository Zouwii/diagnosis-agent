"""Deterministic extraction of text evidence from Case materials."""

from __future__ import annotations

import re
from pathlib import Path


TEXT_SUFFIXES = {
    ".conf", ".ini", ".json", ".log", ".md", ".out", ".text", ".txt", ".yaml", ".yml",
}
SKIP_SUFFIXES = {".bag", ".db", ".gz", ".jpeg", ".jpg", ".mp4", ".png", ".tar", ".tgz", ".zip"}
MAX_ANALYSIS_FILE_BYTES = 2 * 1024 * 1024

FINDING_PATTERNS = [
    ("fatal", re.compile(r"\b(fatal|segmentation fault|core dumped|abort(?:ed)?)\b", re.IGNORECASE)),
    ("error", re.compile(r"\b(error|exception|traceback|failed|failure|timeout|timed out)\b", re.IGNORECASE)),
    ("warn", re.compile(r"\b(warn|warning|disconnect|lost|invalid|missing|denied)\b", re.IGNORECASE)),
]
ERROR_CODE_PATTERNS = [
    re.compile(r"(?:错误码|故障码|报警码|error[_ -]?code|fault[_ -]?code|code)\s*[:=：]?\s*([0-9]{4,8})", re.IGNORECASE),
    re.compile(r"报\s*([0-9]{5,8})(?:\s*的)?(?:错误码|故障码|报警码)?"),
    re.compile(r"([0-9]{5,8})\s*(?:错误码|故障码|报警码)"),
]
ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


def is_probably_text_file(path: Path) -> bool:
    if path.name == "robot-collection-manifest.json":
        return False
    suffix = path.suffix.lower()
    if suffix in SKIP_SUFFIXES:
        return False
    if suffix in TEXT_SUFFIXES:
        return True
    if ".log." in path.name.lower():
        return True
    return path.name.lower() in {"version", "ros_dump"}


def iter_analysis_files(case_dir: Path) -> list[Path]:
    """Return small readable files suitable for a full deterministic scan."""
    return _iter_analysis_files(case_dir, include_large=False)


def iter_large_analysis_files(case_dir: Path) -> list[Path]:
    """Return readable files that need time-window or targeted processing."""
    return _iter_analysis_files(case_dir, include_large=True)


def _iter_analysis_files(case_dir: Path, *, include_large: bool) -> list[Path]:
    files: list[Path] = []
    for root_name in ("raw", "extracted"):
        root = case_dir / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if "log-windows" in path.parts or not path.is_file() or not is_probably_text_file(path):
                continue
            try:
                is_large = path.stat().st_size > MAX_ANALYSIS_FILE_BYTES
            except OSError:
                continue
            if is_large == include_large:
                files.append(path)
    return files


def read_text_lossy(path: Path) -> str:
    """Read text safely; reject files that look binary before decoding."""
    data = path.read_bytes()
    if b"\x00" in data[:4096]:
        return ""
    return data.decode("utf-8", errors="replace")


def extract_error_codes(*texts: str) -> list[str]:
    codes: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for pattern in ERROR_CODE_PATTERNS:
            for match in pattern.finditer(text or ""):
                code = match.group(1)
                if code not in seen:
                    seen.add(code)
                    codes.append(code)
    return codes


def classify_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or (stripped.startswith("/") and " " not in stripped):
        return None
    if '"remote_command"' in stripped or "rosbag/record record" in stripped:
        return None
    if "most likely raised during interpreter shutdown" in stripped:
        return None
    if re.fullmatch(r'"?(failed|errors?|warnings?)"?\s*:\s*\[\s*\],?', stripped, re.IGNORECASE):
        return None
    for level, pattern in FINDING_PATTERNS:
        if pattern.search(line):
            return level
    return None


def short_line(line: str, limit: int = 240) -> str:
    line = ANSI_PATTERN.sub("", line)
    line = re.sub(r"\s+", " ", line.strip())
    return line if len(line) <= limit else line[: limit - 3] + "..."
