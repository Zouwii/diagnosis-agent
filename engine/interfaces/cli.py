"""Command-line interface for the modular diagnosis engine."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from engine.analysis.external_providers import enrich_with_external_evidence
from engine.teambition_client import download_deferred_attachments
from engine.utils import read_case_context, read_case_status
from engine.workflows import ResumeCaseRequest, RunCaseRequest, analyze_case, resume_case, run_case


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_NAME = "diagnosis.config.json"
SOURCE_ALIASES = {
    "auto": "auto",
    "tb": "tb_task",
    "teambition": "tb_task",
    "robot": "internal_robot",
    "internal": "internal_robot",
    "remote": "remote_site",
    "site": "remote_site",
    "local": "local_logs",
}
SOURCE_BUCKETS = {
    "tb_task": "teambition",
    "internal_robot": "robot-peek",
    "remote_site": "remote-hand",
    "local_logs": "local",
}
SOURCE_PREFIXES = {
    "tb_task": "tb",
    "internal_robot": "robot",
    "remote_site": "remote",
    "local_logs": "local",
}


def default_case_root() -> Path:
    return Path(os.environ.get("DIAGNOSIS_CASE_ROOT", str(PROJECT_ROOT / "data" / "cases"))).expanduser()


def default_config_path() -> Path:
    return Path(os.environ.get("DIAGNOSIS_CONFIG", str(Path.cwd() / DEFAULT_CONFIG_NAME))).expanduser()


def template_config() -> dict:
    return {
        "source": "auto",
        "task_url": "",
        "ip": "172.22.0.222",
        "frp_port": "",
        "robot_ip": "",
        "log_path": "",
        "symptom": "请填写问题现象",
        "time_window": "请填写问题发生时间",
        "knowledge_sources": [],
        "code_sources": [],
        "artifacts": [],
        "case_id": "",
        "case_root": str(default_case_root()),
        "force": False,
        "external_evidence": True,
    }


def write_template_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(template_config(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_config(path: Path | None) -> dict:
    if path is None:
        return {}
    if not path.exists():
        write_template_config(path)
        raise FileNotFoundError(f"config not found, created template: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"config must be a JSON object: {path}")
    return data


def _value(args: argparse.Namespace, config: dict, name: str, *aliases: str):
    current = getattr(args, name, None)
    if current not in (None, "", []):
        return current
    for key in (name, *aliases):
        if config.get(key) not in (None, "", []):
            return config[key]
    return current


def _items(value) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _task_id(task_url: str) -> str:
    match = re.search(r"/task/([A-Za-z0-9_-]+)", task_url)
    if match:
        return match.group(1)
    path = urlparse(task_url).path.rstrip("/")
    return path.split("/")[-1] if path else ""


def _source_type(value: str) -> str:
    key = value.strip().lower()
    if key not in SOURCE_ALIASES:
        raise ValueError(f"unsupported source '{value}'")
    return SOURCE_ALIASES[key]


def _infer_source(args: argparse.Namespace) -> str:
    if args.task_url or args.task_id:
        return "tb_task"
    if args.frp_port or (args.robot_ip and not args.ip):
        return "remote_site"
    if args.ip:
        return "internal_robot"
    if args.log_path:
        return "local_logs"
    raise ValueError("source=auto requires task, robot, remote-site, or local-log parameters")


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip() or "case").strip("-._")[:80] or "case"


def _resolve_case(value: str, root: Path) -> Path:
    direct = Path(value).expanduser()
    if direct.exists():
        return direct
    if (root / value).exists():
        return root / value
    for bucket in SOURCE_BUCKETS.values():
        candidate = root / bucket / value
        if candidate.exists():
            return candidate
    return root / value


def _apply_config(args: argparse.Namespace, *, include_source: bool = True) -> argparse.Namespace:
    config_path = Path(args.config).expanduser() if getattr(args, "config", None) else None
    config = load_config(config_path)
    mappings = {
        "task_url": ("taskUrl",),
        "task_id": ("taskId",),
        "ip": ("robot_ip_internal",),
        "frp_port": ("frpPort",),
        "robot_ip": ("site_robot_ip", "robotIp"),
        "log_path": ("logPath",),
        "symptom": (),
        "time_window": (),
        "case_root": ("caseRoot",),
    }
    for name, aliases in mappings.items():
        setattr(args, name, _value(args, config, name, *aliases))
    for name, config_name in (
        ("knowledge_source", "knowledge_sources"),
        ("code_source", "code_sources"),
        ("artifact", "artifacts"),
    ):
        setattr(args, name, _items(getattr(args, name, None) or config.get(config_name)))
    if include_source:
        args.source = _value(args, config, "source")
        args.case_id = _value(args, config, "case_id", "caseId")
    if config.get("external_evidence") is False:
        args.external_evidence = False
    if config.get("force") is True:
        args.force = True
    args.case_root = args.case_root or str(default_case_root())
    if not args.task_id and args.task_url:
        args.task_id = _task_id(str(args.task_url))
    return args


def command_run(args: argparse.Namespace) -> int:
    args = _apply_config(args)
    if not args.source:
        raise ValueError("source is required")
    source = _source_type(str(args.source))
    if source == "auto":
        source = _infer_source(args)
    required = {
        "tb_task": [("task_id", "--task-id or --task-url")],
        "internal_robot": [("ip", "--ip")],
        "remote_site": [("frp_port", "--frp-port"), ("robot_ip", "--robot-ip")],
        "local_logs": [("log_path", "--log-path")],
    }[source]
    missing = [flag for name, flag in required if not getattr(args, name)]
    if missing:
        raise ValueError(f"missing required arguments for {source}: {', '.join(missing)}")

    base = args.task_id or args.ip or args.robot_ip or (Path(args.log_path).name if args.log_path else "case")
    case_id = _slug(args.case_id or f"{SOURCE_PREFIXES[source]}-{str(base).replace('.', '-')}-{datetime.now():%Y%m%d-%H%M%S}")
    case_dir = Path(args.case_root).expanduser() / SOURCE_BUCKETS[source] / case_id
    if case_dir.exists() and not args.force:
        raise ValueError(f"case already exists: {case_dir} (use --force to overwrite)")
    if case_dir.exists():
        shutil.rmtree(case_dir)

    result = run_case(
        RunCaseRequest(
            case_id=case_id,
            case_dir=case_dir,
            source_type=source,
            symptom=args.symptom or "",
            time_window=args.time_window or "",
            task_id=args.task_id or "",
            task_url=args.task_url or "",
            robot_ip=args.ip or "",
            frp_port=args.frp_port or "",
            site_robot_ip=args.robot_ip or "",
            log_path=args.log_path or "",
            artifacts=args.artifact,
            knowledge_sources=args.knowledge_source,
            code_sources=args.code_source,
            collect_remote=args.collect,
            analyze=args.analyze,
            external_evidence=args.external_evidence,
            allow_large_downloads=args.allow_large_downloads,
            allow_all_attachments=args.allow_all_attachments,
        ),
        external_enricher=enrich_with_external_evidence,
    )
    for warning in result.collection.warnings:
        print(f"collection note: {warning}", file=sys.stderr)
    print(f"case_id: {case_id}\ncase_dir: {case_dir}\ncontext: {case_dir / 'context.json'}\nreport: {case_dir / 'report.md'}")
    return 0


def command_analyze(args: argparse.Namespace) -> int:
    case_dir = _resolve_case(args.case, Path(args.case_root).expanduser())
    context = analyze_case(
        case_dir,
        read_case_context(case_dir),
        external_enricher=enrich_with_external_evidence if args.external_evidence else None,
    )
    summary = context.get("analysis_summary", {})
    print(f"case_id: {context.get('case_id', case_dir.name)}\nstatus: {summary.get('conclusion_status', '')}\nreport: {case_dir / 'report.md'}")
    return 0


def command_resume(args: argparse.Namespace) -> int:
    args = _apply_config(args, include_source=False)
    case_dir = _resolve_case(args.case, Path(args.case_root).expanduser())
    context = resume_case(
        ResumeCaseRequest(
            case_dir=case_dir,
            symptom=args.symptom or "",
            time_window=args.time_window or "",
            task_id=args.task_id or "",
            task_url=args.task_url or "",
            robot_ip=args.ip or "",
            frp_port=args.frp_port or "",
            site_robot_ip=args.robot_ip or "",
            log_path=args.log_path or "",
            artifacts=args.artifact,
            knowledge_sources=args.knowledge_source,
            code_sources=args.code_source,
            collect_remote=args.collect,
            analyze=args.analyze,
            external_evidence=args.external_evidence,
        ),
        external_enricher=enrich_with_external_evidence,
    )
    print(f"case_id: {context.get('case_id', case_dir.name)}\ncase_dir: {case_dir}\nreport: {case_dir / 'report.md'}")
    return 0


def command_status(args: argparse.Namespace) -> int:
    case_dir = _resolve_case(args.case, Path(args.case_root).expanduser())
    print(json.dumps({"status": read_case_status(case_dir), "context": read_case_context(case_dir)}, ensure_ascii=False, indent=2))
    return 0


def command_export(args: argparse.Namespace) -> int:
    case_dir = _resolve_case(args.case, Path(args.case_root).expanduser())
    source = case_dir / {
        "report": "report.md",
        "handoff": "human-handoff.md",
        "knowledge": "knowledge-draft.md",
        "prompt": "next-prompt.md",
        "context": "context.json",
    }[args.kind]
    if not source.exists():
        raise FileNotFoundError(f"export target does not exist: {source}")
    if args.output:
        target = Path(args.output).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        print(target)
    else:
        sys.stdout.write(source.read_text(encoding="utf-8"))
    return 0


def command_list(args: argparse.Namespace) -> int:
    root = Path(args.case_root).expanduser()
    rows = []
    if root.exists():
        for context_path in sorted(root.glob("*/*/context.json")):
            case_dir = context_path.parent
            try:
                context = read_case_context(case_dir)
                status = read_case_status(case_dir)
            except (FileNotFoundError, ValueError):
                continue
            rows.append({
                "case_id": context.get("case_id", case_dir.name),
                "source_type": context.get("source_type", ""),
                "status": status.get("status", ""),
                "case_dir": str(case_dir),
            })
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def command_download_deferred(args: argparse.Namespace) -> int:
    case_dir = _resolve_case(args.case, Path(args.case_root).expanduser())
    manifest = case_dir / "raw" / "teambition-attachments.json"
    deferred = json.loads(manifest.read_text(encoding="utf-8")).get("deferred_attachments", [])
    if args.resource_ids:
        deferred = [item for item in deferred if item.get("resource_id") in args.resource_ids]
    if not deferred:
        print("no deferred attachments found for this case")
        return 0
    result = download_deferred_attachments(deferred, case_dir / "raw" / "teambition", case_dir / "extracted")
    print(f"downloaded: {len(result['downloaded'])}\nfailed: {len(result['failed'])}")
    return 0


def command_init_config(args: argparse.Namespace) -> int:
    path = Path(args.output).expanduser()
    if path.exists() and not args.force:
        raise ValueError(f"config already exists: {path} (use --force to overwrite)")
    write_template_config(path)
    print(path)
    return 0


def _common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config")
    parser.add_argument("--task-url")
    parser.add_argument("--task-id")
    parser.add_argument("--ip")
    parser.add_argument("--frp-port")
    parser.add_argument("--robot-ip")
    parser.add_argument("--log-path")
    parser.add_argument("--symptom")
    parser.add_argument("--time-window")
    parser.add_argument("--knowledge-source", action="append")
    parser.add_argument("--code-source", action="append")
    parser.add_argument("--artifact", action="append")
    parser.add_argument("--case-root")
    parser.add_argument("--no-analyze", dest="analyze", action="store_false")
    parser.add_argument("--no-collect", dest="collect", action="store_false")
    parser.add_argument("--no-external-evidence", dest="external_evidence", action="store_false")
    parser.add_argument("--skip-quota-check", action="store_true")
    parser.set_defaults(analyze=True, collect=True, external_evidence=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="diagnosis", description="Technical-support diagnosis case CLI")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    _common_arguments(run)
    run.add_argument("--source")
    run.add_argument("--case-id")
    run.add_argument("--force", action="store_true")
    run.add_argument("--allow-large-downloads", action="store_true")
    run.add_argument("--allow-all-attachments", action="store_true")
    run.set_defaults(func=command_run)

    resume = commands.add_parser("resume")
    resume.add_argument("case")
    _common_arguments(resume)
    resume.add_argument("--force", action="store_true")
    resume.set_defaults(func=command_resume)

    for name, function in (("status", command_status), ("analyze", command_analyze)):
        sub = commands.add_parser(name)
        sub.add_argument("case")
        sub.add_argument("--case-root", default=str(default_case_root()))
        if name == "analyze":
            sub.add_argument("--no-external-evidence", dest="external_evidence", action="store_false")
            sub.set_defaults(external_evidence=True)
        sub.set_defaults(func=function)

    export = commands.add_parser("export")
    export.add_argument("case")
    export.add_argument("--kind", choices=["report", "handoff", "knowledge", "prompt", "context"], default="report")
    export.add_argument("--output")
    export.add_argument("--case-root", default=str(default_case_root()))
    export.set_defaults(func=command_export)

    listed = commands.add_parser("list")
    listed.add_argument("--case-root", default=str(default_case_root()))
    listed.set_defaults(func=command_list)

    deferred = commands.add_parser("download-deferred")
    deferred.add_argument("case")
    deferred.add_argument("resource_ids", nargs="*")
    deferred.add_argument("--case-root", default=str(default_case_root()))
    deferred.set_defaults(func=command_download_deferred)

    init = commands.add_parser("init-config")
    init.add_argument("--output", default=DEFAULT_CONFIG_NAME)
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=command_init_config)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        argv = ["run", "--config", str(default_config_path())]
    try:
        args = build_parser().parse_args(argv)
        return int(args.func(args))
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
