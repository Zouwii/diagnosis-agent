"""统一的 Agent 日志"""
from datetime import datetime, timezone


def log(node: str, message: str, **kwargs):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
    print(f"[{ts}] [{node}] {message} {extra}")
