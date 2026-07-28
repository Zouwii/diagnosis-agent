#!/usr/bin/env python3
"""
一次性迁移：从 onsite_problem_details.raw_json 提取 customField → 写入对应解析列。
运行方式：python3 migrate_customfields.py [--dry-run]
"""
import json, re, sys
from datetime import datetime

# SSH tunnel: sshpass -p '1' ssh -fN -L 3307:127.0.0.1:3306 jz@172.19.3.79
DB_CONFIG = {
    "host": "127.0.0.1", "port": 3307,
    "user": "root", "password": "123456",
    "database": "onsite_problem", "charset": "utf8mb4",
}

# cfId → column 映射
CF_MAP = {
    "659369d32ae435dd0b3c803e": "vehicle_model",        # 车型 (cascading)
    "637c2e2ffbb56c003fdd74e9": "carrier_type",          # 载具配置 (dropDown)
    "62c51d82d7ab965fbdebd686": "occurrence_frequency",  # 复现概率 (dropDown)
    "6645bd4d22e1f70dadb953f6": "software_version",      # JZTOTAL包版本 (dropDown)
    "624e4bf0972b3d03d3008c4c": "problem_description",   # 问题描述 (text)
    "69241440caabefe748f91359": "investigation_conclusion",  # 排查结论 (rtf)
    "692414313ffb7e9afc4e9f43": "doc_value",              # 排查文档价值 (dropDown)
    "6924139133e26574155ea68b": "investigation_doc",     # 排查文档 (lookup2)
    "625f75e9882430143f5bfd0a": "attachments",            # 附件 (work, 特殊：分号拼接)
    "691a95544ce9d3d5a5e541e1": "problem_category",       # 问题类型分类 (cascading)
    "691a95f304c9e52bc9058bd6": "problem_module",         # 问题模块分类 (dropDown)
    "62651eadef4cf6063244aa5c": "guide_doc",              # 指导文档 (lookup)
    "625f8339882430143f5c0b9a": "formal_version",         # 正式版本 (text)
    "625f8317d472ef3d5c2f39a4": "root_cause",              # 原因分析 (text)
    "625f8329b416f5118bb099b2": "solution",               # 解决方案 (text)
    "68f637359ae2d0854e946cb3": "submitter",              # 提交者 (text)
}


def parse_raw_json(raw: str) -> dict:
    """从 raw_json 提取所有 customField 值，返回 {column_name: value}"""
    try:
        task = json.loads(raw)
    except:
        return {}

    cfs = task.get("customfields") or task.get("customFields") or []
    if not isinstance(cfs, list):
        return {}

    result = {}
    attachment_titles = []

    for cf in cfs:
        if not isinstance(cf, dict):
            continue
        cfid = str(cf.get("cfId") or cf.get("customFieldId") or cf.get("customfieldId") or "")
        if not cfid or cfid not in CF_MAP:
            continue

        col = CF_MAP[cfid]
        values = cf.get("value") or []
        if not isinstance(values, list) or not values:
            continue

        first = values[0]
        if isinstance(first, dict):
            title = str(first.get("title") or "").strip()

            # attachments 类型：收集所有 title，用分号拼接
            if col == "attachments":
                for v in values:
                    if isinstance(v, dict):
                        t = str(v.get("title") or "").strip()
                        if t:
                            attachment_titles.append(t)
                continue

            if title:
                result[col] = title

    if attachment_titles:
        result["attachments"] = "; ".join(attachment_titles)

    return result


def main():
    dry_run = "--dry-run" in sys.argv
    try:
        import pymysql
    except ImportError:
        print("ERROR: pymysql not installed", file=sys.stderr)
        sys.exit(1)

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # 统计待处理数
    cursor.execute("SELECT COUNT(*) FROM onsite_problem_details WHERE raw_json IS NOT NULL AND raw_json != ''")
    total = cursor.fetchone()[0]
    print(f"[INFO] 待处理: {total} 条")

    if dry_run:
        # Dry-run: 只打印前 10 条
        print("[DRY-RUN] 预览前 10 条:")
        cursor.execute("SELECT id, task_id, raw_json FROM onsite_problem_details WHERE raw_json IS NOT NULL ORDER BY id LIMIT 10")
        for row in cursor.fetchall():
            rid, tid, raw = row
            extracted = parse_raw_json(raw)
            if extracted:
                print(f"  id={rid} task={tid[:20]}: {extracted}")
            else:
                print(f"  id={rid} task={tid[:20]}: (no customField data)")
        cursor.close()
        conn.close()
        return

    # 批量更新
    print(f"[INFO] 开始迁移 {total} 条...")
    cursor.execute("SELECT id, raw_json FROM onsite_problem_details WHERE raw_json IS NOT NULL AND raw_json != ''")
    updated = 0
    skipped = 0
    batch_count = 0
    errors = 0

    update_sql = """UPDATE onsite_problem_details SET
        vehicle_model=%s, carrier_type=%s, occurrence_frequency=%s,
        software_version=%s, problem_description=%s, investigation_conclusion=%s,
        doc_value=%s, investigation_doc=%s, attachments=%s,
        problem_category=%s, problem_module=%s, guide_doc=%s,
        formal_version=%s, root_cause=%s, solution=%s, submitter=%s
    WHERE id=%s"""

    cols = [
        "vehicle_model", "carrier_type", "occurrence_frequency",
        "software_version", "problem_description", "investigation_conclusion",
        "doc_value", "investigation_doc", "attachments",
        "problem_category", "problem_module", "guide_doc",
        "formal_version", "root_cause", "solution", "submitter",
    ]

    for row in cursor.fetchall():
        rid, raw = row
        extracted = parse_raw_json(raw)

        if not extracted:
            skipped += 1
            continue

        try:
            vals = [extracted.get(col, None) for col in cols]
            vals.append(rid)
            cursor.execute(update_sql, vals)
            updated += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"[ERROR] id={rid}: {e}", file=sys.stderr)

        batch_count += 1
        if batch_count % 2000 == 0:
            conn.commit()
            print(f"  ... {batch_count}/{total} (updated={updated}, skipped={skipped}, errors={errors})")

    conn.commit()
    cursor.close()
    conn.close()

    print(f"\n[DONE] 总={total}, 更新={updated}, 跳过(无数据)={skipped}, 错误={errors}")

    # 验证
    verify_conn = pymysql.connect(**DB_CONFIG)
    vc = verify_conn.cursor()
    vc.execute("""
        SELECT
            SUM(CASE WHEN vehicle_model IS NOT NULL AND vehicle_model != '' THEN 1 ELSE 0 END) as vehicle,
            SUM(CASE WHEN problem_description IS NOT NULL AND problem_description != '' THEN 1 ELSE 0 END) as desc_ok,
            SUM(CASE WHEN software_version IS NOT NULL AND software_version != '' THEN 1 ELSE 0 END) as ver,
            SUM(CASE WHEN problem_module IS NOT NULL AND problem_module != '' THEN 1 ELSE 0 END) as mod_ok,
            SUM(CASE WHEN root_cause IS NOT NULL AND root_cause != '' THEN 1 ELSE 0 END) as cause,
            SUM(CASE WHEN doc_value IS NOT NULL AND doc_value != '' THEN 1 ELSE 0 END) as docval,
            COUNT(*) as total
        FROM onsite_problem_details WHERE raw_json IS NOT NULL
    """)
    row = vc.fetchone()
    print(f"\n[验证] 解析后: vehicle={row[0]}, desc={row[1]}, version={row[2]}, module={row[3]}, cause={row[4]}, docval={row[5]} / total={row[5]}")
    vc.close()
    verify_conn.close()


if __name__ == "__main__":
    main()
