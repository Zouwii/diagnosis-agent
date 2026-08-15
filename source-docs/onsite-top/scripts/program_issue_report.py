#!/usr/bin/env python3
"""program_issue_detail Q2 标签统计报告。

program_issue 使用自己的 customField ID，不能复用 onsite_problem 的字段映射。
统计口径：created_at_ding + executor_id，问题类型和原因直接读取已解析的层级列。
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from onsite_top import db_config, fmtpct, get_db_connection, markdown_table, quarter_dates, render_template

PROGRAM_CF = {
    "description": "624e4bf0972b3d03d3008c4c",
    "problem_type": "67c56f477ed2b4b7bbd0cd69",
    "prompt": "67c572129590cd29ac9c5137",
    "cause": "67c571aa5aed540b545e208c",
    "handling": "687622865d635d4ab503716c",
}
EXECUTORS = {"潘铮": "2108411066921750", "潘峥": "2108411066921750", "panzheng": "2108411066921750"}


def parse_customfields(raw):
    if isinstance(raw, list):
        fields = raw
    else:
        try:
            obj = raw if isinstance(raw, dict) else json.loads(raw or "{}")
        except (TypeError, ValueError):
            return {}
        fields = obj if isinstance(obj, list) else obj.get("customFields") or obj.get("customfields") or []
    result = {}
    for field in fields:
        if not isinstance(field, dict):
            continue
        cfid = str(field.get("customFieldId") or field.get("customfieldId") or field.get("cfId") or "")
        key = next((k for k, v in PROGRAM_CF.items() if v == cfid), None)
        if not key:
            continue
        values = field.get("value") or []
        titles = [str(v.get("title") or "").strip() for v in values if isinstance(v, dict) and v.get("title")]
        if titles:
            result[key] = "; ".join(titles)
    return result


def fetch_records(conn, start, end, executor_id):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT task_id, content, raw_json, created_at_ding,
               problem_type_1, problem_type_2,
               cause_level_1, cause_level_2, cause_level_3, software_version
        FROM program_issue_detail
        WHERE created_at_ding >= %s AND created_at_ding < %s AND executor_id = %s
        ORDER BY created_at_ding
    """, (start, end, executor_id))
    rows = cursor.fetchall()
    cursor.close()
    records = []
    for number, (task_id, content, raw, created, type1, type2, cause1, cause2, cause3, software_version) in enumerate(rows, 1):
        tags = parse_customfields(raw)
        problem_type_levels = [x for x in (type1, type2) if x]
        cause_levels = [x for x in (cause1, cause2, cause3) if x]
        records.append({
            "num": number,
            "task_id": task_id,
            "date": str(created)[:10] if created else "",
            "description": tags.get("description") or content or "",
            "problem_type_levels": problem_type_levels,
            "cause_levels": cause_levels,
            "software_version": software_version or "未填写",
            "problem_type": " / ".join(problem_type_levels) or tags.get("problem_type") or "未填写",
            "cause": " / ".join(cause_levels) or tags.get("cause") or "未填写",
            "prompt": tags.get("prompt") or "未填写",
            "handling": tags.get("handling") or "未填写",
        })
    return records


def type_name(tag):
    if tag.startswith("TB单异常"):
        return "TB单异常/资料不全"
    if tag == "本体导航 / 定位":
        return "定位"
    if tag == "本体导航 / 建图" or tag.startswith("本体地图"):
        return "建图"
    if tag == "本体导航 / 非本体导航":
        return "非本体导航"
    if tag.startswith("本体导航"):
        return "导航"
    if tag == "未填写":
        return "未填写"
    return "非本体导航"


def navigation_cause_type(record):
    """按潘铮原报告口径，导航原因分布统计原因标签的第一级。"""
    levels = record.get("cause_levels") or []
    if levels:
        return levels[0]
    parts = [part.strip() for part in record.get("cause", "").split("/") if part.strip()]
    return parts[0] if parts else "未填写"


def cause_detail_sections(records, denominator, scope_name):
    """按潘铮原报告目录，对原因类型继续拆分原因一级/二级。"""
    order = ["软件bug", "其他模块", "外部因素", "未知原因"]
    sections = []
    for cause_type in order:
        subset = [r for r in records if navigation_cause_type(r) == cause_type]
        if not subset:
            continue

        # 原文明细表：cause_level_2 作为明细表的“原因一级”，
        # cause_level_3 作为明细表的“原因二级”。
        grouped = {}
        for record in subset:
            levels = record.get("cause_levels") or []
            module = levels[1] if len(levels) >= 2 and levels[1] else "/"
            detail = levels[2] if len(levels) >= 3 and levels[2] else "/"
            grouped.setdefault(module, {})
            grouped[module][detail] = grouped[module].get(detail, 0) + 1

        rows = []
        for module, details in grouped.items():
            first = True
            for detail, count in details.items():
                rows.append((module if first else "", detail, count, fmtpct(count, denominator)))
                first = False
        table = markdown_table(
            ["问题原因（一级）", "问题原因（二级）", "单数", f"占比（占{scope_name}问题原因）"],
            rows,
        )
        sections.append(f"* {cause_type}数据统计（{len(subset)}）\n\n{table}")
    return sections


def prompt_sections(records, total):
    """按原文只将导航、定位提示信息作为目录章节。"""
    sections = []
    for index, (type_name_value, title) in enumerate(
        [("导航", "导航原因提示信息分类统计"), ("定位", "定位原因提示信息分类统计")], 1
    ):
        subset = [r for r in records if r["type_name"] == type_name_value]
        if not subset:
            continue
        counts = Counter(r["prompt"] for r in subset)
        rows = [(label, count, fmtpct(count, len(subset))) for label, count in counts.most_common()]
        rows.append(("合计", len(subset), "100.00%"))
        table = markdown_table(["提示标签", "单数", f"占{type_name_value}问题比例"], rows)
        sections.append(f"### 1.3.{index} {title}\n\n{table}")
    return "\n\n".join(sections)


def navigation_software_bug_table(records):
    """导航组软件 bug：版本为列，模块为行，单元格为问题单数。"""
    modules = ["nav-manager", "nav-net", "nav-task"]
    subset = [
        r for r in records
        if r["type_name"] == "导航"
        and navigation_cause_type(r) == "软件bug"
    ]
    versions = []
    for record in subset:
        version = record.get("software_version") or "未填写"
        if version not in versions:
            versions.append(version)
    counts = Counter(
        (r.get("cause_levels", [None, "未填写"])[1] or "未填写", r.get("software_version") or "未填写")
        for r in subset
    )
    rows = []
    for module in modules:
        rows.append((module, *(counts[(module, version)] for version in versions), sum(counts[(module, version)] for version in versions)))
    rows.append(("合计", *(sum(counts[(module, version)] for module in modules) for version in versions), len(subset)))
    return markdown_table(["问题模块\\软件版本", *versions, "合计"], rows)


def build_report(records, person, quarter, source_label):
    total = len(records)
    for record in records:
        record["type_name"] = type_name(record["problem_type"])
    order = ["导航", "定位", "建图", "非本体导航", "TB单异常/资料不全", "未填写"]
    type_counts = Counter(r["type_name"] for r in records)
    type_rows = [(name, type_counts[name], fmtpct(type_counts[name], total)) for name in order]
    type_rows.append(("合计", total, "100.00%"))

    cause_sections = []
    cause_index = 1
    for name in order:
        subset = [r for r in records if r["type_name"] == name]
        if not subset:
            continue
        if name in ("导航", "定位", "建图"):
            counts = Counter(navigation_cause_type(r) for r in subset)
            rows = [(cause, count, fmtpct(count, len(subset))) for cause, count in counts.most_common()]
            rows.append(("合计", len(subset), "100.00%"))
            table = markdown_table(["原因类型", "单数", "占比"], rows)
            type_title = {
                "导航": "本体导航/导航原因分类统计",
                "定位": "本体导航/定位原因分类统计",
                "建图": "本体导航/建图原因分类统计",
            }[name]
            cause_sections.append(f"### 1.2.{cause_index} {type_title}\n\n{table}")
            cause_index += 1
            cause_sections.extend(cause_detail_sections(subset, len(subset), name))
            continue
        else:
            counts = Counter((r["problem_type"], r["cause"]) for r in subset)
            rows = [(tag, cause, count, fmtpct(count, len(subset))) for (tag, cause), count in counts.most_common()]
            rows.append(("合计", "", len(subset), "100.00%"))
            table = markdown_table(["数据库问题类型标签", "数据库原因标签", "单数", "占该类型比例"], rows)
        cause_sections.append(f"**{name}原因分布**\n\n" + table)

    handling_counts = Counter(r["handling"] for r in records)
    handling_rows = [(k, v, fmtpct(v, total)) for k, v in handling_counts.most_common()]
    return {
        "title": person,
        "source_label": source_label,
        "generated_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total": total,
        "type_table": markdown_table(["问题类型", "单数", "占比"], type_rows),
        "cause_table": "\n\n".join(cause_sections),
        "prompt_table": prompt_sections(records, total),
        "stability_table": navigation_software_bug_table(records),
        "stability_title": "导航组软件bug",
        "handling_table": markdown_table(["问题处理方式标签", "单数", "占比"], handling_rows),
        "conclusions": "",
    }


def main():
    parser = argparse.ArgumentParser(description="program_issue_detail 标签统计报告")
    parser.add_argument("--person", default="潘铮")
    parser.add_argument("--quarter", default="Q2", type=str.upper, choices=["Q1", "Q2", "Q3", "Q4"])
    parser.add_argument("--year", default=2026, type=int)
    parser.add_argument("--output", default="")
    parser.add_argument("--template", default="")
    args = parser.parse_args()
    start, end = quarter_dates(args.year, args.quarter)
    conn = get_db_connection("benti")
    try:
        records = fetch_records(conn, start, end, EXECUTORS.get(args.person, args.person))
    finally:
        conn.close()
    if not records:
        raise SystemExit("ERROR: program_issue_detail 查询结果为空")
    base = Path(__file__).parent
    values = build_report(records, args.person, args.quarter, f"program_issue_detail (benti DB，{len(records)} 条 {args.quarter})")
    template = args.template or str(base / "report.template.md")
    output = Path(args.output) if args.output else base / f"{args.person}_{args.quarter}_program_issue_details.md"
    output.write_text(render_template("", template, values), encoding="utf-8")
    print(f"[DONE] → {output} ({len(records)} 条)")


if __name__ == "__main__":
    main()
