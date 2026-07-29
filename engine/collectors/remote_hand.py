"""Read-only customer-site collector via remote-hand FRP tunnel."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from engine.collectors.ssh_robot import ROBOT_COLLECT_COMMANDS, ROBOT_SSH_TIMEOUT_SECONDS
from engine.utils import now_iso, write_json


REMOTE_HAND_SERVER = "frp2.aliyun01.iplusbot.cn"


def run_remote_hand_robot_command(frp_port: str, robot_ip: str, remote_command: str) -> tuple[int, str]:
    sshpass = shutil.which("sshpass")
    if not sshpass:
        return 127, "sshpass is unavailable; cannot collect remote-hand data non-interactively.\n"
    escaped = remote_command.replace("\\", "\\\\").replace('"', '\\"')
    toolkit_command = f'python.exe %CORE_DIR%\\ssh-robot.py {robot_ip} "{escaped}"'
    command = [sshpass, "-p", "robot123", "ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=10", "-p", str(frp_port), f"jz@{REMOTE_HAND_SERVER}", toolkit_command]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=ROBOT_SSH_TIMEOUT_SECONDS + 10)
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        return 124, output + f"\ncommand timed out after {ROBOT_SSH_TIMEOUT_SECONDS + 10}s\n"
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def collect_remote_site_materials(frp_port: str, robot_ip: str, raw_dir: Path) -> list[str]:
    remote_dir = raw_dir / "remote-hand"
    remote_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    manifest: dict[str, Any] = {"frp_port": str(frp_port), "site_robot_ip": robot_ip, "server": REMOTE_HAND_SERVER, "collected_at": now_iso(), "method": "remote-hand ssh tunnel + toolkit ssh-robot.py read-only commands", "commands": []}

    for filename, remote_command in ROBOT_COLLECT_COMMANDS:
        return_code, output = run_remote_hand_robot_command(str(frp_port), robot_ip, remote_command)
        target = remote_dir / filename
        target.write_text(output, encoding="utf-8", errors="replace")
        artifacts.append(str(target))
        manifest["commands"].append({"file": str(target.relative_to(raw_dir)), "return_code": return_code, "remote_command": remote_command, "bytes": len(output.encode("utf-8", errors="replace"))})
        if return_code in {124, 127, 255}:
            break

    manifest_path = remote_dir / "remote-hand-collection-manifest.json"
    write_json(manifest_path, manifest)
    artifacts.append(str(manifest_path))
    if manifest["commands"] and manifest["commands"][-1]["return_code"] in {124, 127, 255}:
        last = manifest["commands"][-1]
        error_path = remote_dir / "remote-hand-collect-error.txt"
        error_path.write_text(f"frp_port: {frp_port}\nsite_robot_ip: {robot_ip}\nreturn_code: {last['return_code']}\nfailed_at: {last['file']}\nhint: Remote-hand collection did not complete. Check start.bat, frp port, site robot IP, and toolkit version.\n", encoding="utf-8")
        artifacts.append(str(error_path))
    return artifacts
