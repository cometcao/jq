#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""官方抽样核对：对「直连官方域名」的指标，绕开 akshare 自己取一次官方数据，

与 data/cache 里的值比对；一致则写入 data/official/<id>.json（该指标升 B）。

当前纳入核对的 3 项（data/provenance.json 中 direct_official=true）：
    MKT_DR007      拆借中心 FrrHis 接口
    FX_CNY_MID     外管局 RMBQuery.do
    MKT_DIV_YIELD  中证指数 000300 估值 xls

用法：
    python scripts/verify_official.py            # 核对并落盘
    python scripts/verify_official.py --dry      # 只看结果不写
"""
import argparse
import datetime as dt
import io
import json
import os
import re
import sys

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "cache")
OFFICIAL = os.path.join(ROOT, "data", "official")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/108.0 Safari/537.36"}


def cached(iid):
    p = os.path.join(CACHE, iid + ".json")
    if not os.path.exists(p):
        return None
    with io.open(p, encoding="utf-8") as f:
        return json.load(f)


def num(s):
    m = re.search(r"[-+]?\d+(?:\.\d+)?", str(s).replace(",", ""))
    return float(m.group(0)) if m else None


# ---------------------------------------------------------------- 三个官方源
def official_dr007(date):
    """拆借中心：回购定盘利率历史（FDR007 = DR007 定盘）。"""
    d = dt.date.fromisoformat(date)
    start = (d - dt.timedelta(days=20)).isoformat()
    r = requests.post("https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/FrrHis",
                      params={"lang": "CN", "startDate": start, "endDate": date},
                      headers=UA, timeout=20)
    recs = r.json().get("records", [])
    for rec in recs:
        m = rec.get("frValueMap") or {}
        if str(m.get("date", ""))[:10] == date:
            return float(m["FDR007"]), "https://www.chinamoney.com.cn/chinese/bkfrr/"
    return None, "https://www.chinamoney.com.cn/chinese/bkfrr/"


def official_fx(date):
    """外管局：人民币汇率中间价（美元，按 100 美元标价）。"""
    r = requests.post("https://www.safe.gov.cn/AppStructured/hlw/RMBQuery.do",
                      data={"startDate": date, "endDate": date, "queryYN": "true"},
                      headers=UA, timeout=20)
    r.encoding = "utf8"
    tables = pd.read_html(io.StringIO(r.text))
    df = tables[-1]
    df.columns = [str(c) for c in df.columns]
    row = df[df.iloc[:, 0].astype(str).str[:10] == date]
    if row.empty:
        return None, "https://www.safe.gov.cn/safe/rmbhlzjj/index.html"
    col = [c for c in df.columns if "美元" in c][0]
    return float(row.iloc[0][col]) / 100.0, "https://www.safe.gov.cn/safe/rmbhlzjj/index.html"


def official_csindex(date, symbol="000300"):
    """中证指数：指数估值 xls（含股息率）。"""
    url = (f"https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/"
           f"autofile/indicator/{symbol}indicator.xls")
    df = pd.read_excel(io.BytesIO(requests.get(url, headers=UA, timeout=30).content))
    df.columns = ["日期", "指数代码", "指数中文全称", "指数中文简称", "指数英文全称",
                  "指数英文简称", "市盈率1", "市盈率2", "股息率1", "股息率2"]
    df["日期"] = pd.to_datetime(df["日期"].astype(str), format="%Y%m%d", errors="coerce").dt.date
    row = df[df["日期"].astype(str) == date]
    if row.empty:
        return None, "https://www.csindex.com.cn/", date      # 官方表里没有当期 → 不核对
    return float(row.iloc[-1]["股息率1"]), "https://www.csindex.com.cn/", date


CHECKS = {
    "MKT_DR007": official_dr007,
    "FX_CNY_MID": official_fx,
    "MKT_DIV_YIELD": official_csindex,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    print(f"{'指标':<16}{'缓存值':>12}{'官方值':>12}  结论")
    print("-" * 62)
    ok = 0
    for iid, fn in CHECKS.items():
        c = cached(iid)
        if not c:
            print(f"{iid:<16}{'无缓存':>12}{'':>12}  跳过")
            continue
        mine = num(c.get("current_state", {}).get("数值"))
        period = c.get("data_period")
        try:
            got = fn(period)
            official, url = got[0], got[1]
            used_period = got[2] if len(got) > 2 else period
        except Exception as e:
            print(f"{iid:<16}{mine!s:>12}{'取数失败':>12}  {type(e).__name__}: {str(e)[:40]}")
            continue
        if official is None:
            print(f"{iid:<16}{mine!s:>12}{'无当期值':>12}  未核对")
            continue
        same = abs(mine - official) <= max(abs(official) * 1e-6, 1e-9)
        print(f"{iid:<16}{mine:>12.4f}{official:>12.4f}  {'一致 → 可升 B' if same else '不一致 → 保持 C'}")
        if same and not a.dry:
            os.makedirs(OFFICIAL, exist_ok=True)
            payload = {"value": f"{official}", "unit": "as-recorded", "data_period": used_period,
                       "source_url": url, "checked_at": dt.date.today().isoformat(),
                       "method": "官方接口直取后与缓存值逐项比对（scripts/verify_official.py）"}
            with io.open(os.path.join(OFFICIAL, iid + ".json"), "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        ok += same
    print("-" * 62)
    print(f"核对一致 {ok} 项" + ("（已写入 data/official/，下次 fetch 时升 B）" if not a.dry and ok else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
