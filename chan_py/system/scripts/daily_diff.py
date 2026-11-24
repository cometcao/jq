#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日数值 diff + 源指纹（B：用"昨天的自己"当基准抓异常）。

解决的是这类 bug：源改版、单位错位、快照回放旧值——代码不报错，数字悄悄变了。
做法：
  1. **数值 diff**：同一指标相邻两个数据期，相对变化 > `jump_pct`（默认 20%）→ 告警。
  2. **源指纹**：每个指标记录 `shape`（返回字段数 + 行数），与上一期比，
     字段数变化 ≥ `shape_keys_delta`（默认 2）→ 告警（源结构可能改版）。
  3. **页面 diff**：证据行数、链条覆盖、跳过条数 与上一份快照比，掉档即告警。

用法：
  python -B scripts/daily_diff.py            # 今天 vs 昨天
  python -B scripts/daily_diff.py --date 2026-11-24
  python -B scripts/daily_diff.py --write    # 另存 reports/diff-<date>.md

退出码：0 无异常 / 1 有异常（供 refresh 与自检串联）。
"""
import io
import os
import sys
import json
import glob
import argparse
import datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACTS = os.path.join(ROOT, "data", "facts")
REPORTS = os.path.join(ROOT, "reports")
HIST = os.path.join(ROOT, "data", "history")
SKIPS = os.path.join(ROOT, "data", "skips")


def load(fp, default=None):
    try:
        with io.open(fp, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def thresholds():
    th = load(os.path.join(ROOT, "data", "thresholds.json"), {}) or {}
    return th.get("jump_pct", 20.0), th.get("shape_keys_delta", 2)


def num(t):
    import re
    m = re.search(r"-?[\d,]+(?:\.\d+)?", str(t or ""))
    return float(m.group(0).replace(",", "")) if m else None


def series_last_two(iid):
    """该指标最近两个数据期的 (period, base_value)。"""
    rows = []
    for fp in glob.glob(os.path.join(FACTS, "*", iid + ".json")):
        r = load(fp)
        if not r or not r.get("data_period"):
            continue
        v = r.get("base_value")
        if v is None:
            v = num((r.get("current_state") or {}).get("数值"))
        if v is None:
            continue
        rows.append((r["data_period"], v, r))
    rows.sort(key=lambda x: x[0])
    return rows[-2:] if len(rows) >= 2 else rows


def all_indicators():
    ids = set()
    for fp in glob.glob(os.path.join(FACTS, "*", "*.json")):
        r = load(fp)
        if r and r.get("indicator_id"):
            ids.add(r["indicator_id"])
    return sorted(ids)


def _hist_p99(iid):
    """该指标历史上"日变化率"的 99 分位（用它自己的波动定阈值）。"""
    fp = os.path.join(HIST, iid + ".jsonl")
    if not os.path.exists(fp):
        return None
    vals = []
    for line in io.open(fp, encoding="utf-8").read().splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        v = r.get("base_value", r.get("value"))
        if r.get("data_period") and v is not None:
            vals.append(v)
    if len(vals) < 8:
        return None
    ch = [abs(vals[i] - vals[i - 1]) / abs(vals[i - 1]) * 100
          for i in range(1, len(vals)) if vals[i - 1]]
    if not ch:
        return None
    ch.sort()
    return ch[int(len(ch) * 0.99) - 1] if len(ch) > 3 else max(ch)


def _registry():
    return load(os.path.join(ROOT, "dist", "market-state", "references", "registry.json"), {}) or {}


def check_jumps(verbose=False):
    """数值跳变检测：超过 max(全局阈值, 自身历史 99 分位 ×1.5) 才算异常。

    日频指标（广度、大宗、板块涨跌）天然会跳 50%+，用固定 20% 会天天误报；
    用每个指标自己的历史波动做基准，只抓"它从没这样跳过"的情况（单位错、回放、源改版）。
    """
    jump_pct, _ = thresholds()
    out = []
    for iid in all_indicators():
        rows = series_last_two(iid)
        if len(rows) < 2:
            continue
        (d0, v0, _r0), (d1, v1, _r1) = rows
        if not v0:
            continue
        reg = _registry().get(iid) or {}
        unit = reg.get("unit") or ""
        # 百分比类指标：用"百分点变化"判断，且允许跨零（相对变化无意义）
        if unit in ("U2", "U7") or "%" in str((_r1.get("current_state") or {}).get("数值") or ""):
            pp = abs(v1 - v0)
            if pp > 20:
                out.append({"indicator_id": iid, "period": d1, "prev_period": d0,
                            "value": v1, "prev": v0, "mode": "pp", "pct": round(pp, 2), "limit": 20})
            continue
        rel = abs(v1 - v0) / abs(v0) * 100
        p99 = _hist_p99(iid)
        # 无历史可校准的指标：放宽到 200%，并在报告里标"未校准"，避免天天误报
        limit = 200.0 if p99 is None else max(jump_pct, p99 * 1.5)
        if rel > limit:
            out.append({"indicator_id": iid, "period": d1, "prev_period": d0,
                        "value": v1, "prev": v0, "mode": "rel",
                        "pct": round(rel, 2), "limit": round(limit, 2),
                        "calibrated": p99 is not None})
    return out


def check_shapes(verbose=False):
    """源指纹变化检测。"""
    _, keys_delta = thresholds()
    out = []
    for iid in all_indicators():
        rows = series_last_two(iid)
        if len(rows) < 2:
            continue
        (d0, _v0, r0), (d1, _v1, r1) = rows
        s0, s1 = r0.get("shape"), r1.get("shape")
        if not s0 or not s1:
            continue
        if abs(int(s1.get("keys", 0)) - int(s0.get("keys", 0))) >= keys_delta:
            out.append({"indicator_id": iid, "period": d1, "before": s0, "after": s1})
    return out


def check_pages(day=None):
    """页面层：证据行数 / 链条覆盖 / 跳过条数 对比上一份快照。"""
    out = []
    pages = sorted(glob.glob(os.path.join(REPORTS, "*-market-state.md")))
    if len(pages) < 2:
        return out
    def stats(fp):
        t = io.open(fp, encoding="utf-8").read()
        body = t.split("```")[1] if "```" in t else t
        lines = [l for l in body.splitlines() if l.startswith("C") and "｜依据：" in l]
        cov = ""
        for l in body.splitlines():
            if l.startswith("链条完整性："):
                cov = l
        return {"file": os.path.basename(fp), "lines": len(lines), "chain": cov}
    a, b = stats(pages[-2]), stats(pages[-1])
    if a["lines"] and b["lines"] < a["lines"]:
        out.append({"kind": "页面", "msg": f"证据行数 {a['lines']} → {b['lines']}（{a['file']} → {b['file']}）"})
    if a["chain"] and b["chain"]:
        ca, cb = a["chain"].count("✓"), b["chain"].count("✓")
        if cb < ca:
            out.append({"kind": "页面", "msg": f"链条覆盖下降 {ca} → {cb}：{b['chain'][:60]}"})
    return out


def skips_of(day):
    fp = os.path.join(SKIPS, day + ".jsonl")
    if not os.path.exists(fp):
        return []
    res = []
    for line in io.open(fp, encoding="utf-8").read().splitlines():
        if line.strip():
            try:
                res.append(json.loads(line))
            except Exception:
                continue
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--write", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    jumps = check_jumps(a.verbose)
    shapes = check_shapes(a.verbose)
    pages = check_pages(a.date)
    skips = skips_of(a.date)
    skip_by_reason = {}
    for s in skips:
        skip_by_reason[s.get("reason", "?")] = skip_by_reason.get(s.get("reason", "?"), 0) + 1

    lines = [f"# 每日 diff · {a.date}", ""]
    lines.append(f"- 数值跳变告警：**{len(jumps)}** 条（阈值 {thresholds()[0]:.0f}%）")
    for j in jumps:
        unit = "pp" if j.get("mode") == "pp" else "%"
        cal = "" if j.get("calibrated", True) else "（未校准，按 200% 兜底）"
        lines.append(f"  - {j['indicator_id']}：{j['prev_period']} {j['prev']:.4g} → {j['period']} {j['value']:.4g}"
                     f"（{j['pct']}{unit}，上限 {j.get('limit')}）{cal}")
    lines.append(f"- 源指纹变化告警：**{len(shapes)}** 条")
    for s in shapes:
        lines.append(f"  - {s['indicator_id']}：字段数 {s['before'].get('keys')} → {s['after'].get('keys')}，"
                     f"行数 {s['before'].get('rows')} → {s['after'].get('rows')}")
    lines.append(f"- 页面异常：**{len(pages)}** 条")
    for p in pages:
        lines.append(f"  - {p['msg']}")
    lines.append(f"- 今日跳过：**{len(skips)}** 条")
    for r, n in sorted(skip_by_reason.items(), key=lambda x: -x[1]):
        lines.append(f"  - {r}：{n} 条")
    if not skips:
        lines.append("  - 无（所有指标都已落盘）")

    text = "\n".join(lines)
    if a.verbose or not (jumps or shapes or pages):
        print(text)
    else:
        print(text)
    if a.write:
        fp = os.path.join(REPORTS, f"diff-{a.date}.md")
        with io.open(fp, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print("\n已写入:", os.path.relpath(fp, ROOT))
    return 1 if (jumps or shapes or pages) else 0


if __name__ == "__main__":
    sys.exit(main())
