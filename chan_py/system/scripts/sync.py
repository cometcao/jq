#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次运行 = 补齐最近缺少的数据 + 重新生成状态。

顺序（与 SKILL 的数据来源优先级一致）：
   1. fetch.py           抓最新快照（走缓存，6h 内不重复请求）
   2. history.py         历史序列**增量**合并（只补缺的期，不重写）
   3. events.py          官方发布日程（未来 N 天）
   4. state.py           市场层 + 板块层（写 reports/ 与 reports/state-*.json）

失败不阻断：某一步失败只记一行，后续步骤照跑（落盘数据仍可用）。

用法：
    python scripts/sync.py                 # 全流程
    python scripts/sync.py --no-events     # 跳过事件
    python scripts/sync.py --days 30
"""
import argparse
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


def run(script, args=(), label=""):
    t0 = time.time()
    r = subprocess.run([PY, os.path.join(ROOT, "scripts", script), *args],
                       capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    ok = r.returncode == 0
    out = (r.stdout or "").strip().splitlines()
    tail = out[-1] if out else (r.stderr or "").strip().splitlines()[-1][:80] if r.stderr else ""
    print(f"{'✓' if ok else '✗'} {label or script:<12} {time.time()-t0:5.1f}s  {tail[:90]}")
    return ok, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--no-events", action="store_true")
    ap.add_argument("--no-history", action="store_true")
    a = ap.parse_args()

    results = []
    results.append(run("fetch.py", (), "抓数"))
    if not a.no_history:
        results.append(run("history.py", (), "历史序列"))
    if not a.no_events:
        results.append(run("events.py", ["--days", str(a.days), "--write"], "事件日历"))
    results.append(run("state.py", ["--layer", "market", "--json", "--write"], "市场层"))
    results.append(run("state.py", ["--layer", "sector", "--json", "--write"], "板块层"))

    bad = [i for i, (ok, _) in enumerate(results) if not ok]
    print(f"\n完成 {len(results)-len(bad)}/{len(results)} 步" + (f"（失败 {len(bad)} 步，其余可用）" if bad else ""))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
