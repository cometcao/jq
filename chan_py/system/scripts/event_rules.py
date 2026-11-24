#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""事件显示规则（只做"是否值得上卡"，不做影响判断）。

解禁的显示阈值（V2.137.0 定稿）：
    解禁市值 ≥ max(200 亿, 1% × 近 20 日两市成交额均值)

理由：解禁的影响来自"可流通筹码相对成交规模"，单看绝对额会在成交极小或极大的日子失真；
所以用"绝对下限 + 相对成交额"双条件，任一满足即显示。低于阈值的不删除数据（日历仍保留），
只在卡上折叠并写出折叠条数——不允许静默消失。
"""
import io
import os
import re
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULTS = {"unlock_abs_yi": 200.0, "unlock_pct_of_turnover": 1.0}


def thresholds():
    th = dict(DEFAULTS)
    try:
        with io.open(os.path.join(ROOT, "data", "thresholds.json"), encoding="utf-8") as f:
            th.update({k: v for k, v in (json.load(f) or {}).items()
                       if k in ("unlock_abs_yi", "unlock_pct_of_turnover")})
    except Exception:
        pass
    return th


def unlock_mv(scope):
    """从"限售解禁：N 家，解禁市值 X 亿"里取市值（亿）；取不到返回 None。"""
    m = re.search(r"解禁市值\s*([\d.]+)\s*亿", str(scope or ""))
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def unlock_passes(scope, turnover_yi, th=None):
    """解禁是否值得上卡。返回 (是否显示, 市值, 占成交额比%)。"""
    th = th or thresholds()
    mv = unlock_mv(scope)
    if mv is None:
        return True, None, None           # 取不到市值就不做过滤（宁可显示）
    ratio = (mv / turnover_yi * 100) if turnover_yi else None
    ok = mv >= float(th["unlock_abs_yi"])
    if not ok and ratio is not None:
        ok = ratio >= float(th["unlock_pct_of_turnover"])
    return ok, mv, ratio


def rule_text(th=None):
    th = th or thresholds()
    return f"解禁仅显示 ≥{th['unlock_abs_yi']:.0f} 亿或 ≥{th['unlock_pct_of_turnover']:.0f}% 当日成交额"


def filter_events(events, turnover_yi, th=None):
    """按显示规则过滤事件。返回 (要显示的事件, 折叠的 {类型: 条数}, 折叠说明)。"""
    th = th or thresholds()
    shown, folded = [], {}
    for e in events:
        if "限售解禁" in (e.get("scope") or "") or e.get("event_type") == "解禁":
            ok, mv, ratio = unlock_passes(e.get("scope"), turnover_yi, th)
            if not ok:
                folded["解禁"] = folded.get("解禁", 0) + 1
                continue
        shown.append(e)
    note = ""
    if folded:
        parts = "；".join(f"{k} 折叠 {v} 天" for k, v in sorted(folded.items()))
        note = f"{rule_text(th)}；{parts}（数据仍在日历 JSON）"
    return shown, folded, note


def main():
    import sys
    tx = float(sys.argv[1]) if len(sys.argv) > 1 else 16585.24
    cases = [("限售解禁：1 家，解禁市值 298.7 亿", True),
             ("限售解禁：5 家，解禁市值 7.2 亿", False),
             ("限售解禁：20 家，解禁市值 150.0 亿", False),
             ("限售解禁：20 家，解禁市值 200.0 亿", True)]
    bad = 0
    for scope, exp in cases:
        ok, mv, ratio = unlock_passes(scope, tx)
        print(("  ✓ " if ok == exp else "  ✗ ") + f"{mv} 亿 → {'显示' if ok else '折叠'}（期望 {'显示' if exp else '折叠'}）")
        bad += 0 if ok == exp else 1
    print(f"\n解禁阈值自检：{len(cases) - bad}/{len(cases)} 通过 · {rule_text()}")
    return 0 if not bad else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
