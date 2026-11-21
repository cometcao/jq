#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""比价记录生成器：按七锚校验后，产出符合 schemas/compare.schema.json 的记录。

规则依据：docs/01 第七节 + 附录 B（七锚）、ADR-001（价格比值禁止）、附录 E（compare schema）。

用法：
    python scripts/compare.py --left MKT_M2_YOY --right MKT_M1_YOY --op difference
    python scripts/compare.py --left SECTOR_VAL --op percent_change
    python scripts/compare.py --list                 # 列出可比指标与数据期
    python scripts/compare.py ... --dry              # 只校验不落盘

七锚不通过 → **不产出记录**，打印是哪一锚失败（规则：不给"勉强可比"）。
"""
import argparse
import datetime as dt
import glob
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACTS = os.path.join(ROOT, "data", "facts")
REVIS = os.path.join(ROOT, "data", "revisions")
OUT = os.path.join(ROOT, "data", "compares")
REGISTRY = os.path.join(ROOT, "dist", "market-state", "references", "registry.json")

UNIT_NAME = {"U1": "亿元", "U2": "%", "U3": "万人", "U4": "亿股", "U5": "万户",
             "U6": "点", "U7": "%", "U8": "文字"}


def load_registry():
    with io.open(REGISTRY, encoding="utf-8") as f:
        return json.load(f)


def load_facts():
    """{indicator_id: [record,...] 按数据期升序}"""
    out = {}
    for fp in glob.glob(os.path.join(FACTS, "*", "*.json")):
        try:
            with io.open(fp, encoding="utf-8") as f:
                rec = json.load(f)
        except Exception:
            continue
        out.setdefault(rec["indicator_id"], []).append(rec)
    for k in out:
        out[k].sort(key=lambda r: r.get("data_period") or "")
    return out


def num(s):
    if s is None:
        return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?", str(s).replace(",", ""))
    return float(m.group(0)) if m else None


def latest(facts, iid):
    rows = facts.get(iid) or []
    return rows[-1] if rows else None


def revisions_periods(iid):
    d = os.path.join(REVIS, iid)
    if not os.path.isdir(d):
        return []
    return sorted(os.path.basename(p)[:-6] for p in glob.glob(os.path.join(d, "*.jsonl")))


def anchored(facts, reg, left, right, op, args):
    """七锚校验。返回 (ok, anchors, payload) 或抛 ValueError 带失败锚名。"""
    lrec = latest(facts, left)
    rrec = latest(facts, right) if right else None
    if not lrec:
        raise ValueError(f"同质锚：左操作数 {left} 无落地事实")
    lmeta = reg.get(left) or {}
    rmeta = reg.get(right) or {} if right else {}

    # 1 同质锚：同一层级
    if rrec and lmeta.get("layer") != rmeta.get("layer"):
        raise ValueError(f"层级锚：{left}={lmeta.get('layer')}，{right}={rmeta.get('layer')}，跨层不可比")
    # 2 量纲锚
    if rrec and lmeta.get("unit") != rmeta.get("unit"):
        raise ValueError(f"量纲锚：{left}={lmeta.get('unit')}（{UNIT_NAME.get(lmeta.get('unit'),'?')}）"
                         f"，{right}={rmeta.get('unit')}（{UNIT_NAME.get(rmeta.get('unit'),'?')}）")
    # 3 口径锚：数据期一致（横截面）
    if op in ("difference", "ratio", "spread"):
        if rrec is None:
            raise ValueError("同质锚：比值/差值需要两个操作数")
        if lrec.get("data_period") != rrec.get("data_period"):
            raise ValueError(f"口径锚：数据期不同（{left}={lrec.get('data_period')}，{right}={rrec.get('data_period')}）；"
                             f"平铺会把不同口径混在一个数里")
    # 4 属性锚：价格水平禁止做比值（ADR-001 / F03）
    if op == "ratio" and (lmeta.get("value_kind") == "price" or rmeta.get("value_kind") == "price"):
        raise ValueError("属性锚：价格水平（price）不得做比值——与价格走势同构（ADR-001）")

    lp, rp = num(lrec["current_state"]["数值"]), num(rrec["current_state"]["数值"]) if rrec else None
    if lp is None or (rrec and rp is None):
        raise ValueError("同质锚：操作数数值无法解析")

    anchors = {
        "同质锚": f"{left} 与 {right or '（自身历史）'} 均为{UNIT_NAME.get(lmeta.get('unit'),'同量纲')}量",
        "属性锚": f"value_kind={lmeta.get('value_kind')}"
                  + (f" / {rmeta.get('value_kind')}" if rrec else "") + "；未使用价格水平比值",
        "口径锚": f"data_period={lrec.get('data_period')}"
                  + (f"（两侧一致）" if rrec else "（时间自比，见窗口锚）"),
        "窗口锚": args.window or f"最新一期 {lrec.get('data_period')} 对上一期",
        "层级锚": f"{lmeta.get('layer')}" + (f" / {rmeta.get('layer')}（一致）" if rrec else ""),
        "归属锚": f"subject={lmeta.get('subject')}"
                  + (f" / {rmeta.get('subject')}" if rrec else "") + (f"；universe={args.universe}" if args.universe else ""),
        "量纲锚": f"{lmeta.get('unit')}（{UNIT_NAME.get(lmeta.get('unit'),'?')}）一致",
    }
    return lrec, rrec, lp, rp, anchors


def build(args):
    reg, facts = load_registry(), load_facts()
    left, right, op = args.left, args.right, args.op

    if op == "percent_change":
        periods = revisions_periods(left)
        if len(periods) < 2:
            raise ValueError(f"窗口锚：{left} 的修订链只有 {len(periods)} 个数据期，无法做时间自比（需 ≥2）")
        lrec = latest(facts, left)
        lp = num(lrec["current_state"]["数值"])
        # 前值优先取缓存 prev_value
        prevp = None
        p = os.path.join(ROOT, "data", "cache", left + ".json")
        if os.path.exists(p):
            prevp = num(json.load(io.open(p, encoding="utf-8")).get("prev_value"))
        if prevp is None or lp is None:
            raise ValueError("窗口锚：前值不可得（缓存无 prev_value）")
        val = (lp / prevp - 1) * 100
        lmeta = reg.get(left) or {}
        anchors = {
            "同质锚": f"{left} 自身前后两期同口径",
            "属性锚": f"value_kind={lmeta.get('value_kind')} → 结果为 return",
            "口径锚": f"{periods[-2]} → {periods[-1]}",
            "窗口锚": args.window or f"{periods[-2]} 对 {periods[-1]}（相邻两期）",
            "层级锚": f"{lmeta.get('layer')}",
            "归属锚": f"subject={lmeta.get('subject')}",
            "量纲锚": f"{lmeta.get('unit')}（{UNIT_NAME.get(lmeta.get('unit'),'?')}），结果以 % 表示",
        }
        payload = {
            "compare_type": "time_self", "compare_operation": "percent_change",
            "result_form": "point_value", "operand_order": f"{left}({periods[-1]}) / {left}({periods[-2]})",
            "reference": f"{periods[-2]} 值 {prevp}",
            "inputs": [{"ref_type": "indicator_id", "ref": left, "layer": lmeta.get("layer", "市场"),
                        "data_period": periods[-2]},
                       {"ref_type": "indicator_id", "ref": left, "layer": lmeta.get("layer", "市场"),
                        "data_period": periods[-1]}],
            "state": (f"{left} 变化率", f"{val:+.2f}%", periods[-1]),
            "value_kind": "return", "data_period": periods[-1],
            "window": anchors["窗口锚"], "anchors": anchors,
            "tier": (latest(facts, left) or {}).get("source_tier", "C"),
        }
        return payload

    lrec, rrec, lp, rp, anchors = anchored(facts, reg, left, right, op, args)
    if op in ("difference", "spread"):
        val, kind, label = lp - rp, "ratio", f"{lp} − {rp}"
        text = f"{val:+.2f}" + ("pp" if (reg.get(left) or {}).get("unit") == "U2" else "")
    else:  # ratio
        if rp == 0:
            raise ValueError("量纲锚：分母为 0，比值不可计算")
        val, kind, label = lp / rp, "ratio", f"{lp} ÷ {rp}"
        text = f"{val:.2f}×"
    payload = {
        "compare_type": "cross_sectional", "compare_operation": op,
        "result_form": "point_value", "operand_order": f"{left} {'−' if op != 'ratio' else '÷'} {right}",
        "reference": None,
        "inputs": [{"ref_type": "indicator_id", "ref": left, "layer": (reg.get(left) or {}).get("layer", "市场"),
                    "data_period": lrec["data_period"]},
                   {"ref_type": "indicator_id", "ref": right, "layer": (reg.get(right) or {}).get("layer", "市场"),
                    "data_period": rrec["data_period"]}],
        "state": (f"{left} {'减' if op != 'ratio' else '除'} {right}", text, lrec["data_period"]),
        "value_kind": kind, "data_period": lrec["data_period"], "window": anchors["窗口锚"],
        "anchors": anchors, "tier": lrec.get("source_tier", "C"),
    }
    return payload


def to_record(payload):
    now = dt.datetime.now().isoformat(timespec="seconds")
    title, value, period = payload["state"]
    cid = f"CMP-{payload['compare_operation']}-{payload['inputs'][0]['ref']}-{payload['inputs'][-1]['ref']}-{period}".upper()
    rec = {
        "compare_id": cid,
        "compare_type": payload["compare_type"],
        "compare_operation": payload["compare_operation"],
        "result_form": payload["result_form"],
        "operand_order": payload["operand_order"],
        "universe": None,
        "reference": payload.get("reference"),
        "anchor": payload["anchors"],
        "inputs": payload["inputs"],
        "current_state": {"对比结果": title, "数值": value, "数据所属期": period},
        "data_period": period,
        "window": payload["window"],
        "value_kind": payload["value_kind"],
        "observation_time": now,
        "release_date": period,
        "update_frequency": "日",
        "source_tier": payload["tier"],
        "fallback_flag": False,
        "missing_type": "none",
        "value_type": "初值",
        "rule_status": "ratified",
    }
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--left")
    ap.add_argument("--right")
    ap.add_argument("--op", choices=["difference", "ratio", "spread", "percent_change"], default="difference")
    ap.add_argument("--window")
    ap.add_argument("--universe")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list:
        reg, facts = load_registry(), load_facts()
        print(f"{'指标':<24}{'层':<6}{'单位':<8}{'数据期':<12}值")
        print("-" * 78)
        for iid in sorted(facts):
            rec = latest(facts, iid)
            m = reg.get(iid, {})
            print(f"{iid:<24}{m.get('layer','?'):<6}{m.get('unit','?'):<8}"
                  f"{(rec.get('data_period') or ''):<12}{(rec.get('current_state') or {}).get('数值','')}")
        return 0

    if not a.left:
        ap.error("--left 必填（或用 --list 查看可用指标）")
    try:
        payload = build(a)
    except ValueError as e:
        print(f"✗ 七锚不通过 → 不产出记录\n  {e}")
        return 2

    rec = to_record(payload)
    print("七锚：")
    for k, v in rec["anchor"].items():
        print(f"  {k}：{v}")
    print(f"\n对比结果：{rec['current_state']['对比结果']} = {rec['current_state']['数值']}"
          f"（{rec['data_period']}）")
    if not a.dry:
        os.makedirs(OUT, exist_ok=True)
        fp = os.path.join(OUT, rec["compare_id"] + ".json")
        with io.open(fp, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        print("已写入:", os.path.relpath(fp, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
