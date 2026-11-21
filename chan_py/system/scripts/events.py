#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""事件面数据：多源抓取「可能的事件」。

两类来源，输出里用 `event_status` 区分：
  1. 未来预定 —— 官方**日程表**（统计局发布日程）。这是真正的"将要发生"。
  2. 已发生   —— 官方**新闻列表**（央行新闻发布、证监会要闻）。政策、会议、公告一发布就能进来。

为什么分开：规则只允许"官方日历明确列出"的入未来预定；新闻是已发生，不能倒推成未来。
**没有官方链接的一律不入**（media/传闻只列未确认线索）。

用法：
    python scripts/events.py --days 30            # 表格
    python scripts/events.py --json --write       # 写 data/events/calendar-<asof>.json
"""
import argparse
import datetime as dt
import io
import json
import os
import re
import sys
import warnings

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "events")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
WD = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}

STATS_URL = "https://www.stats.gov.cn/sj/fbrc/bnxxfb/"
PBC_URL = "http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html"
CSRC_URL = "http://www.csrc.gov.cn/csrc/c100028/common_list.shtml"


def latest_trade_day():
    try:
        with io.open(os.path.join(ROOT, "data", "cache", "IDX_DAILY.json"), encoding="utf-8") as f:
            return json.load(f).get("data_period") or dt.date.today().isoformat()
    except Exception:
        return dt.date.today().isoformat()


# ---------------------------------------------------------------- 源 1：统计局日程（未来预定）
def fetch_stats_schedule(today, horizon):
    import pandas as pd
    import requests

    r = requests.get(STATS_URL, headers=UA, timeout=30)
    r.encoding = "utf-8"
    df = pd.read_html(io.StringIO(r.text))[0]
    rows, header = df.values.tolist(), df.values.tolist()[0]
    months = [int(str(x).strip().rstrip("月")) for x in header[2:] if "月" in str(x)]
    out, i = [], 1
    while i < len(rows):
        content = str(rows[i][1]).strip() if len(rows[i]) > 1 else ""
        if not content or content == "nan":
            i += 1
            continue
        drow = rows[i]
        trow = rows[i + 1] if i + 1 < len(rows) else None
        for idx, m in enumerate(months):
            cell = str(drow[idx + 2]).strip()
            mt = re.match(r"^(\d{1,2})\s*/\s*([一二三四五六日天])$", cell)
            if not mt:
                continue
            day, wd = int(mt.group(1)), WD[mt.group(2)]
            d = None
            for y in (today.year, today.year + 1):
                try:
                    cand = dt.date(y, m, day)
                except ValueError:
                    continue
                if cand.weekday() == wd:
                    d = cand
                    break
            if not d or not (today <= d <= today + dt.timedelta(days=horizon)):
                continue
            hhmm = ""
            if trow is not None:
                mm = re.match(r"^(\d{1,2}:\d{2})", str(trow[idx + 2]).strip())
                hhmm = mm.group(1).rjust(5, "0") if mm else ""
            out.append({"date": d.isoformat(), "time": hhmm, "title": content,
                        "event_type": "数据发布", "event_status": "未来预定",
                        "issuer": "国家统计局", "entry_mode": "auto", "source_link": STATS_URL})
        i += 2
    return out


# ---------------------------------------------------------------- 源 2/3：官方新闻（已发生）
def classify(title):
    if any(k in title for k in ("统计局", "指数", "数据", "运行情况", "统计")):
        return "数据发布"
    if any(k in title for k in ("会议", "例会", "座谈", "论坛", "峰会", "发布会")):
        return "政策会议"
    return "其他"


def fetch_news_list(url, issuer, today, horizon):
    import requests

    r = requests.get(url, headers=UA, timeout=30)
    r.encoding = "utf-8"
    html = r.text
    base = re.match(r"^(https?://[^/]+)", url).group(1)
    pairs = re.findall(r'href="(/[^"]+)"[^>]*title="([^"]{6,80})"[^>]*>(?:.{0,200}?)(\d{4}-\d{2}-\d{2})', html, flags=re.S)
    seen, out = set(), []
    for href, title, dstr in pairs:
        if title in seen:
            continue
        seen.add(title)
        try:
            d = dt.date.fromisoformat(dstr)
        except Exception:
            continue
        if not (today - dt.timedelta(days=horizon) <= d <= today):
            continue
        out.append({"date": d.isoformat(), "time": "", "title": title,
                    "event_type": classify(title), "event_status": "已发生",
                    "issuer": issuer, "entry_mode": "auto", "source_link": base + href})
    return out[:12]


def _csrc_guard(fn, url, issuer, today, horizon):
    """证监会列表页由 JS 动态渲染（静态 HTML 只到 2021 年），抓不到当期条目时明确报 not_crawlable。"""
    got = fn(url, issuer, today, horizon)
    if not got:
        raise RuntimeError("not_crawlable：列表页由 JS 渲染，静态 HTML 无当期条目")
    return got


def collect(today, horizon):
    events, errors = [], []
    for name, fn in (("统计局日程", lambda: fetch_stats_schedule(today, horizon)),
                     ("央行新闻", lambda: fetch_news_list(PBC_URL, "中国人民银行", today, horizon)),
                     ("证监会要闻", lambda: _csrc_guard(fetch_news_list, CSRC_URL, "中国证监会", today, horizon))):
        try:
            got = fn()
            events += got
            print(f"  ✓ {name:<10} {len(got):>2} 条")
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}: {str(e)[:60]}")
            print(f"  ✗ {name:<10} 失败：{type(e).__name__}")
    events.sort(key=lambda e: (e["event_status"] != "未来预定", e["date"], e["time"]))
    return events, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    as_of = latest_trade_day()
    today = dt.date.fromisoformat(as_of)
    events, errors = collect(today, a.days)

    payload = {"as_of": as_of, "horizon_days": a.days, "event_count": len(events),
               "sources": {"stats_schedule": STATS_URL, "pbc_news": PBC_URL, "csrc_news": CSRC_URL},
               "errors": errors, "events": events}
    if a.write:
        os.makedirs(OUT, exist_ok=True)
        with io.open(os.path.join(OUT, f"calendar-{as_of}.json"), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    if a.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    fut = [e for e in events if e["event_status"] == "未来预定"]
    hap = [e for e in events if e["event_status"] == "已发生"]
    print(f"与 C1 指针一致：未来 {a.days} 天预定 {len(fut)} 项 · 近 {a.days} 天已发生 {len(hap)} 项（as-of {as_of}）")
    print(f"\n【未来预定】")
    for e in fut:
        print(f"  {e['date']} {e['time'] or '—':<5} {e['event_type']:<5} {e['title']}")
    print(f"\n【已发生（近 {a.days} 天）】")
    for e in hap:
        print(f"  {e['date']} {'':<5} {e['event_type']:<5} {e['title'][:40]}")
    print("\n来源：统计局发布日程（未来预定）· 央行/证监会新闻发布（已发生）；无官方链接者不入")
    return 0


if __name__ == "__main__":
    sys.exit(main())
