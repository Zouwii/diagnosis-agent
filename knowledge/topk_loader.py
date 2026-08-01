"""导航 TopK 问题文档加载器

加载 B 类文档（现场问题排查文档），按错误码或问题类型做关键词匹配。
"""

from pathlib import Path

# B 类文档路径
TOPK_DOC_DIR = Path("/home/zhr/zhr_ws/src/ai/management-system/docs/error-code-system")

# 错误码 → 文档分类映射
ERROR_CODE_SECTIONS = {
    "614002": "地图异常",
    "614006": "地图异常",
    "614013": "地图异常",
    "614028": "二维码识别异常",
    "614047": "障碍物感知异常",
    "614048": "障碍物感知异常",
    "614049": "障碍物感知异常",
    "615001": "导航偏离",
    "615002": "导航偏离",
    "615005": "定位异常",
    "615006": "定位异常",
    "615007": "定位异常",
    "615008": "定位异常",
    "615011": "定位异常",
    "615012": "定位异常",
    "615013": "定位异常",
    "615014": "定位异常",
    "615015": "定位异常",
    "615016": "定位异常",
    "615017": "定位异常",
    "615018": "路径异常",
    "615019": "路径异常",
    "615020": "路径异常",
    "615021": "路径异常",
    "615022": "路径异常",
    "615023": "路径异常",
    "615024": "路径异常",
    "615025": "路径异常",
    "615026": "路径异常",
    "615027": "路径异常",
    "615028": "路径异常",
    "615029": "路径异常",
    "615030": "路径异常",
    "615031": "路径异常",
    "615033": "路径异常",
    "615034": "路径异常",
    "615035": "路径异常",
    "615036": "路径异常",
    "615037": "路径异常",
    "615038": "路径异常",
    "615039": "路径异常",
    "617001": "转盘/货架异常",
    "617002": "转盘/货架异常",
    "617003": "转盘/货架异常",
    "617004": "转盘/货架异常",
    "617005": "转盘/货架异常",
    "617006": "转盘/货架异常",
    "619002": "电机异常",
    "619003": "电机异常",
    "619004": "电机异常",
}

# 问题类型 → 排查方向关键词
PROBLEM_DIRECTIONS = {
    "navigation_rotate": ["旋转", "打滑", "侧移", "二维码", "定位丢失", "轮速差"],
    "navigation": ["导航", "路径", "move_base", "搜路"],
    "safety": ["安全", "急停", "避障", "限速"],
    "task_chain": ["任务", "下发", "行为树", "BT"],
    "device_sensor": ["激光", "相机", "传感器", "点云"],
}


def match_problem_doc(error_code: str, problem_type: str, symptom: str) -> dict:
    """根据错误码和问题类型匹配 B 类文档

    Returns:
        {
            "matched": bool,
            "section": str,         # 命中的章节名
            "error_code_desc": str,  # 错误码在文档中的描述
            "directions": list[str], # 排查方向
            "relevance": "high|medium|low|none",
        }
    """
    result = {
        "matched": False,
        "section": "",
        "error_code_desc": "",
        "directions": [],
        "relevance": "none",
    }

    # 1. 通过错误码查找章节
    section = ERROR_CODE_SECTIONS.get(error_code, "")
    if section:
        result["section"] = section
        result["relevance"] = "high"

        # 尝试从文档中提取描述
        doc_path = TOPK_DOC_DIR / "导航相关问题排查.md"
        if doc_path.exists():
            content = doc_path.read_text(encoding="utf-8")
            for line in content.split("\n"):
                if error_code in line and "|" in line:
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 2:
                        result["error_code_desc"] = parts[-1]
                        result["matched"] = True
                        break

    # 2. 通过问题类型补充排查方向
    if problem_type in PROBLEM_DIRECTIONS:
        result["directions"] = PROBLEM_DIRECTIONS[problem_type]
        if result["relevance"] == "none":
            result["relevance"] = "medium"
            result["matched"] = True

    # 3. 从 symptom 中提取额外关键词
    if symptom and result["relevance"] == "none":
        for ptype, keywords in PROBLEM_DIRECTIONS.items():
            for kw in keywords:
                if kw in symptom:
                    result["section"] = ptype
                    result["directions"] = keywords
                    result["relevance"] = "low"
                    result["matched"] = True
                    break
            if result["matched"]:
                break

    return result
