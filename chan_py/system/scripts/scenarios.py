#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""事件分支生成器：给「未来预定」事件按类型枚举可能结果。

规则依据：references/events.md 第 2 节 + schemas/scenario.schema.json
  数据发布 → 公布值 高于/等于/低于 前值（三支）
  政策会议 → 有实质决议 / 无决议 / 延期
每支必须给**可机械比对**的 observable_flag；affected_indicators 只列注册 id，不写方向。
前值不可得 → branch_ordering_applicable=false，写「排序不适用：前值不可得」，不猜。
"""
import argparse
import datetime as dt
import glob
import io
import json
import os
import hashlib
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "events")

AFFECT = [
    ("消费价格", ["MKT_CPI_YOY", "MKT_CGB10Y"]),
    ("生产者价格", ["MKT_CGB10Y"]),
    ("采购经理", ["MKT_CGB10Y"]),
    ("国民经济运行", ["MKT_CGB10Y", "MKT_RMB_LOAN_YOY"]),
    ("工业经济效益", ["MKT_RMB_LOAN_YOY"]),
    ("规模以上工业", ["MKT_RMB_LOAN_YOY"]),
    ("固定资产投资", ["MKT_RMB_LOAN_YOY"]),
    ("社会消费品零售", ["MKT_RMB_LOAN_YOY"]),
    ("房地产开发", ["MKT_RMB_LOAN_YOY"]),
    ("商品住宅销售", ["MKT_RMB_LOAN_YOY"]),
    ("能源生产", ["MKT_CGB10Y"]),
]

DATA_BRANCHES = [("公布值高于前值", "公布值 > 前值"),
                 ("公布值等于前值", "公布值 = 前值"),
                 ("公布值低于前值", "公布值 < 前值")]
MEETING_BRANCHES = [("有实质决议", "会议公告中出现决议条款"),
                    ("无实质决议", "会议公告中不含决议条款"),
                    ("延期", "主办方公告改期或取消")]


def affected_of(title):
    for key, ids in AFFECT:
        if key in title:
            return ids
    return ["MKT_CGB10Y"]



PREV_INDICATOR = [("消费价格", "MKT_CPI_YOY"), ("生产者价格", "MKT_PPI_YOY"),
                  ("采购经理", "MKT_PMI"), ("国民经济运行", "MKT_GDP_YOY"),
                  ("工业经济效益", "MKT_IP_YOY"), ("规模以上工业", "MKT_IP_YOY"),
                  ("社会消费品零售", "MKT_RETAIL_YOY"), ("固定资产投资", "MKT_FAI_YOY"),
                  ("商品住宅销售", "MKT_HOUSE_PRICE_YOY"), ("房地产开发", "MKT_REALESTATE"),
                  ("能源生产", "MKT_ELEC_YOY")]


def prev_of(title):
    """取该事件对应指标的上一期值（用于分支排序）。取不到返回 None。"""
    iid = next((v for k, v in PREV_INDICATOR if k in title), None)
    if not iid:
        return None
    fs = sorted(glob.glob(os.path.join(ROOT, "data", "facts", "*", iid + ".json")))
    if not fs:
        return None
    rec = json.load(io.open(fs[-1], encoding="utf-8"))
    return {"indicator_id": iid,
            "value": rec["current_state"]["数值"],
            "data_period": rec["data_period"],
            "source_link": "https://www.stats.gov.cn/sj/zxfb/",
            "observation_time": rec.get("observation_time", "")}


# 事件 → (本次发布的指标名, 该指标 id, 受同一读数影响的指标名)
PUBLISHES = [
    ("消费价格",     "CPI 同比",            "MKT_CPI_YOY",   "中国 10Y 国债收益率（C3）"),
    ("生产者价格",   "PPI 同比",            "MKT_PPI_YOY",   "中国 10Y 国债收益率（C3）"),
    ("采购经理",     "制造业 PMI",          "MKT_PMI",       "中国 10Y 国债收益率（C3）"),
    ("国民经济运行", "GDP 同比",            "MKT_GDP_YOY",   "中国 10Y 国债收益率（C3）与人民币贷款余额同比（C2）"),
    ("工业经济效益", "工业增加值同比",      "MKT_IP_YOY",    "人民币贷款余额同比（C2）"),
    ("规模以上工业", "工业增加值同比",      "MKT_IP_YOY",    "人民币贷款余额同比（C2）"),
    ("社会消费品零售", "社会消费品零售总额同比", "MKT_RETAIL_YOY", "人民币贷款余额同比（C2）"),
    ("固定资产投资", "固定资产投资同比",    "MKT_FAI_YOY",   "人民币贷款余额同比（C2）"),
    ("商品住宅销售", "70 城新建商品住宅价格同比", "MKT_HOUSE_PRICE_YOY", "人民币贷款余额同比（C2）"),
    ("房地产开发",   "房地产开发相关读数",  None,            "人民币贷款余额同比（C2）"),
    ("能源生产",     "全社会用电量同比",    "MKT_ELEC_YOY",  None),
]


def published_of(title):
    for key, name, iid, linked in PUBLISHES:
        if key in title:
            return name, iid, linked
    return "该事件对应读数", None, None


def _sp(name):
    """中文名与数字/符号之间补一个空格。"""
    return name + " " if name and not name.endswith(" ") else name


# 关联指标的方向：同向（读数上行 → 关联指标上行）/ 反向
LINK_DIRECTION = {
    "MKT_CPI_YOY": ("中国 10Y 国债收益率（C3）", +1),
    "MKT_PPI_YOY": ("中国 10Y 国债收益率（C3）", +1),
    "MKT_PMI": ("中国 10Y 国债收益率（C3）", +1),
    "MKT_GDP_YOY": ("中国 10Y 国债收益率（C3）", +1),
    "MKT_IP_YOY": ("人民币贷款余额同比（C2）", +1),
    "MKT_RETAIL_YOY": ("人民币贷款余额同比（C2）", +1),
    "MKT_FAI_YOY": ("人民币贷款余额同比（C2）", +1),
    "MKT_HOUSE_PRICE_YOY": ("人民币贷款余额同比（C2）", +1),
    "MKT_ELEC_YOY": (None, 0),
    None: ("人民币贷款余额同比（C2）", +1),
}


def impact_of(title, label, prev_value=None):
    """条件性影响：哪个指标、从多少到多少、关联指标按固定方向怎么动。

    方向按登记的传导规则固定写死（读数上行 → 长端收益率同向上移），措辞只用机械映射，不用“压力/阻力/支撑”。
    这是机制说明，不是对当日价格的判断。
    """
    name, iid, _linked = published_of(title)
    linked_name, sign = LINK_DIRECTION.get(iid, (None, 0))
    pv = prev_value

    def head(direction):
        if direction == 0:
            return (f"等于前值 → {_sp(name)}维持 {pv}" if pv else f"等于前值 → {_sp(name)}不变")
        if direction > 0:
            return (f"高于前值 → {_sp(name)}从 {pv} 上行到 >{pv}" if pv
                    else f"高于前值 → {_sp(name)}上行")
        return (f"低于前值 → {_sp(name)}从 {pv} 下行到 <{pv}" if pv
                else f"低于前值 → {_sp(name)}下行")

    def tail(direction):
        if linked_name is None or direction == 0:
            return "" if linked_name is None else f"；{linked_name}没有变化"
        move = direction * sign
        if "10Y" in (linked_name or ""):
            # 只用机械映射，不用"压力/阻力/支撑"这类可双向解读的词
            word = "同向上移" if move > 0 else "同向下移"
            return (f"；按登记的传导规则，{linked_name}与公布值同向 → 该分支对应收益率{word}"
                    f"（收益率上行 = 债券价格下行；不预测实际落点）")
        word = "上移" if move > 0 else "下移"
        return f"；{linked_name}参照值{word}"

    if "高于" in label:
        return head(+1) + tail(+1)
    if "等于" in label:
        return head(0) + tail(0)
    if "低于" in label:
        return head(-1) + tail(-1)
    if "实质决议" in label:
        return "公告出现决议条款 → 政策口径发生变化，C1（政策设定）当日即可读"
    if "无实质决议" in label:
        return "公告不含决议条款 → 政策口径不变，C1 维持原读数"
    return "会议延期 → 该事件对应读数顺延，当日无新信息"


def build_record(ev):
    title, date = ev["scope"], ev["event_date"]
    is_data = ev.get("event_type") == "数据发布"
    ids = affected_of(title)
    branches = DATA_BRANCHES if is_data else MEETING_BRANCHES
    eid = "SCN-" + date.replace("-", "") + "-" + hashlib.md5(f"{date}|{title}".encode("utf-8")).hexdigest()[:6]
    pv = prev_of(title) if is_data else None
    rec = {
        "event_id": eid,
        "event_summary": f"{date} {ev.get('event_time') or ''} {title}".strip(),
        "observation_time": dt.datetime.now().isoformat(timespec="seconds"),
        "calendar_version": 1,
        "possible_outcomes": [{
            "outcome_label": label,
            "observable_flag": flag,
            "observable_flag_source": ("国家统计局发布页当期与上期数值" if is_data else "主办方公告原文"),
            "affected_indicators": ids,
            "impact_note": impact_of(title, label, (prev_of(title) or {}).get("value")),
        } for label, flag in branches],
        "branch_ordering": ("按公布值相对前值由高到低排序" if pv
                            else ("排序不适用：前值不可得" if is_data else "排序不适用：会议进程不可比")),
        "branch_ordering_applicable": bool(pv),
        "no_prediction_statement": ("本记录只枚举可能结果与可观测标志，不预测哪个分支会发生、不给概率、"
                                    "不排序可能性、不判断方向；受影响指标为客观标注，不表示涨跌。"),
    }
    if pv:
        rec["prev_value"] = pv
    return rec


def validate(rec):
    with io.open(os.path.join(ROOT, "schemas", "scenario.schema.json"), encoding="utf-8") as f:
        sch = json.load(f)
    errs = [f"缺 {k}" for k in sch["required"] if k not in rec]
    if len(rec.get("possible_outcomes") or []) < 2:
        errs.append("分支少于 2 支")
    for o in rec.get("possible_outcomes") or []:
        for k in ("outcome_label", "observable_flag", "observable_flag_source", "affected_indicators"):
            if k not in o:
                errs.append(f"分支缺 {k}")
        if not o.get("affected_indicators"):
            errs.append("分支缺受影响指标")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default="")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list:
        for p in sorted(glob.glob(os.path.join(OUT, "scenario-scn-*.json"))):
            r = json.load(io.open(p, encoding="utf-8"))
            print(f"{os.path.basename(p):<40} {len(r['possible_outcomes'])} 支 · {r['event_summary'][:44]}")
        return 0

    as_of = a.as_of
    if not as_of:
        fs = sorted(glob.glob(os.path.join(OUT, "calendar-*.json")))
        if not fs:
            print("没有日历文件，先跑 events.py")
            return 2
        as_of = os.path.basename(fs[-1])[len("calendar-"):-len(".json")]
    cal = json.load(io.open(os.path.join(OUT, f"calendar-{as_of}.json"), encoding="utf-8"))
    # 只有「数据发布」有"公布值 vs 前值"三分支；解禁/新股/央行操作/会议硬套会张冠李戴
    fut = [e for e in cal["events"]
           if e.get("event_status") == "未来预定" and e.get("event_type") == "数据发布"]

    made = bad = 0
    for ev in fut:
        rec = build_record(ev)
        errs = validate(rec)
        if errs:
            bad += 1
            print(f"✗ {ev['event_date']} {ev['scope'][:24]}：{errs[:2]}")
            continue
        fp = os.path.join(OUT, f"scenario-{rec['event_id'].lower()}.json")
        with io.open(fp, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        made += 1
    print(f"生成分支记录 {made} 份" + (f"，失败 {bad}" if bad else "") + f"（as-of {as_of}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
