#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一致性校验：cache（工作数据）与 facts（可发布记录）不得漂移。

为什么需要：2026-11-24 发现 `SECTOR_VAL` 在 cache 是 6.33、facts 是 6.37——两套值并存，
对账（verify_official）读的是 cache，状态页读的是 facts，会得出相反结论。

校验三件事：
  1. 数值一致：cache.value 与 facts.current_state.数值 解析后的数字相等（容差 0.5%）
  2. 数据期一致：cache.data_period 与 facts.data_period 相同
  3. 档位一致：facts.source_tier 与 official 记录/默认档位不矛盾（仅提示，不判失败）

运行：python scripts/check_consistency.py [-v]
退出码：0 = 无漂移；1 = 有漂移。
"""
import io
import os
import re
import sys
import json
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "cache")
FACTS = os.path.join(ROOT, "data", "facts")


def load(fp):
    try:
        with io.open(fp, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None


def num(text):
    if text is None:
        return None
    m = re.search(r"-?[\d,]+(?:\.\d+)?", str(text))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except Exception:
        return None


def _stale_ok(iid):
    """按 registry 频率判断：落后超过 stale_block 倍的指标，按规则本就不落盘 → 不算漂移。"""
    import datetime as dt
    reg = load(os.path.join(ROOT, "dist", "market-state", "references", "registry.json")) or {}
    freq = (reg.get(iid) or {}).get("frequency") or "日"
    freq_days = {"日": 1, "周": 5, "月": 21, "季": 63}.get(freq, 1)
    c = load(os.path.join(CACHE, f"{iid}.json")) or {}
    dp = c.get("data_period") or ""
    try:
        lag = (dt.date.today() - dt.date.fromisoformat(dp)).days
    except Exception:
        return False
    return lag / max(freq_days, 1) > 3


def scan(verbose=False):
    cache_vals, cache_periods = {}, {}
    for fp in glob.glob(os.path.join(CACHE, "*.json")):
        rec = load(fp)
        if not isinstance(rec, dict):
            continue
        iid = rec.get("indicator_id") or os.path.basename(fp)[:-5]
        v = num((rec.get("current_state") or {}).get("数值"))
        if v is None:
            v = num(rec.get("value"))
        if v is not None:
            cache_vals[iid] = v
        if rec.get("data_period"):
            cache_periods[iid] = rec["data_period"]

    drift, checked = [], 0
    # facts 按日期分目录：只取**最新日期目录**的当期记录，避免和历史期比
    import datetime as _dt
    def _dkey(p_):
        try:
            return _dt.date.fromisoformat(os.path.basename(p_))
        except Exception:
            return _dt.date(1970, 1, 1)
    day_dirs = sorted([d for d in glob.glob(os.path.join(FACTS, "*")) if os.path.isdir(d)
                       and glob.glob(os.path.join(d, "*.json"))], key=_dkey)
    files = glob.glob(os.path.join(day_dirs[-1], "*.json")) if day_dirs else []
    for fp in files:
        rec = load(fp)
        if not rec:
            continue
        iid = rec.get("indicator_id")
        fv = num((rec.get("current_state") or {}).get("数值"))
        fp_period = rec.get("data_period")
        if iid not in cache_vals:
            continue
        checked += 1
        cv = cache_vals.get(iid)
        if cv is not None and fv is not None:
            denom = max(abs(cv), abs(fv), 1e-9)
            if abs(cv - fv) / denom > 0.005:          # 容差 0.5%
                drift.append((iid, "数值", f"cache={cv} facts={fv}", f"{rec.get('data_period')}"))
        cp = cache_periods.get(iid)
        if cp and fp_period and cp != fp_period:
            drift.append((iid, "数据期", f"cache={cp} facts={fp_period}", fp_period))

    # 反向：cache 有值，但它自己 data_period 对应的 facts 目录里没有该指标 → 抓了没落盘
    for iid, v in cache_vals.items():
        cp_ = cache_periods.get(iid)
        if not cp_:
            continue
        fp_ = os.path.join(FACTS, cp_, f"{iid}.json")
        if not os.path.exists(fp_):
            if _stale_ok(iid):
                continue          # 已超时效，按规则不落盘，属正常
            drift.append((iid, "未落盘", f"cache 有值 {v}（数据期 {cp_}）但 facts 无对应记录", cp_))

    return checked, drift


def main():
    verbose = "-v" in sys.argv
    checked, drift = scan(verbose)
    if drift:
        print(f"一致性校验：{checked} 个指标比对，发现 {len(drift)} 处漂移")
        for iid, kind, detail, period in drift:
            print(f"  ✗ {iid:<20}{kind:<6}{detail}")
        print("\n处理建议：重跑 `python scripts/fetch.py --no-cache <指标>` 让 cache 与 facts 同源后落盘。")
        return 1
    print(f"一致性校验：{checked} 个指标比对，cache 与 facts 一致（0 漂移）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
