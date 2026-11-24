#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""facts 归档迁移：把不该留在 data/facts 的东西移走，**不删除任何记录**。

处理三类（其余原样保留）：
  1. 空目录            → data/facts-archive/empty/<name>/
  2. 目录名不规范      → 先尝试改名成 YYYY-MM-DD；目标已存在或仍不规范则归档到 malformed/
  3. 记录 data_period 与目录不符 → 归档到 period-mismatch/

每次运行写 `data/facts-archive/manifest-<时间戳>.json`，记录动作与理由；可重复执行（幂等）。

用法：
  python -B scripts/migrate_facts.py            # 只看计划（默认 dry-run）
  python -B scripts/migrate_facts.py --apply    # 执行
"""
import io
import os
import re
import sys
import json
import glob
import shutil
import datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACTS = os.path.join(ROOT, "data", "facts")
ARCH = os.path.join(ROOT, "data", "facts-archive")


def backfill_base_values():
    """给缺 base_value 的 facts 补上（幂等）。返回补了多少条。"""
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from units import norm as unorm
    n = 0
    for fp in glob.glob(os.path.join(FACTS, "*", "*.json")):
        try:
            j = json.load(io.open(fp, encoding="utf-8-sig"))
        except Exception:
            continue
        if j.get("base_value") is not None:
            continue
        b, bu, sc = unorm((j.get("current_state") or {}).get("数值"))
        if b is None:
            continue
        j["base_value"], j["base_unit"], j["unit_scale"] = b, bu, sc
        with io.open(fp, "w", encoding="utf-8") as f:
            json.dump(j, f, ensure_ascii=False, indent=2)
        n += 1
    return n


def plan():
    moves = []      # (src, dst, reason)
    renames = []    # (src, dst, reason)
    for d in sorted(glob.glob(os.path.join(FACTS, "*"))):
        if not os.path.isdir(d):
            continue
        name = os.path.basename(d)
        files = glob.glob(os.path.join(d, "*.json"))
        if not files:
            moves.append((d, os.path.join(ARCH, "empty", name), "空目录（无 facts 记录）"))
            continue
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", name):
            fixed = None
            m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", name)
            if m:
                fixed = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            tgt = os.path.join(FACTS, fixed) if fixed else None
            if tgt and not os.path.exists(tgt):
                renames.append((d, tgt, f"目录名不规范 {name} → {fixed}"))
            else:
                moves.append((d, os.path.join(ARCH, "malformed", name), f"目录名不规范且目标已存在：{name}"))
            continue
        bad = []
        for fp in files:
            try:
                j = json.load(io.open(fp, encoding="utf-8-sig"))
            except Exception:
                bad.append(os.path.basename(fp))
                continue
            if j.get("data_period") != name:
                bad.append(os.path.basename(fp))
        if bad:
            moves.append((d, os.path.join(ARCH, "period-mismatch", name),
                          f"{len(bad)} 个记录的 data_period 与目录不符"))
    return moves, renames


def main():
    apply_ = "--apply" in sys.argv
    moves, renames = plan()
    print(f"facts 目录：{len([d for d in glob.glob(os.path.join(FACTS,'*')) if os.path.isdir(d)])} 个")
    print(f"计划：改名 {len(renames)} 个 · 归档 {len(moves)} 个")
    for s, d, why in renames:
        print(f"  改名 {os.path.basename(s)} → {os.path.basename(d)}  ({why})")
    for s, d, why in moves:
        print(f"  归档 {os.path.basename(s)} → {os.path.relpath(d, ROOT)}  ({why})")
    if apply_:
        fixed = backfill_base_values()
        print(f"补 base_value：{fixed} 条")
    if not (moves or renames):
        if not apply_:
            print("无需迁移（只补 base_value 需 --apply）。")
        else:
            print("迁移完成。")
        return 0
    if not apply_:
        print("\n（dry-run）加 --apply 执行。")
        return 0

    os.makedirs(ARCH, exist_ok=True)
    manifest = {"at": dt.datetime.now().isoformat(timespec="seconds"),
                "renamed": [], "archived": []}
    for s, d, why in renames:
        os.rename(s, d)
        manifest["renamed"].append({"from": os.path.relpath(s, ROOT), "to": os.path.relpath(d, ROOT), "reason": why})
    for s, d, why in moves:
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.move(s, d)
        manifest["archived"].append({"from": os.path.relpath(s, ROOT), "to": os.path.relpath(d, ROOT), "reason": why})
    fp = os.path.join(ARCH, f"manifest-{dt.datetime.now():%Y%m%d-%H%M%S}.json")
    with io.open(fp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"\n完成：改名 {len(manifest['renamed'])} · 归档 {len(manifest['archived'])}；manifest → {os.path.relpath(fp, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
