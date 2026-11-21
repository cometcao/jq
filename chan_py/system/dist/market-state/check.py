#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""market-state 自带自检：记录（结构+语义）与页面（证据行+措辞）。

用法：
    python check.py --demo                       # 内置正反例
    python check.py record.json [more.json ...]  # 校验事实/比价/事件/分支记录
    python check.py --page output.md             # 校验输出正文（优先取含 as-of 的代码块）
    python check.py --as-of 2026-11-21 r.json    # 指定 as-of 以计算 stale

退出码：0 通过 / 1 有错 / 2 用法错。只依赖标准库。
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "references")

# 状态词镜像 references/reading-rules.md（--demo 会检查是否漂移）
STATE_WORDS = {
    "C1": ["偏松", "偏紧", "不变"],
    "C2": ["扩", "缩", "不变", "份额升", "份额降", "偏活", "偏死"],
    "C3": ["变贵", "变便宜", "不变", "偏贵", "偏便宜"],
    "C4": ["加杠杆", "去杠杆", "不变", "增", "减", "不可读"],
    "C5": ["增", "减", "不变", "升", "降", "不可读"],
    "C6": ["升", "降", "不变", "强", "弱", "聚", "散", "相对强", "相对弱", "不可读"],
}
BANNED = ["建议", "应当", "看多", "看空", "偏强", "偏弱", "低吸", "高抛", "抄底", "逃顶",
          "支撑位", "压力位", "见底", "见顶", "资金流入", "资金流出", "净流入", "净流出",
          "进场", "撤离", "加仓", "减仓", "聪明钱", "主力吸筹", "概率", "有望", "预计",
          "预期", "或将", "评分", "打分", "综合得分", "背离强度", "资金整体", "宽松", "充裕", "活跃"]
CAUSAL = ["因此", "所以", "导致", "意味着"]
COUNTERPARTY = ["接盘", "出货", "资金从", "流向", "外资撤离"]
FREQ_DAYS = {"日": 1, "周": 7, "月": 30, "季": 90, "年": 365}


def load(name):
    with open(os.path.join(REF, name), encoding="utf-8") as f:
        return json.load(f)


# ---------------- JSON Schema 子集 ----------------
def _ok(v, types):
    m = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None),
         "integer": int, "number": (int, float)}
    for t in types:
        if t == "integer" and isinstance(v, bool):
            continue
        if isinstance(v, m.get(t, object)):
            return True
    return False


def validate(node, schema, path="$"):
    errs = []
    t = schema.get("type")
    if t is not None and not _ok(node, t if isinstance(t, list) else [t]):
        return [f"{path}: 类型错误"]
    if "enum" in schema and node not in schema["enum"]:
        errs.append(f"{path}: 不在枚举 {schema['enum']}")
    if "const" in schema and node != schema["const"]:
        errs.append(f"{path}: 应为 {schema['const']!r}")
    if isinstance(node, str):
        if "minLength" in schema and len(node) < schema["minLength"]:
            errs.append(f"{path}: 过短")
        if "pattern" in schema and not re.search(schema["pattern"], node):
            errs.append(f"{path}: 不匹配 {schema['pattern']}")
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        if "minimum" in schema and node < schema["minimum"]:
            errs.append(f"{path}: < {schema['minimum']}")
    if isinstance(node, dict):
        for r in schema.get("required", []):
            if r not in node:
                errs.append(f"{path}: 缺必填 {r}")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for k in node:
                if k not in props:
                    errs.append(f"{path}: 未知字段 {k}")
        for k, sub in props.items():
            if k in node:
                errs.extend(validate(node[k], sub, f"{path}.{k}"))
    if isinstance(node, list):
        if "minItems" in schema and len(node) < schema["minItems"]:
            errs.append(f"{path}: 少于 {schema['minItems']} 项")
        if isinstance(schema.get("items"), dict):
            for i, v in enumerate(node):
                errs.extend(validate(v, schema["items"], f"{path}[{i}]"))
    for sub in schema.get("allOf", []):
        if "if" in sub:
            if not validate(node, sub["if"], path) and "then" in sub:
                errs.extend(validate(node, sub["then"], path))
        else:
            errs.extend(validate(node, sub, path))
    return errs


# ---------------- 记录语义 ----------------
def _days(a, b):
    import datetime
    return (datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days


def check_fact(rec, schema, reg, as_of):
    errs = [f"[结构] {e}" for e in validate(rec, schema)]
    meta = reg.get(rec.get("indicator_id"))
    if meta is None:
        errs.append(f"[注册表] 未知指标 {rec.get('indicator_id')}")
    else:
        for k in ("channel", "subject", "value_kind"):
            if rec.get(k) and meta.get(k) and rec[k] != meta[k]:
                errs.append(f"[注册表] {k}={rec[k]!r} 与注册表 {meta[k]!r} 不一致")
    if as_of and rec.get("data_period") and rec.get("update_frequency") in FREQ_DAYS:
        try:
            gap = _days(rec["data_period"], as_of) / FREQ_DAYS[rec["update_frequency"]]
            mt = rec.get("missing_type")
            if gap > 3:
                errs.append(f"[stale] 距更新 {gap:.1f} 倍 > 3，应视为不可读")
            elif gap > 2 and mt != "stale":
                errs.append(f"[stale] 距更新 {gap:.1f} 倍 > 2，应标 stale（当前 {mt}）")
            elif gap <= 2 and mt == "stale":
                errs.append(f"[stale] 距更新 {gap:.1f} 倍 ≤ 2，不应标 stale")
        except ValueError:
            errs.append(f"[stale] data_period 不是 YYYY-MM-DD")
    return errs


def check_compare(rec, schema, reg, as_of):
    errs = [f"[结构] {e}" for e in validate(rec, schema)]
    ids = [i["ref"] for i in rec.get("inputs", []) if i.get("ref_type") == "indicator_id"]
    for i in ids:
        if i not in reg:
            errs.append(f"[注册表] 输入 {i} 未注册")
    if len(ids) >= 2 and all(i in reg for i in ids[:2]):
        a, b = reg[ids[0]], reg[ids[1]]
        if (a["attribute"], a["transform"]) != (b["attribute"], b["transform"]):
            errs.append(f"[同质锚] {ids[0]} 与 {ids[1]} 不同质")
    if rec.get("value_kind") == "price":
        errs.append("[V-b] 比价结果不得为 price")
    for s in rec.get("series") or []:
        if s.get("value_kind") == "price":
            errs.append("[V-b] series 含 price")
    return errs


def check_event(rec, schema, reg, as_of):
    return [f"[结构] {e}" for e in validate(rec, schema)]


def check_scenario(rec, schema, reg, as_of):
    errs = [f"[结构] {e}" for e in validate(rec, schema)]
    for o in rec.get("possible_outcomes", []):
        for i in o.get("affected_indicators", []):
            if i not in reg:
                errs.append(f"[注册表] 受影响指标未注册 {i}")
        for w in ["好于", "差于", "积极", "消极", "超预期", "不及预期"]:
            if w in o.get("observable_flag", ""):
                errs.append(f"[分支] 标志含方向词 {w}")
    return errs


def detect(obj):
    if "compare_id" in obj:
        return "compare"
    if "possible_outcomes" in obj:
        return "scenario"
    if "event_date" in obj and "event_status" in obj:
        return "event"
    if "record_id" in obj:
        return "fact"
    return None


# ---------------- 页面 ----------------
def _banned_hits(text):
    negs = ["不", "非", "无", "≠", "不等于"]
    hits = []
    for w in BANNED:
        for m in re.finditer(re.escape(w), text):
            if any(n in text[max(0, m.start() - 8):m.start()] for n in negs):
                continue
            hits.append(w)
            break
    return hits


def check_render(text):
    """校验 ```render 块：组件白名单、覆盖条六环齐全、折线≤1、禁 price、必须绑证据行。"""
    blocks = re.findall(r"```render\s*\n(.*?)```", text, flags=re.S)
    errs = []
    for b in blocks:
        try:
            spec = json.loads(b)
        except Exception as e:
            errs.append(f"[render] JSON 解析失败：{e}")
            continue
        comps = spec.get("components", [])
        types = [c.get("type") for c in comps]
        for tp in types:
            if tp not in ("rings_coverage", "series", "multi_target"):
                errs.append(f"[render] 未知组件 {tp}")
        for tp, limit, label in (("rings_coverage", 1, "覆盖条"), ("series", 1, "折线"), ("multi_target", 1, "并排小格")):
            if types.count(tp) > limit:
                errs.append(f"[render] {label}超过 {limit} 张")
        for c in comps:
            if c.get("type") == "rings_coverage":
                rings = [r.get("ring") for r in c.get("rings", [])]
                if rings != ["C1", "C2", "C3", "C4", "C5", "C6"]:
                    errs.append("[render] 覆盖条必须按 C1–C6 六环齐全")
                for r in c.get("rings", []):
                    if r.get("state") not in ("has_evidence", "substitute", "unreadable"):
                        errs.append(f"[render] 非法 state：{r.get('state')}")
            if c.get("type") == "series":
                if c.get("value_kind") == "price":
                    errs.append("[render] 折线 value_kind 不得为 price")
                if not str(c.get("boundary_text") or "").strip():
                    errs.append("[render] 折线缺 boundary_text")
            if c.get("type") == "rings_coverage":
                for r in c.get("rings", []):
                    rev = str(r.get("evidence_line") or "").strip()
                    if not rev:
                        errs.append("[render] 覆盖条某环缺 evidence_line")
                    elif rev not in text:
                        errs.append(f"[render] 覆盖条证据行在输出里找不到：{rev[:24]}")
            else:
                ev = str(c.get("evidence_line") or "").strip()
                if not ev:
                    errs.append("[render] 组件缺 evidence_line")
                elif ev not in text:
                    errs.append(f"[render] evidence_line 在输出里找不到：{ev[:24]}")
    return errs


def check_page(text):
    blocks = re.findall(r"```[a-zA-Z]*\n(.*?)```", text, flags=re.S)
    cands = [b for b in blocks if "as-of" in b]
    if cands:
        target = max(cands, key=lambda b: len(re.findall(r"^C[1-6]\s", b, flags=re.M)))
    elif "as-of" in text[:300]:
        target = text
    else:
        return ["[V-g] 未找到输出正文（含 as-of 的代码块或纯文本）"]
    errs = []
    lines = [ln.strip() for ln in target.splitlines() if ln.strip()]
    if not lines or "as-of" not in lines[0]:
        errs.append("[V-l] 首行应为 `as-of …`")
    rings = [ln for ln in lines if re.match(r"^C[1-6]\s", ln)]
    if rings:
        order = []
        for ln in rings:
            r = ln[:2]
            order.append(r)
            if "｜依据：" not in ln:
                errs.append(f"[V-j] 缺“依据”：{ln[:36]}")
            if "｜边界：" not in ln:
                errs.append(f"[V-j] 缺“边界”：{ln[:36]}")
            if "不可读" not in ln:
                ws = STATE_WORDS.get(r, [])
                if ws and not any(w in ln for w in ws):
                    errs.append(f"[V-j] {r} 未用白名单状态词：{ln[:36]}")
            elif "无源" not in ln and "无证据" not in ln and "stale" not in ln:
                errs.append(f"[V-j] 不可读行应写无源/无证据/stale：{ln[:36]}")
        rank = {"C1": 1, "C2": 2, "C3": 3, "C4": 4, "C5": 5, "C6": 6}
        seq = [rank[r] for r in order]
        if seq != sorted(seq):
            errs.append(f"[V-g] 六环顺序错乱：{order}")
    for w in _banned_hits(target):
        errs.append(f"[V-d] 禁用词：{w}")
    for w in CAUSAL:
        if w in target:
            errs.append(f"[V-k] 因果连词：{w}")
    for w in COUNTERPARTY:
        if w in target:
            errs.append(f"[V-m] 对手方叙事：{w}")
    errs.extend(check_render(text))
    return errs


# ---------------- 入口 ----------------
def demo():
    reg = load("registry.json")
    schemas = {k: load(os.path.join("schema", k + ".schema.json")) for k in ("fact", "compare", "event", "scenario")}
    fact = {
        "record_id": "r1", "layer": "市场", "indicator_id": "MKT_TURNOVER", "channel": "C6",
        "subject": "公共池", "derived_type": "聚合值", "value_kind": "level",
        "observation_time": "2026-11-21T17:31+08:00", "release_date": "2026-11-20",
        "data_period": "2026-11-20", "update_frequency": "日", "source_tier": "C",
        "fallback_flag": False, "missing_type": "none", "value_type": "初值",
        "proves": "成交额较上日增加", "does_not_prove": "不说明资金来源",
        "rule_status": "ratified", "status": "active",
        "current_state": {"指标": "两市成交额", "数值": "14222 亿元", "数据所属期": "2026-11-20"},
    }
    cmp_ = {
        "compare_id": "CMP-1", "compare_type": "time_self", "compare_operation": "difference",
        "operand_order": "M2同比 − M1同比", "result_form": "point_value",
        "anchor": {k: "x" for k in ["同质锚", "属性锚", "口径锚", "窗口锚", "层级锚", "归属锚", "量纲锚"]},
        "inputs": [{"ref_type": "indicator_id", "ref": "MKT_M2_YOY", "layer": "市场", "data_period": "2026-10"},
                   {"ref_type": "indicator_id", "ref": "MKT_M1_YOY", "layer": "市场", "data_period": "2026-10"}],
        "data_period": "2026-10", "window": "2024-01..2026-10", "value_kind": "level",
        "current_state": {"对比结果": "剪刀差", "数值": "+2.2pp", "数据所属期": "2026-10"},
        "observation_time": "2026-11-21T17:31+08:00", "release_date": "2026-11-15",
        "update_frequency": "月", "source_tier": "A", "fallback_flag": False,
        "missing_type": "none", "value_type": "初值", "rule_status": "ratified",
    }
    good_page = ("as-of 2026-11-20（最慢环 C6）\n"
                 "C1 不可读（—）｜依据：无源｜边界：该环无证据\n"
                 "C6 参与度升（2026-11-20）｜依据：成交额 14222 > 13051 亿｜边界：不说明资金来源\n")
    bad_page = ("as-of 2026-11-20\nC6 参与度升（2026-11-20）｜依据：成交额上升｜边界：无\n"
                "资金整体在收缩，因此增量资金充裕。\n")
    ring_page = ("as-of 2026-11-20（最慢环 C6）\n"
                 "C1 不可读（—）｜依据：无源｜边界：该环无证据\n"
                 "C6 参与度升（2026-11-20）｜依据：成交额 14222 > 13051 亿｜边界：不说明资金来源\n")
    def with_render(spec):
        return ring_page + "```render\n" + json.dumps(spec, ensure_ascii=False) + "\n```\n"
    rc_list = [{"ring": r, "state": "unreadable", "evidence_line": "C1 不可读（—）"} for r in ("C1", "C2", "C3", "C4", "C5")]
    rc_list.append({"ring": "C6", "state": "has_evidence", "evidence_line": "C6 参与度升（2026-11-20）"})
    good_render = {"components": [{"type": "rings_coverage", "rings": rc_list}]}
    bad_price = {"components": [{"type": "series", "series_id": "CMP-1", "value_kind": "price",
                                 "evidence_line": "C6 参与度升（2026-11-20）", "boundary_text": "不说明趋势"}]}
    bad_boundary = {"components": [{"type": "series", "series_id": "CMP-1", "value_kind": "level",
                                    "evidence_line": "C6 参与度升（2026-11-20）"}]}
    bad_rings = {"components": [{"type": "rings_coverage", "rings": rc_list[:3]}]}
    cases = [
        ("render 正例", check_page(with_render(good_render)), 0),
        ("render 折线 price", check_page(with_render(bad_price)), None),
        ("render 折线缺边界", check_page(with_render(bad_boundary)), None),
        ("render 覆盖条缺环", check_page(with_render(bad_rings)), None),
        ("事实正例", check_fact(fact, schemas["fact"], reg, "2026-11-21"), 0),
        ("事实 channel 错", check_fact(dict(fact, channel="C2"), schemas["fact"], reg, "2026-11-21"), 1),
        ("事实超 3 倍未标", check_fact(dict(fact, data_period="2026-06-01"), schemas["fact"], reg, "2026-11-21"), 1),
        ("比价正例", check_compare(cmp_, schemas["compare"], reg, None), 0),
        ("比价 rank 缺 universe", check_compare(dict(cmp_, result_form="rank"), schemas["compare"], reg, None), 1),
        ("页面正例", check_page(good_page), 0),
        ("页面命中禁用词", check_page(bad_page), None),
    ]
    ev = {
        "event_id": "EV-1", "event_type": "数据发布", "layer": "市场", "event_date": "2026-11-25",
        "data_period": "2026-10", "event_status": "未来预定", "issuer": "国家统计局",
        "entry_mode": "manual", "source_tier": "A", "source_link": "https://www.stats.gov.cn/sj/zxfb/",
        "calendar_version": 7, "observation_time": "2026-11-21T20:00+08:00", "missing_type": "none",
    }
    sc = {
        "event_id": "EV-2", "event_summary": "CPI 同比", "observation_time": "2026-11-21T20:00+08:00",
        "calendar_version": 7,
        "possible_outcomes": [
            {"outcome_label": "高于前值", "observable_flag": "公布值 > 前值",
             "observable_flag_source": "统计局发布页", "affected_indicators": ["MKT_CPI_YOY"]},
            {"outcome_label": "低于前值", "observable_flag": "公布值 < 前值",
             "observable_flag_source": "统计局发布页", "affected_indicators": ["MKT_CPI_YOY"]}],
        "branch_ordering": "不适用：前值不可得", "branch_ordering_applicable": False,
        "no_prediction_statement": "以上为可能结果分支的枚举与可观测标志，不预测哪个分支会发生。",
    }
    cases.append(("事件正例", check_event(ev, schemas["event"], reg, None), 0))
    cases.append(("事件 manual 缺链接", check_event(dict(ev, source_link=None), schemas["event"], reg, None), 1))
    cases.append(("分支正例（前值不可得已标不适用）", check_scenario(sc, schemas["scenario"], reg, None), 0))
    cases.append(("分支排序未标不适用", check_scenario(dict(sc, branch_ordering="按进程"), schemas["scenario"], reg, None), 1))
    rules = open(os.path.join(REF, "reading-rules.md"), encoding="utf-8").read()
    drift = [w for ws in STATE_WORDS.values() for w in ws if w not in rules and w not in ("增", "减", "升", "降")]
    cases.append(("词表未漂移", [f"reading-rules 缺词 {w}" for w in drift], 0))
    ok = True
    for name, errs, exp in cases:
        good = (len(errs) == exp) if exp is not None else (len(errs) > 0)
        ok = ok and good
        print(("PASS " if good else "FAIL ") + f"{name}: {len(errs)} 错误")
        if not good:
            for e in errs[:3]:
                print("   -", e)
    print("\nDEMO:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv):
    if "--demo" in argv:
        return demo()
    reg = load("registry.json")
    if "--page" in argv:
        p = argv[argv.index("--page") + 1]
        errs = check_page(open(p, encoding="utf-8").read())
        print(("✓ " if not errs else "✗ ") + f"{p}  {len(errs)} 错误")
        for e in errs:
            print("    -", e)
        return 0 if not errs else 1
    as_of = None
    if "--as-of" in argv:
        as_of = argv[argv.index("--as-of") + 1]
    files = [a for a in argv[1:] if not a.startswith("--") and a != as_of]
    if not files:
        print(__doc__)
        return 2
    schemas = {k: load(os.path.join("schema", k + ".schema.json")) for k in ("fact", "compare", "event", "scenario")}
    total = 0
    for p in files:
        try:
            obj = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            print(f"✗ {p}: 解析失败 {e}")
            total += 1
            continue
        kind = detect(obj)
        if not kind:
            print(f"✗ {p}: 无法识别类型")
            total += 1
            continue
        fn = {"fact": check_fact, "compare": check_compare, "event": check_event, "scenario": check_scenario}[kind]
        errs = fn(obj, schemas[kind], reg, as_of)
        total += len(errs)
        print(("✓ " if not errs else "✗ ") + f"{p} [{kind}]  {len(errs)} 错误")
        for e in errs:
            print("    -", e)
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
