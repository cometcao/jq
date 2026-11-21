#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""历史序列回补：为六环各自的"代表序列"补 N 期历史，供折线图使用。

为什么单开脚本：快照（data/facts）只存最新一期，修订链（data/revisions）记的是
"同一数据期被重跑过几次"，**不是历史**。折线需要真正的多期序列，所以要单独回补。

规则约束（render 契约）：
- 只回补六环的**判据字段**（不是随便挑指标）；
- 禁 price 序列（IDX_DAILY 之类不进来）；
- 每条序列必须能绑定一条证据行；
- 一页最多一张图。

产物：data/history/<indicator_id>.jsonl，每行 {data_period, value, unit}
"""
import argparse
import datetime as dt
import io
import json
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "history")


FULL = False


def write_series(iid, rows, unit, note="", full=None):
    """增量合并：已有数据期保留，新抓到的期补进去（full=True 才重写）。"""
    os.makedirs(OUT, exist_ok=True)
    fp = os.path.join(OUT, iid + ".jsonl")
    seen = {}
    if not (FULL if full is None else full) and os.path.exists(fp):
        for line in io.open(fp, encoding="utf-8").read().splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if "data_period" in obj and obj.get("value") is not None:
                seen[obj["data_period"]] = obj["value"]
    for p, v in rows:
        if p and v is not None:
            seen[p] = v
    with io.open(fp, "w", encoding="utf-8") as f:
        f.write(json.dumps({"indicator_id": iid, "unit": unit, "note": note,
                            "generated_at": dt.datetime.now().isoformat(timespec="seconds")},
                           ensure_ascii=False) + "\n")
        for p in sorted(seen):
            f.write(json.dumps({"data_period": p, "value": seen[p]}, ensure_ascii=False) + "\n")
    return len(seen)


def backfill_lpr(n):
    import akshare as ak
    df = ak.interest_rate_lpr_em()
    d = df.dropna(subset=["1年期LPR"]).copy()
    d["日期"] = d["日期"].astype(str).str[:10]
    rows = [(r["日期"], float(r["1年期LPR"])) for _, r in d.tail(n).iterrows()]
    return write_series("POL_LPR", rows, "%", "1 年期 LPR（月频报价）")


def backfill_m2(n):
    import akshare as ak
    df = ak.macro_china_money_supply_em()
    col = [c for c in df.columns if "M2" in c and "同比增长" in c][0]
    rows = []
    for _, r in df.head(n).iterrows():
        m = "".join(ch for ch in str(r["月份"]) if ch.isdigit())
        rows.append((f"{m[:4]}-{m[4:6]}-01", float(r[col])))
    return write_series("MKT_M2_YOY", sorted(rows), "%", "M2 同比（月频）")


def backfill_dr007(months=2):
    import akshare as ak
    rows = []
    today = dt.date.today()
    for i in range(months, 0, -1):
        end = (today.replace(day=1) - dt.timedelta(days=1)) if i > 1 else today
        start = (end.replace(day=1) - dt.timedelta(days=25))
        try:
            df = ak.interest_rate_repo_hist_cm(start_date=start.strftime("%Y%m%d"),
                                               end_date=end.strftime("%Y%m%d"))
        except Exception:
            continue
        for _, r in df.iterrows():
            rows.append((str(r["date"])[:10], float(r["FDR007"])))
        time.sleep(1)
    return write_series("MKT_DR007", sorted(rows), "%", "FDR007（DR007 定盘代理，日频）")


def backfill_margin(n):
    import akshare as ak
    df = ak.stock_margin_account_info().copy()
    df = df.dropna(subset=["融资余额"]).sort_values("日期").tail(n)
    rows = [(str(r["日期"])[:10], float(r["融资余额"])) for _, r in df.iterrows()]
    return write_series("MKT_MARGIN_BAL", rows, "亿元", "融资余额（全市场，日频）")


def backfill_margin_inv(n):
    import akshare as ak
    df = ak.stock_margin_account_info().copy()
    df = df.dropna(subset=["个人投资者数量"]).sort_values("日期").tail(n)
    rows = [(str(r["日期"])[:10], float(r["个人投资者数量"])) for _, r in df.iterrows()]
    return write_series("RTL_MARGIN_INVESTORS", rows, "万户", "两融个人投资者数（日频）")


def backfill_turnover(n):
    """全市场成交额历史：用沪深两市指数成交额加总（口径：沪+深指数成交额，非全口径）。"""
    import akshare as ak
    out = {}
    start = (dt.date.today() - dt.timedelta(days=120)).strftime("%Y%m%d")
    end = dt.date.today().strftime("%Y%m%d")
    for sym in ("sh000001", "sz399001"):
        df = ak.index_zh_daily_tx(symbol=sym, start_date=start, end_date=end)
        for _, r in df.tail(n).iterrows():
            out.setdefault(str(r["date"])[:10], 0.0)
            out[str(r["date"])[:10]] += float(r["amount"]) / 1e8
    rows = sorted(out.items())
    return write_series("MKT_TURNOVER", rows[-n:], "亿元", "沪指+深成指成交额合计（口径窄于全市场）")


TASKS = {
    "C1": ("POL_LPR", backfill_lpr, 24),
    "C2": ("MKT_M2_YOY", backfill_m2, 24),
    "C3": ("MKT_DR007", backfill_dr007, 0),
    "C4": ("MKT_MARGIN_BAL", backfill_margin, 60),
    "C5": ("RTL_MARGIN_INVESTORS", backfill_margin_inv, 60),
    "C6": ("MKT_TURNOVER", backfill_turnover, 60),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rings", default="C1,C2,C3,C4,C5,C6")
    ap.add_argument("--full", action="store_true", help="重写而非增量合并")
    global FULL
    a = ap.parse_args()
    for ring in a.rings.split(","):
        ring = ring.strip()
        if ring not in TASKS:
            continue
        iid, fn, n = TASKS[ring]
        try:
            cnt = fn(n) if n else fn()
            print(f"{ring} {iid:<22} 现有 {cnt} 期")
        except Exception as e:
            print(f"{ring} {iid:<22} 失败：{type(e).__name__}: {str(e)[:70]}")
    print("产物:", os.path.relpath(OUT, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
