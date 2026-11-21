#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多板块观察：按 data/sector_config.json 里的分组，一次算出每个分组的
成交额、占全市场、成交额加权涨跌幅、上涨家数占比，并留历史快照。

为什么要这个脚本：注册表里的指标 id 是固定的（SECTOR_AMT 等只能代表"一个"板块），
而"医药=6 个行业加总"这类分组是**动态口径**。所以多板块观察走这里，
不做成注册指标；正式六环仍用 state.py --layer sector（单一目标板块）。

用法：
    python scripts/sector.py                 # 表格输出
    python scripts/sector.py --json          # JSON 输出
    python scripts/sector.py --write         # 另存 data/sector_groups/<期>.json 并追加修订链
"""
import argparse
import datetime as dt
import glob
import io
import json
import os
import re
import sys
import warnings

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "data", "sector_config.json")
SNAP_DIR = os.path.join(ROOT, "data", "sector_groups")
REVIS_DIR = os.path.join(ROOT, "data", "revisions", "SECTOR_GROUP")

DEFAULT_CONFIG = {
    "note": "同花顺行业分类；members 为该分组包含的行业板块（加总口径）",
    "groups": [
        {"name": "医药", "members": ["中药", "医药商业", "化学制药", "医疗器械", "医疗服务", "生物制品"]},
        {"name": "电力", "members": ["电力"]},
        {"name": "基础化工", "members": ["化学原料", "化学制品", "化学纤维", "橡胶制品", "塑料制品", "农化制品"]},
    ],
}


def load_config():
    if not os.path.exists(CONFIG):
        os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
        with io.open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
            f.write("\n")
    with io.open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


def num(x):
    try:
        return float(x)
    except Exception:
        return 0.0


def latest_trade_day():
    p = os.path.join(ROOT, "data", "cache", "IDX_DAILY.json")
    try:
        with io.open(p, encoding="utf-8") as f:
            return json.load(f).get("data_period") or dt.date.today().isoformat()
    except Exception:
        return dt.date.today().isoformat()


def collect(cfg):
    import akshare as ak

    df = ak.stock_board_industry_summary_ths().copy()
    df["总成交额"] = df["总成交额"].map(num)
    df["涨跌幅"] = df["涨跌幅"].map(num)
    df["上涨家数"] = df["上涨家数"].map(num)
    df["下跌家数"] = df["下跌家数"].map(num)
    df = df.set_index("板块")
    total = float(df["总成交额"].sum())

    out = []
    for g in cfg.get("groups", []):
        members = [m for m in g.get("members", []) if m in df.index]
        missing = [m for m in g.get("members", []) if m not in df.index]
        sub = df.loc[members]
        amt = float(sub["总成交额"].sum())
        up, down = float(sub["上涨家数"].sum()), float(sub["下跌家数"].sum())
        pct = float((sub["涨跌幅"] * sub["总成交额"]).sum() / amt) if amt else 0.0
        out.append({
            "group": g["name"], "members": members, "missing_members": missing,
            "n_members": len(members), "amount_yi": round(amt, 2),
            "share_pct": round(amt / total * 100, 2) if total else 0.0,
            "pct_weighted": round(pct, 2),
            "up": int(up), "down": int(down),
            "breadth_pct": round(up / (up + down) * 100, 1) if (up + down) else None,
        })
    return out, round(total, 2)


def append_history(as_of, rows):
    os.makedirs(REVIS_DIR, exist_ok=True)
    os.makedirs(SNAP_DIR, exist_ok=True)
    with io.open(os.path.join(SNAP_DIR, as_of + ".json"), "w", encoding="utf-8") as f:
        json.dump({"as_of": as_of, "groups": rows}, f, ensure_ascii=False, indent=2)
    for r in rows:
        fp = os.path.join(REVIS_DIR, re.sub(r"[^\w\-]", "_", r["group"]) + ".jsonl")
        seq = 0
        if os.path.exists(fp):
            seq = len([l for l in io.open(fp, encoding="utf-8").read().splitlines() if l.strip()])
        entry = {"revision_seq": seq, "group": r["group"], "data_period": as_of,
                 "amount_yi": r["amount_yi"], "share_pct": r["share_pct"],
                 "pct_weighted": r["pct_weighted"], "breadth_pct": r["breadth_pct"],
                 "observed_at": dt.datetime.now().isoformat(timespec="seconds")}
        with io.open(fp, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    cfg = load_config()
    rows, total = collect(cfg)
    as_of = latest_trade_day()

    if a.write:
        append_history(as_of, rows)

    if a.json:
        print(json.dumps({"as_of": as_of, "market_total_yi": total, "groups": rows},
                         ensure_ascii=False, indent=2))
        return 0

    print(f"as-of {as_of}（同花顺行业分类；全市场 {total:.2f} 亿；涨跌幅按成交额加权）")
    print(f"{'分组':<12}{'板块数':>5}{'成交额(亿)':>12}{'占全市场':>9}{'加权涨跌':>10}{'上涨占比':>9}")
    print("-" * 62)
    for r in rows:
        b = f"{r['breadth_pct']:.1f}%" if r["breadth_pct"] is not None else "—"
        print(f"{r['group']:<12}{r['n_members']:>5}{r['amount_yi']:>12.2f}{r['share_pct']:>8.2f}%{r['pct_weighted']:>9.2f}%{b:>9}")
        if r["missing_members"]:
            print(f"{'':<12}⚠ 配置里的板块名未找到：{r['missing_members']}")
    print("-" * 62)
    print("成员口径见 data/sector_config.json；历史见 data/sector_groups/ 与 data/revisions/SECTOR_GROUP/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
