"""Read-only internal robot material collector."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from engine.utils import now_iso, write_json


ROBOT_SSH_TIMEOUT_SECONDS = 20

ROBOT_COLLECT_COMMANDS = [
    ("system.txt", "date; hostname; uptime; uname -a; df -h / /opt/jz 2>/dev/null; free -h 2>/dev/null"),
    ("version.txt", "export PATH=/opt/jz/bin:$PATH; jz_total_display 2>&1; echo '--- install history ---'; jz_install_history jz-total 2>/dev/null | tail -80"),
    ("emma-status.txt", "export PATH=/opt/jz/bin:$PATH; echo '--- emma_status -v ---'; echo 'robot123' | sudo -S /opt/jz/bin/emma_status -v 2>&1; echo '--- emma_errors ---'; echo 'robot123' | sudo -S /opt/jz/bin/emma_errors 2>&1; echo '--- emma_node_state ---'; echo 'robot123' | sudo -S /opt/jz/bin/emma_node_state 2>&1"),
    ("robot-links.txt", "export PATH=/opt/jz/bin:$PATH; echo '--- jlinks ---'; /opt/jz/bin/jlinks 2>&1; echo '--- jjobs list ---'; /opt/jz/bin/jjobs list 2>&1"),
    ("processes.txt", "export PATH=/opt/jz/bin:$PATH; echo '--- circusctl status ---'; /opt/jz/bin/circusctl status 2>&1; echo '--- circusctl list ---'; /opt/jz/bin/circusctl list 2>&1; echo '--- key processes ---'; ps -ef | grep -Ei 'agent|jmother|carly|nav|map|locali|cartographer|iosys|jrosth|jzhw|async|web-service' | grep -v grep | head -200"),
    ("ros.txt", "export PATH=/opt/jz/bin:$PATH; source /opt/ros/*/setup.bash 2>/dev/null; echo '--- rosnode list ---'; rosnode list 2>&1 | head -200; echo '--- rostopic list ---'; rostopic list 2>&1 | head -300; echo '--- route agent3 sample ---'; timeout 5 jz_rostopic /route/agent3 2>&1 | head -240"),
    ("log-inventory.txt", "echo '--- /opt/jz/log ---'; ls -lt /opt/jz/log 2>&1 | head -120; echo '--- dump ---'; ls -lt /opt/jz/log/dump 2>&1 | head -40; echo '--- backup_log ---'; ls -lt /opt/jz/log/backup_log 2>&1 | head -60"),
    ("recent-errors.log", "grep -ihE '622002|error|fail|fault|exception|traceback|timeout|disconnect|abnormal|报警|错误|故障' /opt/jz/log/agent3.log /opt/jz/log/agent-node.log /opt/jz/log/circus.log /opt/jz/log/jmother.log /opt/jz/log/carly-web.log /opt/jz/log/web-service.log /opt/jz/log/nav-manager*.log /opt/jz/log/map-manager*.log /opt/jz/log/localiser*.log 2>/dev/null | tail -300"),
    ("agent3-tail.log", "tail -n 500 /opt/jz/log/agent3.log 2>&1 || tail -n 500 /opt/jz/log/agent-node.log 2>&1"),
    ("circus-tail.log", "tail -n 200 /opt/jz/log/circus.log 2>&1"),
]


def run_robot_ssh_command(ip: str, remote_command: str) -> tuple[int, str]:
    sshpass = shutil.which("sshpass")
    if sshpass:
        command = [sshpass, "-p", "robot123", "ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=5", "-o", "BatchMode=no", f"jz@{ip}", remote_command]
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=ROBOT_SSH_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or "") + (exc.stderr or "")
            return 124, output + f"\ncommand timed out after {ROBOT_SSH_TIMEOUT_SECONDS}s\n"
        return result.returncode, (result.stdout or "") + (result.stderr or "")

    try:
        import paramiko
    except ImportError:
        return 127, "sshpass and paramiko are both unavailable; cannot collect robot data non-interactively.\n"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(ip, username="jz", password="robot123", timeout=5, banner_timeout=5, auth_timeout=5, look_for_keys=False, allow_agent=False)
        stdin, stdout, stderr = client.exec_command(remote_command, timeout=ROBOT_SSH_TIMEOUT_SECONDS)
        stdin.close()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return stdout.channel.recv_exit_status(), out + err
    except Exception as exc:
        return 255, f"paramiko ssh failed: {type(exc).__name__}: {exc}\n"
    finally:
        client.close()


def collect_internal_robot_materials(ip: str, raw_dir: Path) -> list[str]:
    robot_dir = raw_dir / "robot"
    robot_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    manifest: dict[str, Any] = {"ip": ip, "collected_at": now_iso(), "method": "sshpass ssh read-only commands", "commands": []}

    for filename, remote_command in ROBOT_COLLECT_COMMANDS:
        return_code, output = run_robot_ssh_command(ip, remote_command)
        target = robot_dir / filename
        target.write_text(output, encoding="utf-8", errors="replace")
        artifacts.append(str(target))
        manifest["commands"].append({"file": str(target.relative_to(raw_dir)), "return_code": return_code, "remote_command": remote_command, "bytes": len(output.encode("utf-8", errors="replace"))})
        if return_code in {124, 127, 255}:
            break

    manifest_path = robot_dir / "robot-collection-manifest.json"
    write_json(manifest_path, manifest)
    artifacts.append(str(manifest_path))
    if manifest["commands"] and manifest["commands"][-1]["return_code"] in {124, 127, 255}:
        last = manifest["commands"][-1]
        error_path = robot_dir / "robot-collect-error.txt"
        error_path.write_text(f"robot_ip: {ip}\nreturn_code: {last['return_code']}\nfailed_at: {last['file']}\nhint: SSH collection did not complete. Check network reachability, credentials, and sshpass availability.\n", encoding="utf-8")
        artifacts.append(str(error_path))
    return artifacts
