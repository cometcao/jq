#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""触发即刷新：每次调用 skill 时先跑这一支，把数据推到最新交易日再出声。

规则：
- 幂等：同一交易日内，若距上次刷新 < STALE_MIN 分钟，直接跳过（不重复打网络）。
- 失败不断：任一步失败只打印一行，继续后面的步骤（宁可给降级状态，不给空手）。
- 交易日：工作日且已过 15:00 → 当天；否则回退上一工作日。

用法：
    python scripts/refresh.py            # 自动判断要不要刷
    python scripts/refresh.py --force    # 强制全刷
    python scripts/refresh.py --check    # 只看要不要刷，不执行
"""
import argparse
import datetime as dt
import glob
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
STALE_MIN = 20          # 同一交易日内，20 分钟内不重复刷


def trade_day(now=None):
    now = now or dt.datetime.now()
    d = now.date()
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    if d == now.date() and now.hour < 15:
        d -= dt.timedelta(days=1)
        while d.weekday() >= 5:
            d -= dt.timedelta(days=1)
    return d.isoformat()


def last_run():
    """上一次市场层快照的写入时间（state-history 的 mtime）。"""
    fs = glob.glob(os.path.join(ROOT, "reports", "state-history", "*-market.json"))
    if not fs:
        return None, None
    f = max(fs, key=os.path.getmtime)
    as_of = os.path.basename(f)[:10]
    return as_of, dt.datetime.fromtimestamp(os.path.getmtime(f))


def need_refresh(force=False):
    as_of, ts = last_run()
    today_td = trade_day()
    if force:
        return True, f"强制刷新（目标交易日 {today_td}）"
    if as_of != today_td:
        return True, f"快照停在 {as_of or '无'}，目标交易日 {today_td}"
    if ts is None:
        return True, "无快照"
    age = (dt.datetime.now() - ts).total_seconds() / 60
    if age > STALE_MIN:
        return True, f"距上次刷新 {age:.0f} 分钟（阈值 {STALE_MIN}）"
    return False, f"{as_of} 的快照 {age:.0f} 分钟前刚刷过，跳过"


def run(args, label, timeout=300):
    t0 = dt.datetime.now()
    try:
        r = subprocess.run([PY] + args, cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", timeout=timeout)
        ok = r.returncode == 0
        tail = (r.stdout or "").strip().splitlines()
        note = tail[-1][:80] if tail else ("失败" if not ok else "")
        print(f"{'✓' if ok else '✗'} {label:<10}{(dt.datetime.now()-t0).total_seconds():>5.1f}s  {note}")
        return ok
    except subprocess.TimeoutExpired:
        print(f"✗ {label:<10}超时 {timeout}s")
        return False
    except Exception as e:
        print(f"✗ {label:<10}{type(e).__name__}: {str(e)[:60]}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    yes, why = need_refresh(a.force)
    print(f"[刷新判断] {why}")
    if a.check or not yes:
        return 0

    steps = [
        (["scripts/fetch.py"], "抓数"),
        (["scripts/verify_official.py"], "官方对账"),
        (["scripts/history.py"], "历史"),
        (["scripts/events.py", "--days", "30", "--write"], "事件"),
        (["scripts/scenarios.py"], "分支"),
        (["scripts/audit.py", "--daily"], "日检(巡检+台账)"),
        (["scripts/sw_sectors.py", "--meta", "--daily"], "申万板块"),
        (["scripts/sw_sectors.py", "--breadth"], "板块广度"),
        (["scripts/sw_sectors.py", "--margin"], "板块两融"),
        (["scripts/state.py", "--layer", "market", "--write", "--archive", "--json"], "市场层"),
        (["scripts/state.py", "--layer", "sector", "--write", "--archive"], "板块层"),
        (["scripts/sector_dashboard.py"], "板块面板"),
    ]
    # 申万历史回补：官方日线滞后约 6 个交易日，6 天内跑一次就够（全量约 100 秒）
    _stamp = os.path.join(ROOT, "data", "sw", ".last_backfill")
    _need = True
    if os.path.exists(_stamp):
        _age = (dt.datetime.now() - dt.datetime.fromtimestamp(os.path.getmtime(_stamp))).total_seconds() / 86400
        _need = _age >= 6
    if _need:
        steps.append((["scripts/sw_sectors.py", "--backfill", "--limit", "200", "--depth", "250"], "申万历史(6日)"))
        with io.open(_stamp, "w", encoding="utf-8") as _f:
            _f.write(dt.datetime.now().isoformat(timespec="seconds"))

    ok_n = sum(1 for args, label in steps if run(args, label))
    print(f"[刷新完成] {ok_n}/{len(steps)} 步成功（失败步跳过后仍可出声，断点会在状态里标出）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
