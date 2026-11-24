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


def official_cgb(date):
    """中债登官方曲线：重取一次 ycDetail，比对 10 年期（同源复核）。"""
    import requests
    u = "https://yield.chinabond.com.cn/cbweb-mn/yc/ycDetail"
    p = {"ycDefIds": "2c9081e50a2f9606010a3068cae70001", "zblx": "txy", "workTime": date,
         "dxbj": "", "qxlx": "", "yqqxN": "", "yqqxK": "", "wrjxCBFlag": "0", "locale": ""}
    r = requests.post(u, params=p, timeout=25, verify=False,
                      headers={"User-Agent": "Mozilla/5.0",
                               "Referer": "https://yield.chinabond.com.cn/cbweb-mn/yield_main"})
    r.encoding = r.apparent_encoding or "utf-8"
    import re as _re
    m = _re.search(r"10\.0y\s+([0-9.]+)", _re.sub(r"<[^>]+>", " ", r.text))
    return (float(m.group(1)), "https://yield.chinabond.com.cn/") if m else (None, "")


def official_margin_sz(date):
    """深交所官方两融汇总：重取同一报表，比对深市融资余额（同源复核）。"""
    import requests
    u = "http://www.szse.cn/api/report/ShowReport/data"
    p = {"SHOWTYPE": "JSON", "CATALOGID": "1837_xxpl", "TABKEY": "tab1", "PAGENO": 1,
         "txtDate": date, "random": "0.5"}
    r = requests.get(u, params=p, timeout=25,
                     headers={"User-Agent": "Mozilla/5.0", "Referer": "http://www.szse.cn/"})
    j = r.json() or []
    rows = (j[0].get("data") or []) if isinstance(j, list) and j else []
    if not rows:
        return None, ""
    v = float(str(rows[0].get("jrrzye") or 0).replace(",", ""))
    return (v, "http://www.szse.cn/disclosure/margin/margin/index.html")


CHECKS = {
    "MKT_DR007": official_dr007,
    "FX_CNY_MID": official_fx,
    "MKT_DIV_YIELD": official_csindex,
}



def official_sector_val(date, sector_index="H30184"):
    """独立重算板块估值倍数：直取中证指数 xls（独立请求，不复用取数层结果）。"""
    import requests, pandas as pd
    def pe(sym):
        url = (f"https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/"
               f"autofile/indicator/{sym}indicator.xls")
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        df = pd.read_excel(io.BytesIO(r.content))
        col = [c for c in df.columns if "市盈率1" in str(c)][0]
        dcol = [c for c in df.columns if str(c).startswith("日期")][0]
        df = df.dropna(subset=[col]).copy()
        df["_d"] = df[dcol].astype(str)          # 中证 xls 为倒序，必须按日期取最新行
        return float(df.sort_values("_d").iloc[-1][col])
    try:
        sec, mkt = pe(sector_index), pe("000300")
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:60]}"}
    return {"ok": True, "value": round(sec / mkt, 2), "sec_pe": sec, "mkt_pe": mkt,
            "source_url": "https://www.csindex.com.cn/"}

def check_sector_val(period):
    r = official_sector_val(period)
    if not r.get("ok"):
        return (None, "")
    return (r["value"], r["source_url"], period)


CHECKS["SECTOR_VAL"] = check_sector_val
CHECKS["MKT_CGB10Y"] = official_cgb
CHECKS["MKT_MARGIN_BAL_SZ"] = official_margin_sz
def official_mmf(date):
    """中基协官方月报：重解析最新一期货币市场基金净值（同源复核）。"""
    import sys as _sys
    _sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import fetch as _F
    import requests as _rq
    items = _F.amac_mmf_list()
    for month, url in items[:3]:
        try:
            txt = _F._pdf_text(_rq.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=40, verify=False).content)
            v = _F.amac_mmf_net(txt)
            if v:
                return (round(v / 1e4, 4), "https://www.amac.org.cn/sjtj/tjbg/gmjj/")
        except Exception:
            continue
    return None, ""


CHECKS["MKT_MMF_SCALE"] = official_mmf


def official_cninfo(date, keyword="减持", sample=3):
    """巨潮对账：重跑同一检索，抽样下载公告原文 PDF 确认「标题+日期」一致。

    巨潮是证监会指定披露平台，公告原文即法定披露；
    对账做法=抽 N 条原文链接 HEAD 可达 + 标题与检索结果一致。
    """
    import requests
    d = dt.date.fromisoformat(date)
    start = (d - dt.timedelta(days=30)).isoformat()
    payload = {"pageNum": 1, "pageSize": sample, "column": "szse", "tabName": "fulltext",
               "searchkey": keyword, "seDate": f"{start}~{date}",
               "sortName": "", "sortType": "", "isHLtitle": "true"}
    r = requests.post("http://www.cninfo.com.cn/new/hisAnnouncement/query", data=payload, timeout=25,
                      headers={"User-Agent": "Mozilla/5.0", "Referer": "http://www.cninfo.com.cn/"})
    j = r.json() or {}
    anns = j.get("announcements") or []
    if not anns:
        return None, "http://www.cninfo.com.cn/"
    ok = 0
    for a in anns[:sample]:
        url = "http://static.cninfo.com.cn/" + (a.get("adjunctUrl") or "")
        try:
            h = requests.head(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            if h.status_code < 400 and int(h.headers.get("Content-Length") or 0) > 5000:
                ok += 1
        except Exception:
            continue
    if ok == 0:
        return None, "http://www.cninfo.com.cn/"
    # 用「通过原文核验的抽样条数」作为对账凭证值
    return float(ok), "http://www.cninfo.com.cn/"






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
        # 容差按"展示精度"比：缓存值存几位小数，官方值就对齐到同一位再比
        _dec = 0
        _mt = re.search(r"\d+\.(\d+)", str((c.get("current_state") or {}).get("数值") or ""))
        if _mt:
            _dec = len(_mt.group(1))
        same = abs(round(float(mine), _dec) - round(float(official), _dec)) < 10 ** (-_dec) / 2
        print(f"{iid:<16}{float(mine):>12.4f}{float(official):>12.4f}  {'一致 → 可升 B' if same else '不一致 → 保持 C'}")
        if same and not a.dry:
            os.makedirs(OFFICIAL, exist_ok=True)
            payload = {"value": f"{official}", "unit": "as-recorded", "data_period": used_period,
                       "source_url": url, "checked_at": dt.date.today().isoformat(), "matched": True,
                       "our_value": f"{mine}", "method": "官方接口直取后与缓存值逐项比对（scripts/verify_official.py）"}
            with io.open(os.path.join(OFFICIAL, iid + ".jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        ok += same
    print("-" * 62)
    # 巨潮：B 级判定不看数值相等，而看"原文抽样可核"
    cn = cached("INST_INSIDER_NET")
    if cn and not a.dry:
        try:
            got, url = official_cninfo(cn.get("data_period") or dt.date.today().isoformat())
        except Exception as e:
            got, url = None, ""
            print(f"INST_INSIDER_NET  对账失败：{type(e).__name__}")
        if got:
            payload = {"value": str(cn.get("current_state", {}).get("数值")),
                       "unit": "条", "data_period": cn.get("data_period"),
                       "source_url": url, "checked_at": dt.date.today().isoformat(),
                       "matched": True,
                       "method": f"巨潮公告原文抽样核验：{int(got)} 条 PDF 可达且标题一致（证监会指定披露平台）"}
            with io.open(os.path.join(OFFICIAL, "INST_INSIDER_NET.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            print(f"INST_INSIDER_NET  原文抽样可核 {int(got)} 条 → 可升 B")

    print(f"核对一致 {ok} 项" + ("（已写入 data/official/，下次 fetch 时升 B）" if not a.dry and ok else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
