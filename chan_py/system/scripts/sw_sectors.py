#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""申万二级板块数据层：124 个板块的面板 + 逐板块历史。

设计：申万提供"一次拿全"的接口，所以不做逐板块抓取。
  - 元数据：index_second_info_sw()  → 代码/名称/一级行业/成份数/PE/PB/股息率
  - 当日面板：index_spot_sw("二级行业") → 124 个板块的价/量/成交额，一次调用
  - 历史：index_hist_sw(code) 逐板块（每个约 1.4 秒，只做一次，之后只追加）

产物：
  data/sw/sectors.json            元数据（板块清单 + 估值快照）
  data/sw/daily/<date>.json       当日面板（124 行）
  data/sw/history/<code>.jsonl    逐板块时间序列

用法：
    python scripts/sw_sectors.py --meta --daily       # 元数据 + 当日面板（约 7 秒）
    python scripts/sw_sectors.py --backfill --limit 40 --offset 0    # 分批回补历史
    python scripts/sw_sectors.py --rank               # 按当日成交额排名
"""
import argparse
import datetime as dt
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SW = os.path.join(ROOT, "data", "sw")
REPORTS_SW = os.path.join(ROOT, "reports", "sector")
HIST = os.path.join(SW, "history")
DAILY = os.path.join(SW, "daily")


def _io(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def load_json(p, default=None):
    try:
        with io.open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(p, obj):
    _io(p)
    tmp = p + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def fetch_meta():
    import akshare as ak
    df = ak.index_second_info_sw()
    rows = []
    for _, r in df.iterrows():
        code = str(r["行业代码"]).split(".")[0]
        rows.append({
            "code": code,
            "name": str(r["行业名称"]),
            "parent": str(r["上级行业"]),
            "n_const": int(r["成份个数"]) if str(r["成份个数"]).replace(".", "").isdigit() else None,
            "pe_static": _num(r["静态市盈率"]),
            "pe_ttm": _num(r["TTM(滚动)市盈率"]),
            "pb": _num(r["市净率"]),
            "div_yield": _num(r["静态股息率"]),
        })
    save_json(os.path.join(SW, "sectors.json"),
              {"generated_at": dt.datetime.now().isoformat(timespec="seconds"),
               "source": "申万宏源·申万指数（akshare index_second_info_sw）",
               "count": len(rows), "sectors": rows})
    return rows


def _num(x):
    try:
        v = float(x)
        return None if v != v else round(v, 4)
    except Exception:
        return None


def fetch_daily():
    import akshare as ak
    df = ak.index_spot_sw(symbol="二级行业")
    meta = {s["code"]: s for s in (load_json(os.path.join(SW, "sectors.json"), {}) or {}).get("sectors", [])}
    rows = []
    for _, r in df.iterrows():
        code = str(r["指数代码"])
        prev = _num(r["昨收盘"])
        last = _num(r["最新价"])
        pct = None if not (prev and last) else round((last / prev - 1) * 100, 2)
        rows.append({
            "code": code,
            "name": str(r["指数名称"]),
            "parent": (meta.get(code) or {}).get("parent"),
            "close": last,
            "prev_close": prev,
            "pct": pct,
            "amount": None if _num(r["成交额"]) is None else round(_num(r["成交额"]) / 100, 2),  # 源单位百万元 → 亿元
            "volume": _num(r["成交量"]),
            "pe_ttm": (meta.get(code) or {}).get("pe_ttm"),
            "pb": (meta.get(code) or {}).get("pb"),
            "div_yield": (meta.get(code) or {}).get("div_yield"),
        })
    day = _trade_day()
    save_json(os.path.join(DAILY, f"{day}.json"),
              {"date": day, "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
               "source": "申万宏源·申万二级行业实时行情（akshare index_spot_sw）+ 估值（index_second_info_sw）",
               "count": len(rows), "sectors": rows})
    return day, rows


def _trade_day():
    now = dt.datetime.now()
    d = now.date()
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    if d == now.date() and now.hour < 15:
        d -= dt.timedelta(days=1)
        while d.weekday() >= 5:
            d -= dt.timedelta(days=1)
    return d.isoformat()


def history_path(code):
    return os.path.join(HIST, f"{code}.jsonl")


def existing_periods(code):
    p = history_path(code)
    if not os.path.exists(p):
        return set()
    out = set()
    with io.open(p, encoding="utf-8") as f:
        next(f, None)
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.add(json.loads(line)["date"])
            except Exception:
                continue
    return out


def backfill(limit=40, offset=0, depth=120):
    import akshare as ak
    sectors = (load_json(os.path.join(SW, "sectors.json"), {}) or {}).get("sectors", [])
    todo = sectors[offset:offset + limit] if limit else sectors[offset:]
    made = 0
    for s in todo:
        code = s["code"]
        try:
            df = ak.index_hist_sw(symbol=code, period="day")
        except Exception as e:
            print(f"  ✗ {code} {s['name']}: {type(e).__name__}")
            continue
        have = existing_periods(code)
        rows = []
        for _, r in df.tail(depth).iterrows():
            d = str(r["日期"])[:10]
            if d in have:
                continue
            rows.append({"date": d, "close": _num(r["收盘"]), "open": _num(r["开盘"]),
                         "high": _num(r["最高"]), "low": _num(r["最低"]),
                         "volume": _num(r["成交量"]), "amount": _num(r["成交额"])})
        if not rows:
            continue
        fp = _io(history_path(code))
        exists = os.path.exists(fp)
        with io.open(fp, "a" if exists else "w", encoding="utf-8") as f:
            if not exists:
                f.write(json.dumps({"indicator_id": "SW_" + code, "name": s["name"],
                                    "unit": "点 / 原始量（成交量）", "source": "申万指数日线（akshare index_hist_sw）"},
                                   ensure_ascii=False) + "\n")
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        made += 1
    print(f"回补完成：{made}/{len(todo)} 个板块（offset {offset}）")
    return made


def rank(top=20, key="amount"):
    day = _trade_day()
    panel = load_json(os.path.join(DAILY, f"{day}.json"), None)
    if not panel:
        cand = sorted(os.listdir(DAILY)) if os.path.isdir(DAILY) else []
        if not cand:
            print("没有当日面板，先跑 --daily")
            return 2
        day = cand[-1][:10]
        panel = load_json(os.path.join(DAILY, f"{day}.json"), {})
    rows = [r for r in panel.get("sectors", []) if r.get(key) is not None]
    rows.sort(key=lambda r: r[key], reverse=True)
    print(f"{day} 申万二级板块 · 按 {key} 前 {top}")
    print(f"{'代码':<8}{'板块':<12}{'涨跌%':>8}{'成交额(亿)':>12}{'PE_TTM':>9}")
    for r in rows[:top]:
        print(f"{r['code']:<8}{r['name'][:10]:<12}{(r['pct'] or 0):>8.2f}{(r['amount'] or 0):>12.0f}"
              f"{(r['pe_ttm'] or 0):>9.1f}")
    return 0


# ---------------------------------------------------------------- 成分表（周更）
def fetch_constituents(limit=40, offset=0):
    import akshare as ak
    fp = os.path.join(SW, "constituents.json")
    cur = load_json(fp, {}) or {}
    got = cur.get("sectors") or {}
    sectors = (load_json(os.path.join(SW, "sectors.json"), {}) or {}).get("sectors", [])
    todo = sectors[offset:offset + limit] if limit else sectors[offset:]
    made = 0
    for s in todo:
        try:
            df = ak.index_component_sw(symbol=s["code"])
        except Exception as e:
            print(f"  ✗ {s['code']} {s['name']}: {type(e).__name__}")
            continue
        codes = [str(c).zfill(6) for c in df["证券代码"].tolist()]
        got[s["code"]] = {"name": s["name"], "codes": codes, "n": len(codes)}
        made += 1
    save_json(fp, {"generated_at": dt.datetime.now().isoformat(timespec="seconds"),
                   "source": "申万宏源·申万二级成分（akshare index_component_sw）",
                   "count": len(got), "sectors": got})
    print(f"成分表：本轮更新 {made} 个，累计 {len(got)} 个")
    return made


# ---------------------------------------------------------------- 板块内广度
def fetch_breadth(force=False):
    """用全市场快照 + 成分表算每个申万二级板块的上涨家数占比（当日已算过则跳过）。"""
    day = _trade_day()
    if not force and os.path.exists(os.path.join(SW, "breadth", f"{day}.json")):
        print(f"板块广度：{day} 已算过，跳过")
        return 0
    import akshare as ak
    cons = (load_json(os.path.join(SW, "constituents.json"), {}) or {}).get("sectors") or {}
    if not cons:
        print("没有成分表，先跑 --constituents")
        return 2
    try:
        spot = ak.stock_zh_a_spot_sina()
    except Exception as e:
        print(f"全市场快照失败：{type(e).__name__}；东财限流时可隔几分钟再试")
        return 3
    px = {}
    for _, r in spot.iterrows():
        code = str(r["代码"])[-6:]
        try:
            px[code] = float(r["涨跌幅"])
        except Exception:
            continue
    day = _trade_day()
    rows = []
    for code, meta in cons.items():
        vals = [px[c] for c in meta.get("codes", []) if c in px and px[c] == px[c]]
        if not vals:
            continue
        up = sum(1 for v in vals if v > 0)
        rows.append({"code": code, "name": meta["name"], "n": len(vals),
                     "up": up, "breadth": round(up / len(vals) * 100, 1)})
    save_json(os.path.join(SW, "breadth", f"{day}.json"),
              {"date": day, "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
               "source": "全市场个股涨跌幅（新浪）+ 申万二级成分表",
               "count": len(rows), "sectors": rows})
    print(f"板块广度：{day} · {len(rows)} 个板块")
    return 0


# ---------------------------------------------------------------- 多板块对比
def board(top=15, sort_key="amount"):
    day = _trade_day()
    panel = load_json(os.path.join(DAILY, f"{day}.json"), None)
    if not panel:
        fs = sorted(os.listdir(DAILY)) if os.path.isdir(DAILY) else []
        if not fs:
            print("没有当日面板")
            return 2
        day = fs[-1][:10]
        panel = load_json(os.path.join(DAILY, f"{day}.json"), {})
    bd = load_json(os.path.join(SW, "breadth", f"{day}.json"), {}) or {}
    bd_map = {x["code"]: x["breadth"] for x in (bd.get("sectors") or [])}
    mkt = None
    try:
        import json as _j
        mp = os.path.join(ROOT, "data", "cache", "MKT_TURNOVER.json")
        mkt = _j.load(io.open(mp, encoding="utf-8"))["current_state"]["数值"]
        mkt = float("".join(ch for ch in str(mkt) if ch.isdigit() or ch == "."))
    except Exception:
        mkt = None

    rows = panel.get("sectors") or []
    for r in rows:
        r["breadth"] = bd_map.get(r["code"])
        r["share"] = (r["amount"] / mkt * 100) if (mkt and r.get("amount")) else None
    rows = [r for r in rows if r.get(sort_key) is not None]
    rows.sort(key=lambda r: r[sort_key], reverse=True)
    out = [f"# 申万二级板块对比 · {day}", "",
           f"共 {len(panel.get('sectors') or [])} 个板块；按 {sort_key} 排序，取前 {top}。", "",
           "| 板块 | 涨跌% | 成交额(亿) | 占全市场% | 上涨家数占比 | PE_TTM |",
           "|---|---|---|---|---|---|"]
    for r in rows[:top]:
        out.append(f"| {r['name']} | {r.get('pct', 0):+.2f} | {(r.get('amount') or 0):.0f} | "
                   f"{(r.get('share') or 0):.2f} | {('—' if r.get('breadth') is None else str(round(r['breadth'])) + '%')} | "
                   f"{(r.get('pe_ttm') or 0):.1f} |")
    fp = os.path.join(REPORTS_SW, f"board-{day}.md")
    os.makedirs(REPORTS_SW, exist_ok=True)
    with io.open(fp, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("\n".join(out))
    print(f"\n已写入 {os.path.relpath(fp, ROOT)}")
    return 0


# ---------------------------------------------------------------- 板块两融（深市官方明细）
def fetch_margin_sz(force=False, max_pages=120):
    """深交所两融明细（per stock）→ data/sw/margin/<date>.json；1 页 20 条，约 106 页。"""
    import requests
    day = _trade_day()
    fp = os.path.join(SW, "margin", f"{day}.json")
    if not force and os.path.exists(fp):
        print(f"板块两融：{day} 已拉过，跳过")
        return 0
    base = "http://www.szse.cn/api/report/ShowReport/data"
    UA = {"User-Agent": "Mozilla/5.0", "Referer": "http://www.szse.cn/"}
    rows, page, total = [], 1, None
    import datetime as _dt
    # T+1：当天没有就回退
    d = _dt.date.fromisoformat(day)
    for _ in range(8):
        if d.weekday() < 5:
            first = None
            try:
                r = requests.get(base, params={"SHOWTYPE": "JSON", "CATALOGID": "1837_xxpl", "TABKEY": "tab2",
                                               "PAGENO": 1, "txtDate": d.isoformat(), "random": "0.3"},
                                 headers=UA, timeout=25)
                j = r.json() or []
                first = (j[0].get("data") or []) if isinstance(j, list) and j else []
                total = ((j[0].get("metadata") or {}).get("pagecount") or 0) if first else 0
            except Exception:
                first = []
            if first:
                rows = list(first)
                pages = min(int(total or 1), max_pages)
                for pg in range(2, pages + 1):
                    try:
                        rr = requests.get(base, params={"SHOWTYPE": "JSON", "CATALOGID": "1837_xxpl",
                                                        "TABKEY": "tab2", "PAGENO": pg,
                                                        "txtDate": d.isoformat(), "random": "0.3"},
                                          headers=UA, timeout=25)
                        jj = rr.json() or []
                        rows += (jj[0].get("data") or []) if isinstance(jj, list) and jj else []
                    except Exception:
                        continue
                out = {}
                for x in rows:
                    code = str(x.get("zqdm") or "").zfill(6)
                    try:
                        bal = float(str(x.get("jrrzye") or 0).replace(",", ""))
                    except Exception:
                        continue
                    if code:
                        out[code] = bal
                save_json(os.path.join(SW, "margin", f"{d.isoformat()}.json"),
                          {"date": d.isoformat(), "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
                           "source": "深交所·融资融券交易明细（ShowReport 1837_xxpl tab2）",
                           "count": len(out), "pages": pages, "fin_bal": out})
                print(f"板块两融：{d.isoformat()} · {len(out)} 只（{pages} 页）")
                return 0
        d -= _dt.timedelta(days=1)
    print("板块两融：近 8 天无数据")
    return 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meta", action="store_true")
    ap.add_argument("--daily", action="store_true")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--depth", type=int, default=120)
    ap.add_argument("--constituents", action="store_true")
    ap.add_argument("--breadth", action="store_true")
    ap.add_argument("--margin", action="store_true")
    ap.add_argument("--board", action="store_true")
    ap.add_argument("--rank", action="store_true")
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args()

    if a.meta:
        rows = fetch_meta()
        print(f"元数据：{len(rows)} 个申万二级板块 → data/sw/sectors.json")
    if a.daily:
        day, rows = fetch_daily()
        print(f"当日面板：{day} · {len(rows)} 个板块 → data/sw/daily/{day}.json")
    if a.backfill:
        backfill(a.limit, a.offset, a.depth)
    if a.constituents:
        fetch_constituents(a.limit, a.offset)
    if a.breadth:
        rc = fetch_breadth()
        if rc:
            return rc
    if a.margin:
        rc = fetch_margin_sz()
        if rc:
            print(f"（板块两融返回 {rc}）")
    if a.board:
        return board(a.top)
    if a.rank:
        return rank(a.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
