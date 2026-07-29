"""Parsers and deterministic evidence helpers for deeper system insights."""

from __future__ import annotations

import re


def clean_text(text: str) -> str:
    return text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")


def parse_emma_errors(text: str) -> list[dict[str, str]]:
    clean = clean_text(text)
    marker = "--- emma_errors ---"
    if marker not in clean:
        return []
    section = clean.split(marker, 1)[1].split("--- emma_node_state ---", 1)[0]
    errors: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw in section.splitlines():
        line = raw.rstrip()
        if line.startswith(("jstate/", "/jstate/")):
            if current:
                errors.append(current)
            current = {"name": line.strip().rstrip(":")}
        elif current and ":" in line:
            key, value = line.split(":", 1)
            if key.strip() in {"details", "level", "sub_id", "timestamp", "trigger"}:
                current[key.strip()] = value.strip().strip("'\"")
    if current:
        errors.append(current)
    return errors


def parse_version_mismatches(text: str) -> tuple[str, list[str]]:
    title = ""
    mismatches: list[str] = []
    for raw in clean_text(text).splitlines():
        line = re.sub(r"\s+", " ", raw.strip())
        if line.startswith("Jz-total("):
            title = line
        elif "-->" in line and not line.endswith("--> OK") and " OK" not in line.split("-->", 1)[1]:
            mismatches.append(line)
    return title, mismatches


def parse_stopped_watchers(text: str) -> list[str]:
    ignored = {"fm_localiser_node", "jz-rosbridge-server", "lego_map_optimization"}
    stopped: list[str] = []
    in_status = False
    for raw in clean_text(text).splitlines():
        line = raw.strip()
        if line == "--- circusctl status ---":
            in_status = True
        elif line.startswith("--- ") and in_status:
            break
        elif in_status and ":" in line:
            name, state = (part.strip() for part in line.split(":", 1))
            if state == "stopped" and name not in ignored:
                stopped.append(name)
    return stopped


def count_pattern(text: str, pattern: str) -> int:
    return len(re.findall(pattern, clean_text(text), flags=re.IGNORECASE))
