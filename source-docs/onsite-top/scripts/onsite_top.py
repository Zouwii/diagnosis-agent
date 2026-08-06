#!/usr/bin/env python3
"""onsite-top 数据整理工具：生成现场问题报告，或迁移 raw_json 字段。"""

import argparse
import json, os, re, sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

DEFAULT_EXECUTORS = {
    "onsite": {"潘峥": "61dce1a3bd146ff52e5624d7", "panzheng": "61dce1a3bd146ff52e5624d7"},
    "benti": {"潘峥": "2108411066921750", "panzheng": "2108411066921750"},
}
DB_NAMES = {"benti": "benti_management", "onsite": "onsite_problem"}
TABLES = {
    # CLI 名称                 数据库来源       实际表名                 时间字段
    "program_issue_details": ("benti", "program_issue_detail", "created_at_ding"),
    "onsite_problem": ("onsite", "onsite_problem_details", "ding_created"),
}
QUARTERS = {"Q1": ("01-01", "04-01"), "Q2": ("04-01", "07-01"),
            "Q3": ("07-01", "10-01"), "Q4": ("10-01", "01-01")}

def db_config(source):
    """按来源读取连接配置；密码优先从环境变量读取。"""
    prefix = source.upper()
    return {
        "host": os.getenv(f"{prefix}_DB_HOST", "127.0.0.1"),
        "port": int(os.getenv(f"{prefix}_DB_PORT", "3307")),
        "user": os.getenv(f"{prefix}_DB_USER", "root"),
        "password": os.getenv(f"{prefix}_DB_PASSWORD", ""),
        "database": os.getenv(f"{prefix}_DB_NAME", DB_NAMES[source]),
        "charset": "utf8mb4",
    }

def get_db_connection(source):
    try:
        import pymysql
        return pymysql.connect(**db_config(source))
    except Exception as e:
        raise RuntimeError(f"{source} 数据库连接失败: {e}") from e

def quarter_dates(year, quarter):
    if quarter not in QUARTERS:
        raise ValueError(f"不支持的季度: {quarter}，可选 Q1/Q2/Q3/Q4")
    start, end = QUARTERS[quarter]
    start_year = year
    end_year = year + (1 if quarter == "Q4" else 0)
    return f"{start_year}-{start}", f"{end_year}-{end}"

def fetch_from_db(conn, table_key, s, e, executor_id):
    """按表结构查询指定人员和季度；两个表缺失的字段统一补 NULL。"""
    _source, table_name, date_column = TABLES[table_key]
    c = conn.cursor()
    c.execute(f"SHOW COLUMNS FROM `{table_name}`")
    columns = {row[0] for row in c.fetchall()}
    def field(name, alias=None):
        alias = alias or name
        return f"`{name}` AS `{alias}`" if name in columns else f"NULL AS `{alias}`"
    raw_field = "raw_json" if "raw_json" in columns else "custom_fields_json"
    selects = [field(name) for name in (
        "task_id", "content", "problem_description", "problem_category", "problem_module",
        "root_cause", "solution", "vehicle_model", "occurrence_frequency", "software_version",
        "is_done")]
    selects += [field(date_column, "due_date"), field(raw_field, "raw_json")]
    where = f"WHERE `{date_column}` >= %s AND `{date_column}` < %s"
    params = [s, e]
    if "executor_id" in columns:
        where += " AND `executor_id` = %s"; params.append(executor_id)
    c.execute(f"SELECT {', '.join(selects)} FROM `{table_name}` {where} ORDER BY `{date_column}`", params)
    rows = c.fetchall(); c.close()
    result = []
    for i, r in enumerate(rows, 1):
        raw = r[12]
        extracted = parse_raw_json(raw) if raw else {}
        result.append({
            "num": i,
            "date": str(r[11])[:10] if r[11] else "",
            "description": (r[2] or r[1] or extracted.get("problem_description") or "").strip(),
            "vehicle_model": r[7] or "",
            "status": "done" if r[10] else "pending",
            "root_cause_text": r[5] or "",
            "solution_text": r[6] or "",
            "problem_category": r[3] or extracted.get("problem_category", ""),
            "problem_module": r[4] or extracted.get("problem_module", ""),
            "occurrence_frequency": r[8] or "",
            "software_version": r[9] or extracted.get("software_version", ""),
        })
    return result

# ═══════════════════════════════════════════════════
# 分类引擎 — 多轮匹配策略
# ═══════════════════════════════════════════════════

# ── 问题类型分类（优先级：建图 > 定位 > 非本体导航 > 导航）──
_PROBLEM_TYPE_RULES = [
    # type, keywords
    ("TB单异常/资料不全", ["资料不全","重复提单","信息不全","无法定位问题"]),
    ("建图", ["建图","续建","地图创建","扫图","地图文件","创建二维码区域",
              "地图热更新","地图对齐","打开地图.*报错","地图保存","保存地图",
              "地图无法打开","地图未同步","地图内容异常","地图区域.*扫","子图.*报错",
              "地图文件损坏","不能建立正常的地图","地图.*橡皮擦","地图.*错乱",
              "新建地图","生成.*地图","地图.*推送.*直线","新增.*子图.*报错",
              "地图.*歪斜","续建.*卡死","续建.*内存","续建.*缩水","续建.*断开"]),
    ("定位", ["定位","位姿","丢定位","定位漂移","定位偏移","定位跳动",
              "定位异常","定位跑偏","定位飘移","无法手动定位",
              "cartographer","定位卡死","定位源未开启","无法定位",
              "反光板误识别","反光板定位","点云对不上","点云跳",
              "激光有数据无点云","激光标定","标定异常","内外参",
              "定位.*初始化","等待定位","定位.*不变化",
              "激光.*断联","激光.*数据不变化","激光.*无点",
              "纯反光板","定位.*丢","定位.*切换","跳*丢定位"]),
    ("非本体导航", ["停障","io停障","安全激光停障","安全激光全失效",
              "web-service异常","web-service报错","webservice报错",
              "web_service报错","web-servce","web-service.*就绪",
              "行为树异常","行为树报错","行为树不结束",
              "actionlib","速度跟踪","速度跟随","速度异常慢",
              "磁盘爆满","载货开关未触发","plc没有吸合",
              "驱动器异常","电机速度","伺服报错","伺服.*报错",
              "载货开关","node.state","节点重启",
              "降叉.*距离太远","撞到货架.*降叉","叉齿.*下降卡住",
              "安全激光","轨迹停障","软急停",
              "光电器件","挡板触发","放料.*叉齿",
              "web-service.*报错","webservice.*报错",
              "node.*崩溃.*无dump","监测到系统中节点崩溃",
              "检查载具状态安全检测异常",
              # 伺服/载具/动作
              "载具.*参数获取失败","通用载具位置环","举升.*报错",
              "载具.*任务执行失败","手动升降.*顿挫",
              "伺服.*运行中","伺服.*异常","伺服充电",
              "伺服进叉取偏","栈板伺服",
              # 门控/电梯/龙门
              "电梯卡在","电梯不关门","请求开门","门未自动关闭",
              "门.*自动.*关","龙门.*到位后直接",
              "提升机口","提升机",
              # 电气/硬件/配置
              "电气原理图","接线","com口不通","工控机断电",
              "硬盘占用","车体外部.*镂空","定制填补",
              "人形机器人.*打包",
              # 对接类型/需求变更
              "对接类型.*需要改成","需要定制",
              # 切换地图指令
              "执行完切换地图的指令",
              # 重复前进后退（控制震荡→非本体/电机驱动）
              "重复前进.*后退","前进.*后退.*重复",
              # 未到点位就执行动作
              "未到点位.*就执行","未到点位上.*执行",
    ]),
]
_NAV_ROOT_CAUSE_RULES = [
    # (category, module, sub_reason), keywords
    # ── 软件bug ──
    (("软件bug","nav-manager","程序崩溃"), ["nav-manager.*节点崩溃","nav-manager.*崩溃"]),
    (("软件bug","nav-manager","优化逻辑"), [
        "到点精度异常","到点报到点精度异常","到点精度",
        "到点报错精度","导航到点精度","到点报错精度异常",
        "报导航精度异常","精度异常.*到库位","精度异常.*伺",
        "到点精度异常.*定位跳","定位跳动导致到点精度",
        "禁止旋转.*点位旋转","禁止旋转点位","在禁止旋转",
        "非法旋转.*报错","异常旋转.*报错","非曲线道路.*到点精度",
        "报错.*非法旋转","原地旋转上道",
        "甩头","原地摆头",
        "旋转报错","原地旋转.*报错","原地左右旋转上道",
        "到点后.*任务不停止","执行到点后.*不停止",
        "上道.*逻辑出错","上道.*错误","旋转上道",
        "全向车上道.*错","禁止旋转点.*旋转",
    ]),
    (("软件bug","nav-base","优化逻辑"), [
        "载具状态安全检测异常","货架角度不满足路线要求",
    ]),
    (("软件bug","nav-net","程序崩溃"), [
        "nav-net.*node.state","nav-net.*节点","nav-net.*崩溃",
        "node.*崩溃","系统中节点崩溃",
    ]),
    (("软件bug","nav-net","优化逻辑"), [
        "other_reason","其他错误",
    ]),
    (("软件bug","nav-task","优化逻辑"), [
        "任务信息格式非法","下发任务信息非法","下发任务信息异常",
        "下发任务离当前位置过远","任务下发异常",
        "任务被抢占","导航规划失败",
        "无法搜索出有效路径","路径不可达",
        "没有规划路线","下发信息.*异常",
        "调度下发.*异常","抢占路径.*没有重合",
        "返航点太远","下发.*格式转换失败",
        "task.unexpectly.canceled","underline task",
    ]),
    (("软件bug","nav-task","曾经修复过的问题"), [
        "距离上道返航点太远",
    ]),
    (("软件bug","jz-pnc","优化逻辑"), [
        "偏移路线","冲出路线","冲出路","走歪","走偏",
        "偏离路线","偏离线路","曲线没有按照曲线走",
        "没有按照曲线","偏移.*冲出","偏移.*差点撞",
        "曲线.*直线过去","导航走歪","导航.*偏移",
        "拐弯.*无法正常拐弯","无法正常拐弯","报左转弯",
        "两点之间来回跑","来回跑无法正常",
        "导航运行缓慢","速度异常慢.*导航",
        "原地掉头偏移太大","运行缓慢",
        "颠一下","卡死无法遥控",
        "卡死.*报错.*原地旋转",
        "起点左右摇摆","导航时扭动",
    ]),
    (("软件bug","motion-common","优化逻辑"), [
        "震荡","振荡","控制命令激荡","到点晃动",
    ]),
    # ── 软件bug - nav-manager (导航卡死/不动) ──
    (("软件bug","nav-manager","优化逻辑（导航不动）"), [
        "导航移动中实际不动","显示移动中实际.*不动",
        "状态正常报导航移动中","显示后退中.*原地不动",
        "显示准备移动.*不动","报后退中.*不动",
        "在原地不动.*语音","移动中实际车体未动",
        "导航到点不动","后退中.*无法移动",
        "报后退中","后退中.*实际原地不动",
        "无法正常离开休息点.*报后退中",
        "导航卡住不动.*遥控可以移动",
        "显示任务实行中.*没有进行导航移动",
        "接到调度任务.*没有.*移动",
        "下发导航指令车辆不运动",
        "导航过程中停止不动",
    ]),
    # ── 软件bug - nav-manager (取货/离开/库位异常) ──
    (("软件bug","nav-manager","优化逻辑（库位进出）"), [
        "取货退出库位.*报错","退出时开始原地.*无法直行",
        "库位点出发上道.*原地旋转","伺服任务结束.*退出库位.*报",
        "放完货车辆不动.*切单机",
    ]),
    # ── 软件bug - nav-manager (上道/旋转异常) ──
    (("软件bug","nav-manager","优化逻辑（上道/旋转）"), [
        "执行调度任务.*原地旋转$","调度.*不受道路属性限制.*旋转",
        "急停复位后.*上道.*旋转","拍急停复位.*上道.*旋转",
        "到点执行动作前.*发生异常旋转",
        "禁止货架旋转点位.*旋转出库位",
    ]),
    # ── 软件bug - nav-manager (到点问题) ──
    (("软件bug","nav-manager","优化逻辑（到点）"), [
        "到点偏差","到点.*现场观察.*偏差",
        "到点异常.*撞机",
    ]),
    # ── 软件bug - jz-pnc (motion异常) ──
    (("软件bug","jz-pnc","优化逻辑（motion异常）"), [
        "前进后退异常跑偏",
        "导航走完轨迹后需要停顿",
        "导航过程中无故停车",
        "行走到曲线时报错",
        "原地旋转过程中卡顿",
        "多车.*行驶过程.*明显停顿",
        "行驶途中卡死无法遥控",
        "执行任务途中卡死在前进中",
        "运行到一半卡死未报错",
        "转弯后在点位报错",
        "换向点没规划路线正确路线",
        "导航时显示移动中.*跑出图外",
        "行驶途中.*故障不动.*跑出图外",
    ]),
    # ── 软件bug - jz-pnc (行驶偏航) ──
    (("软件bug","jz-pnc","优化逻辑（行驶偏航）"), [
        "导航到.*二维码前歪了","差点撞隔板",
    ]),
    # ── 外部因素 - 感知/伺服/硬件 ──
    (("外部因素","部署实施异常","感知/伺服配置"), [
        "failed_get_perception","获取不到感知数据","感知标志物",
        "离散二维码伺服错误","获取导航距离超时",
        "检测到传感器数据异常",
        "切换地图后动作异常",
    ]),
    (("外部因素","硬件异常","激光/打滑"), [
        "激光断连","自恢复异常.*激光",
        "打滑以后.*激光无数据","严重打滑.*激光",
    ]),
    # ── 其他模块 ──
    (("其他模块","行为树异常",""), [
        "行为树任务","行为树异常","行为树报错","行为树一直不结束",
    ]),
    (("其他模块","web-service异常",""), [
        "web-service.*报错","web_service.*报错","webservice.*报错",
        "等待web-servce","webservice/others",
    ]),
    (("其他模块","调度",""), [
        "交管.*导航","交管.*无法移","交管.*不动",
        "交管.*锁死","区域锁死","调导航.*交管",
        "调度.*不放","调度.*信号","调度.*无载货",
        "调度.*导航.*不结束",
        "发生交管$","报交管$","报交管，",
        "接取新任务.*发生交管","取货离开库位.*交管",
        "单机.*下发.*不运动",
        "交管.*原地交管",
        "到点交管","导航到点交管",
        "交管锁死","交管异常","交管管制","交管中",
        "交通管制","交管模块","全场交管",
        "单车交管","相互交管","异常交管",
        "交管.*附近无","交管.*无视",
        "直交管不好","交管.*管理",
        "不申请交管.*道路","交管.*锁死",
        "交点.*卡死","申请交管",
        "交管.*没收到回复","一直报交通管制",
        "一直处于交管","交管.*被.*锁",
        "单线交管","交管.*卡死","锁死.*交管",
        "取货出库位.*交管.*锁","出库位.*交管",
    ]),
    (("其他模块","安全模块","停障触发"), [
        "停障.*导航","停障.*恢复后.*旋转","停障.*报错",
        "触发停障.*报错","软急停",
    ]),
    (("其他模块","电机驱动","速度跟踪偏差"), [
        "电机速度","速度跟踪","速度跟随","速度.*异常",
    ]),
    # ── 外部因素 ──
    (("外部因素","部署实施异常","二维码/相机问题"), [
        "二维码检测超时","二维码定位超时","二维码定位开启超时",
        "未检测到二维码","未识别到二维码","二维码伺服失败",
        "视觉伺服失败","起点未检测到二维码",
        "未找到二维码","连续运行.*未识别到二维码",
        "二维码.*检测超时","二维码.*相机状态",
        "二维码.*超时",
    ]),
    (("外部因素","现场误报","版本升级引入"), [
        "升级版本.*报错","更新.*版本.*报错","升级后.*报错",
        "更新iobox.*乱转","更新jz-system.*爆满",
        "更新nav.*爆满",
    ]),
    (("外部因素","部署实施异常","地图/轨迹配置"), [
        "轨迹文件","未搜到轨迹","线路属性.*自主上道",
        "热切换.*线路","伺服终点.*误差","点位方向.*对齐",
        "货架方向.*满足点位","轨迹点位",
        "新老调度使用",
    ]),
    (("外部因素","出厂设置异常","导航参数"), [
        "导航运行参数异常",
    ]),
    (("外部因素","部署实施异常","网络问题"), [
        "网络.*ping","网络.*999",
    ]),
    (("外部因素","新场景需求",""), [
        "新场景需求","适配现场",
    ]),
    (("外部因素","部署实施异常","车体超出可行域"), [
        "车体超出可行域","调度空间管理.*footprint",
    ]),
]

# ── 定位原因规则 ──
_LOC_CAUSE_RULES = [
    (("软件bug","cartographer-iplus-mod","程序崩溃"), ["cartographer-iplus-mod.*unusual_msg","cartographer.*故障"]),
    (("软件bug","map-manager","其他"), ["map-manager","打开地图.*无法手动定位"]),
    (("软件bug","定位算法","定位漂移"), [
        "定位.*偏移","定位漂移","定位飘移","定位跑偏",
        "定位开始发生偏移","定位跳动","定位.*跳",
        "定位未丢跑偏","导航严重偏移路线.*没丢定位",
        "走直线丢定位.*左右摆动",
    ]),
    (("其他模块","传感器异常","激光数据不变化"), ["激光数据不变化","激光.*无点云","激光数据异常"]),
    (("其他模块","传感器异常","激光强度异常"), ["激光强度数据","激光强度异常"]),
    (("其他模块","传感器异常","时间不一致"), ["传感器时间.*ros::now","传感器时间和ros"]),
    (("其他模块","传感器异常","点云异常"), [
        "点云没有了","点云对不上","点云跳",
    ]),
    (("外部因素","出厂设置异常","激光内外参"), ["激光内外参标定","标定参数异常"]),
    (("外部因素","出厂设置异常","前后激光外参"), ["前后激光外参不重合","外参不重合"]),
    (("外部因素","部署实施异常","缺少定位源"), ["参照物过少","缺少定位源","环境特征不明显"]),
    (("外部因素","部署实施异常","定位忽略区域"), ["定位忽略区域.*框选","忽略区域"]),
    (("外部因素","部署实施异常","地图扫太厚"), ["地图区域扫太厚"]),
    (("外部因素","部署实施异常","反光板异常"), ["反光板.*异常识别","高反物体","反光板识别"]),
    (("外部因素","部署实施异常","二维码定位源未开启"), [
        "二维码定位开启超时","二维码定位超时","目标定位源.*有效开启",
        "二维码.*定位超时",
    ]),
    (("外部因素","部署实施异常","点位姿变更"), [
        "二维码切换点位姿变了","位姿变了","位姿偏移",
    ]),
    (("外部因素","适配现场","优化参数"), ["优化参数","参数调整"]),
    (("外部因素","现场作业环境","打滑"), ["打滑","地面环境","轮子"]),
    (("外部因素","现场作业环境","定位初始化异常"), [
        "开机后自动定位异常","等待定位中",
        "定位.*初始化",
    ]),
    (("外部因素","现场误报","版本升级引入"), ["升级版本","新版.*定位","更新.*定位"]),
    (("外部因素","硬件异常","激光断联"), [
        "激光断联.*自恢复","激光断联异常",
    ]),
    (("未知原因","","丢定位-原因不明"), [
        "丢定位","定位.*丢","丢定位","定位.*异常",
        "纯反光板定位","b+.*丢定位",
        "定位.*不变化",
    ]),
]

# ── 建图原因规则 ──
_MAP_CAUSE_RULES = [
    (("外部因素","部署实施异常","地图文件损坏"), ["地图.*文件损坏","地图.*损坏","损坏.*地图"]),
    (("外部因素","部署实施异常","误扫2x2码"), ["创建子图.*误扫","误扫了2x2","误扫.*码"]),
    (("外部因素","部署实施异常","地图内容异常"), ["地图.*内容异常","地图文件内容异常","地图.*错乱","地图.*不显示","地图.*歪斜"]),
    (("外部因素","部署实施异常","续建操作异常"), ["续建.*操作异常","续建操作","续建.*卡死","保存失败","续建.*缩水","续建.*断开"]),
    (("外部因素","部署实施异常","续建内存过大"), ["续建.*内存","内存.*过大","内存占用"]),
    (("外部因素","部署实施异常","地图对齐异常"), ["地图对齐.*bug","对齐之后.*没有","地图.*对齐.*不对"]),
    (("外部因素","部署实施异常","地图推送异常"), ["地图.*推送.*直线","推送.*显示","热更新.*数量不对"]),
    (("外部因素","部署实施异常","橡皮擦后无法保存"), ["橡皮擦.*无法保存","橡皮擦.*保存"]),
    (("外部因素","部署实施异常","创建二维码区域异常"), ["创建二维码区域.*错乱","二维码区域.*保存后"]),
    (("外部因素","现场误报","版本升级引入"), ["升级.*打开地图","更新版本.*打开","升级包.*地图"]),
    (("外部因素","部署实施异常","切换地图异常"), ["切换地图.*bug","切换地图.*异常"]),
    (("未知原因","","新建地图卡死"), ["建图卡死","无法打开","不能建立","不能打开"]),
]

# ── 提示信息规则 ──
_PROMPT_RULES = [
    ("导航/nav-manager/到点精度异常", ["到点精度异常","精度异常"]),
    ("导航/nav-manager/导航过程异常偏离路线超过阈值", ["偏离路线超过","偏离线路超过"]),
    ("本体导航/定位/检测到传感器数据异常", ["传感器数据异常"]),
    ("无提示/移动导航中/后退中", ["后退中"]),
    ("无提示/移动导航中/前进中", ["前进中","移动中","准备移动"]),
    ("导航/nav-manager/导航过程异常", ["导航过程异常"]),
    ("本体导航/建图/续建异常", ["续建.*异常","续建.*失败"]),
    ("本体导航/定位/定位异常", ["定位异常","定位失败"]),
    ("非本体导航/web-service异常", ["web-service","webservice"]),
    ("非本体导航/行为树异常", ["行为树"]),
    ("导航/nav-net/其他错误", ["其他错误","其他异常"]),
    ("导航/nav-manager/任务下发异常", ["任务.*下发","下发.*非法"]),
    ("导航/nav-manager/非法旋转", ["非法旋转"]),
    ("导航/jz-pnc/路线偏移", ["偏移","偏离","冲出","走歪","走偏"]),
    ("无提示/其他", []),  # default
]


def _match(text: str, keywords: list) -> bool:
    """检查 text 是否匹配任一关键词"""
    return any(re.search(kw, text) for kw in keywords)


def classify_problem_type(desc: str) -> str:
    for ptype, keywords in _PROBLEM_TYPE_RULES:
        if _match(desc, keywords):
            return ptype
    return "导航"


def classify_nav_root_cause(desc: str, problem_category: str = "") -> dict:
    for (cat, mod, sub), keywords in _NAV_ROOT_CAUSE_RULES:
        if _match(desc, keywords):
            return {"category": cat, "module": mod, "sub_reason": sub}

    # 关键词未命中，用 problem_category 兜底
    pc = problem_category
    if pc:
        if pc.startswith("云端研发"):
            return {"category": "其他模块", "module": "调度", "sub_reason": ""}
        if pc.startswith("基线开发") and ("任务引擎" in pc):
            return {"category": "其他模块", "module": "任务引擎", "sub_reason": ""}
        if pc.startswith("基线开发"):
            return {"category": "软件bug", "module": "基线软件", "sub_reason": "优化逻辑"}
        if pc.startswith("本体对接"):
            return {"category": "其他模块", "module": "本体对接", "sub_reason": ""}
        if pc.startswith("外部因素"):
            return {"category": "外部因素", "module": "外部因素", "sub_reason": ""}
        if pc.startswith("工程"):
            return {"category": "外部因素", "module": "部署实施异常", "sub_reason": ""}
        if pc.startswith("电气电子"):
            return {"category": "外部因素", "module": "硬件异常", "sub_reason": ""}
        if pc.startswith("云端业务"):
            return {"category": "其他模块", "module": "调度", "sub_reason": ""}
        if pc.startswith("生产"):
            return {"category": "外部因素", "module": "出厂设置异常", "sub_reason": ""}

    return {"category": "未知原因", "module": "", "sub_reason": ""}


def classify_loc_cause(desc: str) -> dict:
    for (cat, mod, sub), keywords in _LOC_CAUSE_RULES:
        if _match(desc, keywords):
            return {"category": cat, "module": mod, "sub_reason": sub}
    return {"category": "未知原因", "module": "", "sub_reason": ""}


def classify_map_cause(desc: str) -> dict:
    for (cat, mod, sub), keywords in _MAP_CAUSE_RULES:
        if _match(desc, keywords):
            return {"category": cat, "module": mod, "sub_reason": sub}
    return {"category": "未知原因", "module": "", "sub_reason": ""}


def classify_prompt_info(desc: str) -> str:
    for prompt, keywords in _PROMPT_RULES:
        if not keywords:
            return prompt
        if _match(desc, keywords):
            return prompt
    return "无提示/其他"


# ═══════════════════════════════════════════════════
# Markdown 解析
# ═══════════════════════════════════════════════════

def parse_panzheng_markdown(filepath: str) -> list:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    records = []
    for m in re.finditer(r'\|\s*(\d+)\s*\|\s*(2026-0[4-6]-\d{2})\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(✅|⏳)', content):
        records.append({
            "num": int(m.group(1)), "date": m.group(2),
            "description": m.group(3).strip(),
            "vehicle_model": m.group(4).strip(),
            "status": "done" if m.group(5) == "✅" else "pending",
        })
    # 去重（前80字符+日期）
    seen = set()
    unique = []
    for r in records:
        key = (r["date"], r["description"][:80])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


# ═══════════════════════════════════════════════════
# 统计引擎
# ═══════════════════════════════════════════════════

def classify_all(records: list) -> dict:
    total = len(records)
    type_counter = Counter()
    # 导航原因
    nav_cause_counter = Counter()
    nav_cause_detail = defaultdict(lambda: defaultdict(int))
    nav_module_sub = defaultdict(lambda: defaultdict(int))
    # 定位原因
    loc_cause_counter = Counter()
    loc_cause_detail = defaultdict(lambda: defaultdict(int))
    # 建图原因
    map_cause_counter = Counter()
    map_cause_detail = defaultdict(lambda: defaultdict(int))
    # 提示信息
    prompt_counter = Counter()

    categorized = {"导航": [], "定位": [], "建图": [], "非本体导航": [], "TB单异常/资料不全": []}

    for r in records:
        desc = r["description"]
        ptype = classify_problem_type(desc)
        r["problem_type"] = ptype
        type_counter[ptype] += 1
        prompt_counter[classify_prompt_info(desc)] += 1

        if ptype == "导航":
            cause = classify_nav_root_cause(desc, r.get("problem_category",""))
            r["root_cause"] = cause
            nav_cause_counter[cause["category"]] += 1
            nav_cause_detail[cause["category"]][cause["module"]] += 1
            if cause["sub_reason"]:
                nav_module_sub[cause["module"]][cause["sub_reason"]] += 1
            categorized["导航"].append(r)
        elif ptype == "定位":
            cause = classify_loc_cause(desc)
            r["root_cause"] = cause
            loc_cause_counter[cause["category"]] += 1
            loc_cause_detail[cause["category"]][cause["module"]] += 1
            categorized["定位"].append(r)
        elif ptype == "建图":
            cause = classify_map_cause(desc)
            r["root_cause"] = cause
            map_cause_counter[cause["category"]] += 1
            map_cause_detail[cause["category"]][cause["module"]] += 1
            categorized["建图"].append(r)
        elif ptype == "非本体导航":
            categorized["非本体导航"].append(r)
        else:
            categorized["TB单异常/资料不全"].append(r)

    return {
        "total": total, "type_counter": type_counter, "categorized": categorized,
        "nav_cause_counter": nav_cause_counter, "nav_cause_detail": nav_cause_detail,
        "nav_module_sub": nav_module_sub,
        "loc_cause_counter": loc_cause_counter, "loc_cause_detail": loc_cause_detail,
        "map_cause_counter": map_cause_counter, "map_cause_detail": map_cause_detail,
        "prompt_counter": prompt_counter,
    }


# ═══════════════════════════════════════════════════
# 报告生成
# ═══════════════════════════════════════════════════

def fmtpct(cnt, total):
    return f"{cnt/total*100:.2f}%" if total else "0.00%"

def generate_legacy_report(stats: dict, source: str = "") -> str:
    total = stats["total"]
    tc = stats["type_counter"]
    nav_total = tc.get("导航", 0)
    loc_total = tc.get("定位", 0)
    map_total = tc.get("建图", 0)
    non_nav_total = tc.get("非本体导航", 0)
    tb_bad = tc.get("TB单异常/资料不全", 0)

    L = []; A = L.append
    A("# 2026年Q2导航组问题复盘 — 数据库统计版\n")
    A(f"> 数据来源：{source}")
    A(f"> 统计时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    A(f"> 总计打标单数：{total}单\n")

    # ═══ 问题类型统计 ═══
    A("## 问题类型统计\n")
    A("| 问题类型 | 单数 | 占比 |")
    A("|---|---|---|")
    A(f"| 本体导航/导航 | {nav_total} | {fmtpct(nav_total,total)} |")
    A(f"| 本体导航/定位 | {loc_total} | {fmtpct(loc_total,total)} |")
    A(f"| 本体导航/建图 | {map_total} | {fmtpct(map_total,total)} |")
    A(f"| 本体导航/非本体导航 | {non_nav_total} | {fmtpct(non_nav_total,total)} |")
    A(f"| TB单异常/资料不全 | {tb_bad} | {fmtpct(tb_bad,total)} |")
    A(f"| 合计 | {total} | 100% |\n")

    total_nav_problem = nav_total + loc_total + map_total
    A("## 问题原因统计\n")
    A(f"本体导航问题总计{total_nav_problem}单。\n")

    # ═══ 导航原因 ═══
    A("### 本体导航/导航原因分类统计\n")
    nc = stats["nav_cause_counter"]
    A("| 原因类型 | 单数 | 占比 |")
    A("|---|---|---|")
    for k in ["软件bug","其他模块","外部因素","未知原因"]:
        A(f"| {k} | {nc.get(k,0)} | {fmtpct(nc.get(k,0),nav_total)} |")
    A(f"| 合计 | {nav_total} | 100% |\n")

    if nav_total > 0:
        A(f"导航原因中{'软件bug' if nc.get('软件bug',0)>=nc.get('其他模块',0) else '其他模块'}占比最高。\n")

    # 软件bug详细
    A("*   软件bug数据统计\n")
    A("| 问题原因（一级） | 问题原因（二级） | 单数 | 占比（占导航问题原因） |")
    A("|---|---|---|---|")
    msub = stats["nav_module_sub"]
    for mod in sorted(msub.keys()):
        for sub in sorted(msub[mod], key=lambda x: -msub[mod][x]):
            A(f"| {mod} | {sub} | {msub[mod][sub]} | {fmtpct(msub[mod][sub],nav_total)} |")
    A("")

    # 其他模块
    A("*   其他模块数据统计\n")
    A("| 问题原因（一级） | 问题原因（二级） | 单数 | 占比（占导航问题原因） |")
    A("|---|---|---|---|")
    od = stats["nav_cause_detail"].get("其他模块", {})
    for mod in sorted(od, key=lambda x: -od[x]):
        A(f"| {mod} | / | {od[mod]} | {fmtpct(od[mod],nav_total)} |")
    if not od: A("| （无） | / | 0 | 0.00% |")
    A("")

    # 外部因素
    A("*   外部因素统计\n")
    A("| 问题原因（一级） | 问题原因（二级） | 单数 | 占比（占导航问题原因） |")
    A("|---|---|---|---|")
    ed = stats["nav_cause_detail"].get("外部因素", {})
    for mod in sorted(ed, key=lambda x: -ed[x]):
        A(f"| {mod} | / | {ed[mod]} | {fmtpct(ed[mod],nav_total)} |")
    if not ed: A("| （无） | / | 0 | 0.00% |")
    A("")

    # ═══ 定位原因 ═══
    A("### 本体导航/定位原因分类统计\n")
    lc = stats["loc_cause_counter"]
    A("| 原因类型 | 单数 | 占比 |")
    A("|---|---|---|")
    for k in ["软件bug","其他模块","外部因素","未知原因"]:
        A(f"| {k} | {lc.get(k,0)} | {fmtpct(lc.get(k,0),loc_total)} |")
    A(f"| 合计 | {loc_total} | 100% |\n")

    ld = stats["loc_cause_detail"]
    if ld:
        A("*   数据统计\n")
        A("| 问题原因（一级） | 问题原因（二级） | 单数 | 占比（占定位问题原因） |")
        A("|---|---|---|---|")
        for cat in ["软件bug","其他模块","外部因素"]:
            for mod in sorted(ld.get(cat,{}), key=lambda x: -ld[cat][x]):
                A(f"| {mod} | / | {ld[cat][mod]} | {fmtpct(ld[cat][mod],loc_total)} |")
        A("")

    # ═══ 建图原因 ═══
    A("### 本体导航/建图原因分类统计\n")
    mc = stats["map_cause_counter"]
    A("| 原因类型 | 单数 | 占比 |")
    A("|---|---|---|")
    for k in ["外部因素","未知原因"]:
        A(f"| {k} | {mc.get(k,0)} | {fmtpct(mc.get(k,0),map_total)} |")
    A(f"| 合计 | {map_total} | 100% |\n")

    md = stats["map_cause_detail"]
    if md:
        A("*   外部因素数据统计\n")
        A("| 问题原因（一级） | 问题原因（二级） | 单数 | 占比（占建图问题原因） |")
        A("|---|---|---|---|")
        for mod in sorted(md.get("外部因素",{}), key=lambda x: -md["外部因素"][x]):
            A(f"| {mod} | / | {md['外部因素'][mod]} | {fmtpct(md['外部因素'][mod],map_total)} |")
        A("")

    # ═══ 提示信息统计 ═══
    A("## 问题提示信息统计\n")
    prompt_data = stats["prompt_counter"]
    # 按单数排序
    A("| 提示信息类型 | 单数 | 占比 |")
    A("|---|---|---|")
    for k, v in prompt_data.most_common():
        A(f"| {k} | {v} | {fmtpct(v,total)} |")
    A("")

    # ═══ 详细列表 ═══
    A("## 详细分类明细\n")
    for cat_name in ["导航", "定位", "建图", "非本体导航"]:
        records = stats["categorized"].get(cat_name, [])
        if not records:
            continue
        A(f"### {cat_name}问题明细\n")
        A("| # | 日期 | 问题描述 | 原因分类 | 模块 |")
        A("|---|---|---|---|---|")
        for r in records:
            rc = r.get("root_cause", {})
            A(f"| {r['num']} | {r['date']} | {r['description'][:65]} | {rc.get('category','')} | {rc.get('module','')} |")
        A("")

    return "\n".join(L)

def markdown_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(str(v) for v in row) + " |" for row in rows)
    return "\n".join(lines)

def db_value(value):
    value = str(value or "").strip()
    return value or "未填写"

def onsite_navigation_version_table(records):
    """onsite 本体导航问题：版本为列，问题分类为行。"""
    subset = [
        r for r in records
        if db_value(r.get("problem_module")) == "本体导航"
    ]
    versions = []
    categories = []
    for record in subset:
        version = db_value(record.get("software_version"))
        if version not in versions:
            versions.append(version)
        category = db_value(record.get("problem_category"))
        if " / " in category:
            category = category.split(" / ")[-1]
        if category not in categories:
            categories.append(category)
    counts = Counter()
    for record in subset:
        version = db_value(record.get("software_version"))
        category = db_value(record.get("problem_category"))
        if " / " in category:
            category = category.split(" / ")[-1]
        counts[(category, version)] += 1
    rows = []
    for category in categories:
        values = [counts[(category, version)] for version in versions]
        rows.append((category, *values, sum(values)))
    rows.append(("合计", *(sum(counts[(category, version)] for category in categories) for version in versions), len(subset)))
    return markdown_table(["问题分类\\软件版本", *versions, "合计"], rows)

def generate_table_report(records, source_label, person, quarter):
    """只生成统计表；原因分布直接按查询返回的数据库字段聚合。"""
    total = len(records)
    typed = []
    type_counter = Counter()
    prompt_counter = Counter()
    for record in records:
        ptype = classify_problem_type(record.get("description", ""))
        record["report_problem_type"] = ptype
        typed.append(record)
        type_counter[ptype] += 1
        prompt_counter[classify_prompt_info(record.get("description", ""))] += 1

    type_order = ["导航", "定位", "建图", "非本体导航", "TB单异常/资料不全"]
    type_rows = [(f"本体导航/{name}" if name in {"导航", "定位", "建图", "非本体导航"} else name,
                  type_counter.get(name, 0), fmtpct(type_counter.get(name, 0), total))
                 for name in type_order]
    type_rows.append(("合计", total, "100.00%"))

    cause_sections = []
    for ptype in type_order:
        subset = [r for r in typed if r["report_problem_type"] == ptype]
        if not subset:
            continue
        pairs = Counter((db_value(r.get("problem_category")), db_value(r.get("problem_module"))) for r in subset)
        rows = [(category, module, count, fmtpct(count, len(subset)))
                for (category, module), count in pairs.most_common()]
        rows.append(("合计", "", len(subset), "100.00%"))
        cause_sections.append(f"### {('本体导航/' if ptype != 'TB单异常/资料不全' else '')}{ptype}原因分布\n\n" +
                             markdown_table(["数据库问题分类", "数据库问题模块", "单数", "占该类型比例"], rows))

    prompt_rows = [(key, value, fmtpct(value, total)) for key, value in prompt_counter.most_common()]
    solution_counts = Counter(db_value(r.get("solution_text")) for r in typed)
    solution_rows = [(key, value, fmtpct(value, total)) for key, value in solution_counts.most_common()]
    return {
        "title": f"{quarter}问题统计表 — {person}",
        "source_label": source_label,
        "total": total,
        "type_table": markdown_table(["问题类型", "单数", "占比"], type_rows),
        "cause_table": "\n\n".join(cause_sections),
        "prompt_table": markdown_table(["提示信息类型", "单数", "占比"], prompt_rows),
        "handling_table": markdown_table(["解决方案", "单数", "占比"], solution_rows),
        "stability_table": onsite_navigation_version_table(typed),
        "stability_title": "本体导航问题版本×模块",
        "conclusions": "",
    }


# ═══════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════

CF_MAP = {
    "659369d32ae435dd0b3c803e": "vehicle_model", "637c2e2ffbb56c003fdd74e9": "carrier_type",
    "62c51d82d7ab965fbdebd686": "occurrence_frequency", "6645bd4d22e1f70dadb953f6": "software_version",
    "624e4bf0972b3d03d3008c4c": "problem_description", "69241440caabefe748f91359": "investigation_conclusion",
    "692414313ffb7e9afc4e9f43": "doc_value", "6924139133e26574155ea68b": "investigation_doc",
    "625f75e9882430143f5bfd0a": "attachments", "691a95544ce9d3d5a5e541e1": "problem_category",
    "691a95f304c9e52bc9058bd6": "problem_module", "62651eadef4cf6063244aa5c": "guide_doc",
    "625f8339882430143f5c0b9a": "formal_version", "625f8317d472ef3d5c2f39a4": "root_cause",
    "625f8329b416f5118bb099b2": "solution", "68f637359ae2d0854e946cb3": "submitter",
}

def parse_raw_json(raw):
    if isinstance(raw, list):
        fields = raw
        task = {}
    else:
        fields = None
        task = None
        if isinstance(raw, dict):
            task = raw
        else:
            try:
                task = json.loads(raw)
            except (TypeError, ValueError):
                return {}
        if isinstance(task, list):
            fields = task
        else:
            fields = task.get("customfields") or task.get("customFields") or []
    result, attachments = {}, []
    for field in fields if isinstance(fields, list) else []:
        if not isinstance(field, dict):
            continue
        cfid = str(field.get("cfId") or field.get("customFieldId") or field.get("customfieldId") or "")
        col = CF_MAP.get(cfid)
        values = field.get("value") or []
        if not col or not isinstance(values, list):
            continue
        if col == "attachments":
            attachments.extend(str(v.get("title") or "").strip() for v in values if isinstance(v, dict) and v.get("title"))
        elif values and isinstance(values[0], dict) and values[0].get("title"):
            result[col] = str(values[0]["title"]).strip()
    if attachments:
        result["attachments"] = "; ".join(attachments)
    return result

def migrate_customfields(source, dry_run=False):
    conn = get_db_connection(source)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM onsite_problem_details WHERE raw_json IS NOT NULL AND raw_json != ''")
    total = cursor.fetchone()[0]
    print(f"[INFO] {source} 待处理: {total} 条")
    cursor.execute("SELECT id, task_id, raw_json FROM onsite_problem_details WHERE raw_json IS NOT NULL AND raw_json != ''")
    rows = cursor.fetchall()
    cols = list(dict.fromkeys(CF_MAP.values()))
    if dry_run:
        for rid, tid, raw in rows[:10]:
            print(f"  id={rid} task={str(tid)[:20]}: {parse_raw_json(raw)}")
        cursor.close(); conn.close(); return
    sql = f"UPDATE onsite_problem_details SET {', '.join(f'{c}=%s' for c in cols)} WHERE id=%s"
    updated = skipped = errors = 0
    for rid, _tid, raw in rows:
        values = parse_raw_json(raw)
        if not values:
            skipped += 1; continue
        try:
            cursor.execute(sql, [values.get(c) for c in cols] + [rid])
            updated += 1
        except Exception as exc:
            errors += 1
            if errors <= 5: print(f"[ERROR] id={rid}: {exc}", file=sys.stderr)
        if (updated + skipped) % 2000 == 0:
            conn.commit()
    conn.commit(); cursor.close(); conn.close()
    print(f"[DONE] 总={total}, 更新={updated}, 跳过={skipped}, 错误={errors}")

def render_template(report, template_path, variables):
    if not template_path:
        return report
    template = Path(template_path).read_text(encoding="utf-8")
    values = {"report_body": report, **variables}
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template

def make_parser():
    parser = argparse.ArgumentParser(description="onsite-top 报表和数据迁移工具")
    sub = parser.add_subparsers(dest="command", required=True)
    report = sub.add_parser("report", help="分类并生成 Markdown 报告")
    report.add_argument("--person", default="潘峥", help="人员名称或 executor_id（默认：潘峥）")
    report.add_argument("--quarter", default="Q2", type=str.upper, choices=QUARTERS, help="季度（默认：Q2）")
    report.add_argument("--year", default=2026, type=int)
    report.add_argument("--source", default="onsite", choices=["benti", "onsite", "md"], help="兼容参数；数据库报告会由 --table 决定来源")
    report.add_argument("--table", default="onsite_problem", choices=list(TABLES), help="数据库表：program_issue_details 或 onsite_problem")
    report.add_argument("--input-file", default="", help="source=md 时的输入 Markdown")
    report.add_argument("--output", default="", help="输出路径，默认：潘峥_Q2_<source>.md")
    report.add_argument("--template", default="", help="模板路径，默认使用 scripts/report.template.md；支持统计表和结论占位符")
    migrate = sub.add_parser("migrate", help="将 raw_json customField 迁移到结构化列")
    migrate.add_argument("--source", default="onsite", choices=["benti", "onsite"])
    migrate.add_argument("--dry-run", action="store_true", help="只预览前 10 条，不写数据库")
    return parser

def main():
    args = make_parser().parse_args()
    if args.command == "migrate":
        migrate_customfields(args.source, args.dry_run); return
    base = Path(__file__).parent
    start, end = quarter_dates(args.year, args.quarter)
    if args.source == "md":
        input_file = Path(args.input_file) if args.input_file else Path("/home/zhr/zhr_ws/src/潘峥_2026Q2_现场问题子单明细.md")
        if not input_file.exists():
            raise SystemExit(f"ERROR: Markdown 数据文件不存在: {input_file}")
        records = parse_panzheng_markdown(str(input_file))
        source_label = f"{args.person} {args.quarter} Markdown ({len(records)} 条)"
    else:
        table_source = TABLES[args.table][0]
        person_id = DEFAULT_EXECUTORS[table_source].get(args.person, args.person)
        conn = get_db_connection(table_source)
        try: records = fetch_from_db(conn, args.table, start, end, person_id)
        finally: conn.close()
        source_label = f"{args.table} ({table_source} DB，{len(records)} 条 {args.quarter})"
    if not records:
        raise SystemExit("ERROR: 数据为空")
    tables = generate_table_report(records, source_label, args.person, args.quarter)
    template = args.template or str(base / "report.template.md")
    template_values = dict(tables)
    template_values.update({"person": args.person, "quarter": args.quarter,
                            "source": args.table if args.source != "md" else args.source,
                            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M")})
    report = render_template("", template, template_values)
    suffix = args.table if args.source != "md" else "md"
    output = Path(args.output) if args.output else base / f"{args.person}_{args.quarter}_{suffix}.md"
    output.write_text(report, encoding="utf-8")
    print(f"[DONE] → {output} ({len(records)} 条)")


if __name__ == "__main__":
    main()
