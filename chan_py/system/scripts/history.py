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
import glob
import re
import sys
import time
import warnings

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "history")


FULL = False


def _dp_of(raw):
    """把各种月份写法统一成 YYYY-MM-01（'2026.4' / '2026年4月' / '202604' 都可以）。

    旧写法用"只保留数字"再取前 6 位，单数字月份（1-9 月）会变成 5 位被整段丢弃——
    实测 243 期用电量只写进 25 期，2026-01~08 全缺。
    """
    import importlib
    _f = importlib.import_module("fetch")
    return _f.norm_period(raw)


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
            f.write(json.dumps({"data_period": p, "value": seen[p], "base_value": seen[p]}, ensure_ascii=False) + "\n")
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
        m = _dp_of(r["月份"])
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



def backfill_loan_yoy(n=24):
    """人民币贷款余额同比：取「累计人民币贷款-同比」列（与指标口径一致，值形如 4.70%）。"""
    import akshare as ak
    df = ak.macro_china_rmb_loan_ths()
    col = "累计人民币贷款-同比"
    if col not in df.columns:
        raise ValueError(f"缺列：{col}")
    rows = []
    for _, r in df.iterrows():
        mm = _dp_of(r["月份"])
        v = str(r[col]).replace("%", "").strip()
        if len(mm) >= 6 and v not in ("", "nan"):
            rows.append((mm, float(v)))
    return write_series("MKT_RMB_LOAN_YOY", sorted(rows)[-n:], "%", "人民币贷款余额同比（月频）")


def backfill_collateral(n=60):
    import akshare as ak
    df = ak.stock_margin_account_info().copy()
    col = [c for c in df.columns if "担保" in str(c)]
    if not col:
        raise ValueError(f"列不符：{list(df.columns)}")
    df = df.dropna(subset=[col[0]]).sort_values("日期").tail(n)
    rows = [(str(r["日期"])[:10], float(r[col[0]])) for _, r in df.iterrows()]
    return write_series("MKT_MARGIN_COLLATERAL", rows, "亿元", "两融担保物总价值（日频）")



def _macro_series(iid, fn, month_col, val_col, n=24, unit="%"):
    import akshare as ak
    df = fn()
    rows = []
    for _, r in df.head(n * 2).iterrows():
        mm = _dp_of(r[month_col])
        v = str(r[val_col]).replace("%", "").strip()
        if len(mm) >= 6 and v not in ("", "nan"):
            rows.append((mm, float(v)))
    return write_series(iid, sorted(rows)[-n:], unit, "")


def backfill_cpi(n=24):
    import akshare as ak
    return _macro_series("MKT_CPI_YOY", ak.macro_china_cpi, "月份", "全国-同比增长", n)


def backfill_ppi(n=24):
    import akshare as ak
    return _macro_series("MKT_PPI_YOY", ak.macro_china_ppi, "月份", "当月同比增长", n)


def backfill_pmi(n=24):
    import akshare as ak
    return _macro_series("MKT_PMI", ak.macro_china_pmi, "月份", "制造业-指数", n, unit="")


def backfill_gdp(n=12):
    import akshare as ak
    df = ak.macro_china_gdp()
    rows = []
    for _, r in df.head(n * 2).iterrows():
        q = str(r["季度"]); ys = re.findall(r"\d+", q)
        if not ys:
            continue
        y = ys[0]
        per = (f"{y}-12-31" if ("1-4" in q or "全年" in q) else
               f"{y}-09-30" if "1-3" in q else
               f"{y}-06-30" if "1-2" in q else f"{y}-03-31")
        rows.append((per, float(r["国内生产总值-同比增长"])))
    return write_series("MKT_GDP_YOY", sorted(rows)[-n:], "%", "GDP 同比（季频）")


def _bf(iid, fn, month_col, val_col, n=24, unit="%"):
    import akshare as ak
    df = fn()
    rows = []
    for _, r in df.iterrows():
        mm = _dp_of(r[month_col])
        v = str(r[val_col]).replace("%", "").strip()
        if len(mm) >= 6 and v not in ("", "nan"):
            rows.append((mm, float(v)))
    rows = sorted(rows)[-n:]
    return write_series(iid, rows, unit, "")


def backfill_ip(n=24):
    import akshare as ak; return _bf("MKT_IP_YOY", ak.macro_china_industrial_value_added, "月份", "同比增长", n)


def backfill_retail(n=24):
    import akshare as ak; return _bf("MKT_RETAIL_YOY", ak.macro_china_consumer_goods_retail, "月份", "同比增长", n)


def backfill_fai(n=24):
    import akshare as ak; return _bf("MKT_FAI_YOY", ak.macro_china_fixed_asset_investment, "月份", "同比增长", n)


def backfill_elec(n=300):
    import akshare as ak
    df = ak.macro_china_society_electricity()
    rows = []
    for _, r in df.iterrows():
        mm = _dp_of(r["统计时间"])
        v = str(r["全社会用电量同比"]).strip()
        if len(mm) >= 6 and v not in ("", "nan"):
            rows.append((mm, float(v)))
    return write_series("MKT_ELEC_YOY", sorted(rows)[-n:], "%", "全社会用电量同比（月频）")


def backfill_house(n=24):
    import akshare as ak
    df = ak.macro_china_new_house_price()
    rows = []
    for d, g in df.groupby("日期"):
        try:
            v = float(g["新建商品住宅价格指数-同比"].astype(float).mean())
        except Exception:
            continue
        rows.append((str(d)[:7] + "-01", v - 100 if v > 50 else v))
    return write_series("MKT_HOUSE_PRICE_YOY", sorted(rows)[-n:], "%", "70 城新建商品住宅价格指数同比均值")

EXTRA_TASKS = [("MKT_RMB_LOAN_YOY", backfill_loan_yoy), ("MKT_MARGIN_COLLATERAL", backfill_collateral),
               ("MKT_CPI_YOY", backfill_cpi), ("MKT_PPI_YOY", backfill_ppi),
               ("MKT_PMI", backfill_pmi), ("MKT_GDP_YOY", backfill_gdp),
               ("MKT_IP_YOY", backfill_ip), ("MKT_RETAIL_YOY", backfill_retail),
               ("MKT_FAI_YOY", backfill_fai), ("MKT_ELEC_YOY", backfill_elec),
               ("MKT_HOUSE_PRICE_YOY", backfill_house)]

TASKS = {
    "C1": ("POL_LPR", backfill_lpr, 24),
    "C2": ("MKT_M2_YOY", backfill_m2, 24),
    "C3": ("MKT_DR007", backfill_dr007, 0),
    "C4": ("MKT_MARGIN_BAL", backfill_margin, 60),
    "C5": ("RTL_MARGIN_INVESTORS", backfill_margin_inv, 60),
    "C6": ("MKT_TURNOVER", backfill_turnover, 60),
}


def append_from_facts(iid):
    """把 facts 目录里该指标的**全部**记录追加进 history（幂等，按 data_period 去重）。

    用于没有历史接口、只能逐日累积的指标（深市两融明细、中债收益率曲线、中基协月度）。
    """
    fp = os.path.join(OUT, f"{iid}.jsonl")
    rows = []
    if os.path.exists(fp):
        for x in io.open(fp, encoding="utf-8").read().splitlines():
            if not x.strip():
                continue
            try:
                r0 = json.loads(x)
            except Exception:
                continue
            if r0.get("data_period") and r0.get("value") is not None:
                rows.append(r0)
    have = {r["data_period"] for r in rows}
    added = 0
    for f in glob.glob(os.path.join(ROOT, "data", "facts", "*", f"{iid}.json")):
        try:
            rec = json.load(io.open(f, encoding="utf-8"))
        except Exception:
            continue
        dp = rec.get("data_period")
        raw = str((rec.get("current_state") or {}).get("数值") or "")
        m = re.search(r"-?[\d,]+(?:\.\d+)?", raw)
        if not dp or not m or dp in have:
            continue
        try:
            val = float(m.group(0).replace(",", ""))
        except Exception:
            continue
        _bv = rec.get("base_value")
        _row = {"data_period": dp, "value": val}
        if isinstance(_bv, (int, float)):
            _row["base_value"] = _bv
        rows.append(_row)
        have.add(dp)
        added += 1
    rows.sort(key=lambda r: r["data_period"])
    with io.open(fp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)



def backfill_margin_sz(days=15):
    """深市两融官方汇总（ShowReport 1837_xxpl tab1）逐日回补：最近 N 个自然日。"""
    import datetime as dt
    import requests
    fp = os.path.join(OUT, "MKT_MARGIN_BAL_SZ.jsonl")
    rows = []
    if os.path.exists(fp):
        rows = [json.loads(x) for x in io.open(fp, encoding="utf-8").read().splitlines() if x.strip()]
    have = {r["data_period"] for r in rows}
    d = dt.date.today()
    added = 0
    for _ in range(days):
        if d.weekday() < 5 and d.isoformat() not in have:
            try:
                r = requests.get("http://www.szse.cn/api/report/ShowReport/data",
                                 params={"SHOWTYPE": "JSON", "CATALOGID": "1837_xxpl", "TABKEY": "tab1",
                                         "PAGENO": 1, "txtDate": d.isoformat(), "random": "0.4"},
                                 headers={"User-Agent": "Mozilla/5.0", "Referer": "http://www.szse.cn/"},
                                 timeout=20)
                j = r.json() or []
                data = (j[0].get("data") or []) if isinstance(j, list) and j else []
                if len(data) == 1:
                    v = float(str(data[0].get("jrrzye") or 0).replace(",", ""))
                    if 100 < v < 100000:
                        rows.append({"data_period": d.isoformat(), "value": v})
                        added += 1
            except Exception:
                pass
        d -= dt.timedelta(days=1)
    rows.sort(key=lambda r: r["data_period"])
    with io.open(fp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def backfill_mmf(max_months=18):
    """货币基金规模：从中基协官方月报回补（月频，走 fetch 的 PDF 解析器）。"""
    import sys as _sys
    _sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import fetch as _F
    import requests as _rq
    fp = os.path.join(OUT, "MKT_MMF_SCALE.jsonl")
    rows = []
    if os.path.exists(fp):
        rows = [json.loads(x) for x in io.open(fp, encoding="utf-8").read().splitlines() if x.strip()]
    have = {r["data_period"] for r in rows}
    added = 0
    for month, url in _F.amac_mmf_list()[:max_months]:
        key = f"{month}-01"
        if key in have:
            continue
        try:
            txt = _F._pdf_text(_rq.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=40, verify=False).content)
            v = _F.amac_mmf_net(txt)
            if v:
                rows.append({"data_period": key, "value": round(v / 1e4, 4), "base_value": round(v, 2)})
                added += 1
        except Exception:
            continue
    rows.sort(key=lambda r: r["data_period"])
    with io.open(fp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def backfill_turnover_official(days=20):
    """MKT_TURNOVER 用交易所官方口径重建最近 N 个交易日（沪+深股票成交额）。

    2026-11-24：此前 history 来自同花顺指数/板块加总、facts 来自快照，
    同一天出现两个数（11-23：15528.80 vs 15639.61）。统一为交易所官方。
    """
    import sys as _sys
    _sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import fetch as _F
    import datetime as _dt
    fp = os.path.join(OUT, "MKT_TURNOVER.jsonl")
    rows = []
    if os.path.exists(fp):
        for x in io.open(fp, encoding="utf-8").read().splitlines():
            if not x.strip():
                continue
            try:
                r0 = json.loads(x)
            except Exception:
                continue
            if r0.get("data_period") and r0.get("value") is not None:
                rows.append(r0)
    by = {r["data_period"]: r for r in rows}
    # 最近 N 个工作日（不判节假日，失败即跳过）
    day = _dt.date.fromisoformat(_F._trade_day_of())
    tried = got = 0
    for _ in range(days * 2):
        if tried >= days:
            break
        if day.weekday() < 5:
            tried += 1
            ds = day.isoformat()
            try:
                v = _F.p_turnover_official_date(ds)
                if v and v > 0:
                    by[ds] = {"data_period": ds, "value": round(v, 2), "base_value": round(v, 2)}
                    got += 1
            except Exception:
                pass
        day -= _dt.timedelta(days=1)
    out = [by[k] for k in sorted(by)]
    with io.open(fp, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(out)


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
    for iid, fn in list(EXTRA_TASKS) + [("MKT_MARGIN_BAL_SZ", lambda: backfill_margin_sz()), ("MKT_MMF_SCALE", lambda: backfill_mmf()), ("MKT_TURNOVER", lambda: backfill_turnover_official()), ("MKT_CGB10Y", lambda: append_from_facts("MKT_CGB10Y"))]:
        try:
            cnt = fn()
            print(f"   {iid:<24} 现有 {cnt} 期")
        except Exception as e:
            print(f"   {iid:<24} 失败：{type(e).__name__}: {str(e)[:60]}")
    print("产物:", os.path.relpath(OUT, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
