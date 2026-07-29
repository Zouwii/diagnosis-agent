"""Public analyzer boundary for a prepared diagnosis Case.

The first implementation adapts the existing deterministic analyzer unchanged.
Future AI and multimodal analyzers will implement the same ``analyze`` method.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol


class CaseAnalyzer(Protocol):
    """Analyze existing Case material without collecting or reporting."""

    def analyze(self, case_dir: Path, context: dict[str, Any]) -> dict[str, Any]:
        """Return structured findings, routes, evidence, and confidence."""


AnalyzeImplementation = Callable[[Path, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class DeterministicCaseAnalyzer:
    """Compatibility adapter around the current rules-based implementation."""

    implementation: AnalyzeImplementation

    def analyze(self, case_dir: Path, context: dict[str, Any]) -> dict[str, Any]:
        return self.implementation(case_dir, context)
