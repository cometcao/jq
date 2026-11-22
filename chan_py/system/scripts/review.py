#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复盘对照：拿某天归档的状态快照，和"现在的状态"比一遍。

回答复盘的三个问题：
  1. 当时看到什么？（读 reports/state-history/<date>-<layer>.json，原样不改）
  2. 后来变了什么？（与当前状态逐环对比状态词与数值）
  3. 差在哪？（标出"当时有值→现在无值""状态词翻转""数值变化"）

用法：
    python scripts/review.py --list                 # 有哪些快照
    python scripts/review.py --date 2026-11-20      # 市场层对照
    python scripts/review.py --date 2026-11-20 --layer sector
"""
import argparse
import glob
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST = os.path.join(ROOT, "reports", "state-history")
REPORTS = os.path.join(ROOT, "reports")


def load_snapshot(date, layer):
    fp = os.path.join(HIST, f"{date}-{layer}.json")
    if not os.path.exists(fp):
        raise SystemExit(f"没有该日快照：{os.path.relpath(fp, ROOT)}（用 --list 看现有）")
    with io.open(fp, encoding="utf-8") as f:
        return json.load(f)


def parse_lines(body):
    """把 body 拆成 {环: [(状态词, 依据, 边界)]} 与链条行。"""
    rings, chain = {}, []
    for ln in body.splitlines():
        if ln.startswith("链条完整性") or ln.startswith("本次 "):
            chain.append(ln)
            continue
        m = re.match(r"^(C[1-6]) (\S+?)(（[^）]*）)?｜依据：(.+?)｜边界：", ln)
        if not m:
            continue
        rings.setdefault(m.group(1), []).append({
            "state": m.group(2), "period": m.group(3) or "", "evidence": m.group(4),
        })
    return rings, chain


def current_state(layer):
    fp = os.path.join(REPORTS, f"state-{layer}.json")
    if not os.path.exists(fp):
        return None
    with io.open(fp, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--layer", default="market", choices=["market", "sector"])
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list:
        rows = sorted(os.path.basename(p) for p in glob.glob(os.path.join(HIST, "*.json")))
        print(f"已归档快照 {len(rows)} 份：")
        for r in rows:
            print("  ", r)
        return 0

    if not a.date:
        ap.error("需要 --date YYYY-MM-DD（或用 --list 查看）")

    snap = load_snapshot(a.date, a.layer)
    old_rings, old_chain = parse_lines(snap.get("body", ""))

    cur = current_state(a.layer)
    if cur:
        cur_body = "\n".join(x.get("raw", "") for x in (cur.get("lines") or []))
        new_rings, new_chain = parse_lines(cur_body)
    else:
        new_rings, new_chain = {}, []

    print(f"复盘对照 · {a.layer} · 当时 {a.date}（归档于 {snap.get('archived_at','—')}）→ 现在")
    print("=" * 78)
    print("\n【当时】")
    for ln in old_chain:
        print("  " + ln)

    changed, same = [], 0
    print("\n【逐环对照】")
    print(f"  {'环':<4}{'当时':<16}{'现在':<16}差异")
    for ring in ("C1", "C2", "C3", "C4", "C5", "C6"):
        o = old_rings.get(ring, [])
        n = new_rings.get(ring, [])
        o_states = [x["state"] for x in o]
        n_states = [x["state"] for x in n]
        note = []
        if o_states != n_states:
            note.append(f"状态词变化：{'/'.join(o_states) or '无'} → {'/'.join(n_states) or '无'}")
        if not n and o:
            note.append("现在无数据（当时有）")
        if n and not o:
            note.append("现在有数据（当时无）")
        # 数值对比
        for oo in o:
            for nn in n:
                if oo["state"] == nn["state"] and oo["evidence"] != nn["evidence"]:
                    note.append(f"{oo['state']} 依据变了")
                    break
        if note:
            changed.append((ring, note))
            print(f"  {ring:<4}{('/'.join(o_states) or '—'):<16}{('/'.join(n_states) or '—'):<16}{'；'.join(note)}")
        else:
            same += 1
            print(f"  {ring:<4}{('/'.join(o_states) or '—'):<16}{('/'.join(n_states) or '—'):<16}无变化")

    print("\n【现在】")
    for ln in new_chain:
        print("  " + ln)

    print(f"\n结论：6 环中 {same} 环无变化，{len(changed)} 环有变化" +
          ("（" + "、".join(r for r, _ in changed) + "）" if changed else "") + "。")
    print("复盘提醒：差异是因为数据更新、还是因为当时链是断的？后者不算判断错。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
