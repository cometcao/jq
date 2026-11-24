#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键自检：把项目所有机械校验串起来跑一遍（改完代码/文字后执行）。

包含：
  1. 三方一致性：registry / fetch SPECS / docs/09
  2. cache 与 facts 漂移
  3. 歧义表述扫描
  4. 回归测试（历史坑断言）
  5. 页面契约 + 两张卡片契约
  6. 依赖与目录卫生（requirements、临时文件、__pycache__）

用法：python -B scripts/selftest.py [-q]
退出码：0 全过；1 有失败。
"""
import io
import os
import re
import sys
import glob
import json
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


def run(args, timeout=300, cwd=None):
    return subprocess.run([PY, "-B"] + args, capture_output=True, text=True,
                          encoding="utf-8", cwd=cwd or ROOT, timeout=timeout)


def main():
    quiet = "-q" in sys.argv
    results = []

    def add(name, ok, detail=""):
        results.append((name, ok, detail))
        if not quiet:
            print(("  ✓ " if ok else "  ✗ ") + name + (f"  [{detail}]" if detail else ""))

    # 1 三方一致
    try:
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import importlib
        import fetch as F
        importlib.reload(F)
        reg = json.load(io.open(os.path.join(ROOT, "dist", "market-state", "references", "registry.json"), encoding="utf-8"))
        spec = {s["id"] for s in F.SPECS}
        add("有取数器的指标都已注册", not (set(spec) - set(reg)), str(sorted(set(spec) - set(reg))[:3]))
        d9 = io.open(os.path.join(ROOT, "docs", "09_指标本体表.md"), encoding="utf-8").read()
        ids9 = set(re.findall(r"^\|\s*([A-Z]{2,6}_[A-Z0-9_]+)\s*\|", d9, re.M))
        add("docs/09 与 registry 一致", ids9 == set(reg), str(sorted(ids9 ^ set(reg))[:3]))
    except Exception as e:
        add("三方一致性", False, f"{type(e).__name__}")

    # 2 一致性
    r = run([os.path.join(ROOT, "scripts", "check_consistency.py")], 180)
    add("cache 与 facts 无漂移", "0 漂移" in (r.stdout or ""), (r.stdout or "").strip()[-60:])

    # 3 歧义
    r = run([os.path.join(ROOT, "scripts", "ambiguity_scan.py")], 180)
    add("歧义扫描 0 处", "0 处歧义" in (r.stdout or ""), (r.stdout or "").strip()[:80])

    # 4 回归
    r = run([os.path.join(ROOT, "scripts", "test_regression.py")], 420)
    tail = (r.stdout or "").strip().splitlines()[-1] if r.stdout else ""
    add("回归测试全过", "0 失败" in tail, tail[-60:])

    # 4b 单元测试 + 数值金标
    r = run([os.path.join(ROOT, "scripts", "test_units.py")], 240)
    tail = (r.stdout or "").strip().splitlines()[-1] if r.stdout else ""
    add("单元测试+金标全过", "0 失败" in tail, tail[-60:])

    # 4c 跳过登记 + 每日 diff
    import glob as _g
    sfs = sorted(_g.glob(os.path.join(ROOT, "data", "skips", "*.jsonl")))
    bad_skip = []
    for fp_ in sfs:
        for line in io.open(fp_, encoding="utf-8").read().splitlines():
            if not line.strip():
                continue
            try:
                r_ = json.loads(line)
            except Exception:
                bad_skip.append(os.path.basename(fp_))
                continue
            if not r_.get("reason") or not r_.get("indicator_id"):
                bad_skip.append(os.path.basename(fp_))
    add("跳过登记表格式合规", not bad_skip, str(bad_skip[:2]))
    r = run([os.path.join(ROOT, "scripts", "daily_diff.py")], 300)
    add("每日 diff 能产出", "# 每日 diff" in (r.stdout or ""), (r.stdout or "").splitlines()[0][:30] if r.stdout else "")

    # 4d 卡片哈希（交付自证：贴出去的内容必须与被校验的文件一致）
    import hashlib as _hl
    hashes = {}
    for name in ("card-market.html", "card-events.html"):
        fp_ = os.path.join(ROOT, "reports", name)
        if os.path.exists(fp_):
            b = io.open(fp_, "rb").read()
            hashes[name] = {"sha256": _hl.sha256(b).hexdigest()[:16], "chars": len(b.decode("utf-8"))}
    if hashes:
        hj = os.path.join(ROOT, "reports", "card-hashes.json")
        io.open(hj, "w", encoding="utf-8").write(json.dumps(hashes, ensure_ascii=False, indent=2))
    add("卡片哈希已记录（交付自证）", len(hashes) == 2, ", ".join(f"{k}:{v['sha256']}" for k, v in hashes.items()))

    # 5 契约
    ck = os.path.join(ROOT, "dist", "market-state", "check.py")
    for label, args in (
        ("页面契约", ["--page", os.path.join(ROOT, "reports", "2026-11-24-market-state.md")]),
        ("状态卡契约", ["--card", os.path.join(ROOT, "reports", "card-market.html")]),
        ("事件卡契约", ["--card", os.path.join(ROOT, "reports", "card-events.html")]),
    ):
        fp = args[1]
        if not os.path.exists(fp):
            add(label, False, "文件不存在")
            continue
        r = run([ck] + args, 120, cwd=os.path.dirname(ck))
        add(label, "0 错误" in (r.stdout or ""), (r.stdout or "").strip()[:80])

    # 6 卫生
    add("requirements.txt 存在", os.path.exists(os.path.join(ROOT, "requirements.txt")))
    tmps = [p for p in glob.glob(os.path.join(ROOT, "tmp_*")) + glob.glob(os.path.join(ROOT, "card_payload*"))]
    add("无临时文件残留", not tmps, str([os.path.basename(p) for p in tmps][:3]))
    pyc = glob.glob(os.path.join(ROOT, "scripts", "__pycache__"))
    add("scripts 无 __pycache__", not pyc)
    # facts 目录规范（空目录/不规范名 → 应被 migrate_facts 归档）
    bad_dirs = []
    for d in glob.glob(os.path.join(ROOT, "data", "facts", "*")):
        if not os.path.isdir(d):
            continue
        nm = os.path.basename(d)
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", nm) or not glob.glob(os.path.join(d, "*.json")):
            bad_dirs.append(nm)
    add("facts 目录规范且非空", not bad_dirs, str(bad_dirs[:3]))

    if "--deep" in sys.argv:
        r = run([os.path.join(ROOT, "scripts", "deep_audit.py")], 900)
        add("深度巡检 0 错误", "0 错误" in (r.stdout or ""), (r.stdout or "").strip().splitlines()[-1][:60])

    bad = [r for r in results if not r[1]]
    print(f"\n自检：{len(results) - len(bad)} 通过 / {len(bad)} 失败（共 {len(results)} 项）")
    if bad:
        for name, _, detail in bad:
            print(f"  ✗ {name}  [{detail}]")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
