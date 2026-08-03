"""Server-controlled mapping from diagnosis entry modes to collection Skills."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DiagnosisModeSpec:
    mode: str
    collection_skill: str
    analysis_skill: str = "robot-diagnosis"


MODE_SPECS: dict[str, DiagnosisModeSpec] = {
    "internal_robot": DiagnosisModeSpec("internal_robot", "robot-peek"),
    "tb_task": DiagnosisModeSpec("tb_task", "teambition"),
    "remote_site": DiagnosisModeSpec("remote_site", "remote-hand"),
    # Local material is already collected, so robot-diagnosis starts in offline mode.
    "local_logs": DiagnosisModeSpec("local_logs", "robot-diagnosis"),
}


def get_mode_spec(mode: str) -> DiagnosisModeSpec:
    try:
        return MODE_SPECS[mode]
    except KeyError as exc:
        allowed = ", ".join(MODE_SPECS)
        raise ValueError(f"unsupported diagnosis mode: {mode!r}; allowed: {allowed}") from exc


def validate_mode_params(mode: str, params: dict[str, Any]) -> DiagnosisModeSpec:
    """Validate the minimum inputs needed by the selected fixed Skill route."""
    spec = get_mode_spec(mode)

    if mode == "internal_robot" and not str(params.get("robot_ip") or "").strip():
        raise ValueError("internal_robot mode requires robot_ip")
    if mode == "tb_task" and not (
        str(params.get("task_url") or "").strip() or str(params.get("task_id") or "").strip()
    ):
        raise ValueError("tb_task mode requires task_url or task_id")
    if mode == "remote_site":
        if not str(params.get("frp_port") or "").strip():
            raise ValueError("remote_site mode requires frp_port")
        if not str(params.get("site_robot_ip") or "").strip():
            raise ValueError("remote_site mode requires site_robot_ip")
    if mode == "local_logs" and not str(params.get("log_path") or "").strip():
        raise ValueError("local_logs mode requires log_path or upload_id")

    return spec
