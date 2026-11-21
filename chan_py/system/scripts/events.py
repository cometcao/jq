#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""事件日历：抓国家统计局「最新统计信息发布日程」，产出未来 N 天的发布事件。

为什么用它：统计局日程是**官方、结构化、带日期与时间**的（表格 12 个月 × 发布内容），
比第三方经济日历更符合"事件必须可追溯官方来源"的规则。

边界（与 SKILL 的 events 规则一致）：
- 事件层**不参与 as-of**；报告另标 horizon；
- 只出统计局日程（CPI/PPI/GDP/PMI/工业/投资/消费等）；央行 OMO、交易所公告不在此表，标不可读；
- 日期靠"日/周几"反推年份，匹配不上就跳过，不猜。

用法：
    python scripts/events.py                 # 未来 30 天
    python scripts/events.py --days 14
    python scripts/events.py --json --write  # 写 data/events/calendar-<asof>.json
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
OUT = os.path.join(ROOT, "data", "events")
URL = "https://www.stats.gov.cn/sj/fbrc/bnxxfb/"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
WD = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}


def latest_trade_day():
    try:
        with io.open(os.path.join(ROOT, "data", "cache", "IDX_DAILY.json"), encoding="utf-8") as f:
            return json.load(f).get("data_period") or dt.date.today().isoformat()
    except Exception:
        return dt.date.today().isoformat()


def fetch_table():
    import pandas as pd
    import requests

    r = requests.get(URL, headers=UA, timeout=30)
    r.encoding = "utf-8"
    tables = pd.read_html(io.StringIO(r.text))
    return tables[0]


def resolve_year(month, day, weekday, today):
    """用「日/周几」反推年份：只在今年与明年里找（日程表通常覆盖未来 12 个月）。"""
    for y in (today.year, today.year + 1):
        try:
            d = dt.date(y, month, day)
        except ValueError:
            continue
        if d.weekday() == weekday:
            return d
    return None


def parse(df, today, horizon):
    rows = df.values.tolist()
    header = rows[0]
    months = [int(str(x).strip().rstrip("月")) for x in header[2:] if "月" in str(x)]
    events = []
    i = 1
    while i < len(rows):
        content = str(rows[i][1]).strip() if len(rows[i]) > 1 else ""
        if not content or content == "nan":
            i += 1
            continue
        date_row = rows[i]
        time_row = rows[i + 1] if i + 1 < len(rows) else None
        for idx, m in enumerate(months):
            cell = str(date_row[idx + 2]).strip()
            mt = re.match(r"^(\d{1,2})\s*/\s*([一二三四五六日天])$", cell)
            if not mt:
                continue
            day, wd = int(mt.group(1)), WD[mt.group(2)]
            d = resolve_year(m, day, wd, today)
            if not d:
                continue
            hhmm = ""
            if time_row is not None:
                tcell = str(time_row[idx + 2]).strip()
                mm = re.match(r"^(\d{1,2}:\d{2})", tcell)
                if mm:
                    hhmm = mm.group(1).rjust(5, "0")
            if today <= d <= today + dt.timedelta(days=horizon):
                events.append({
                    "date": d.isoformat(), "time": hhmm, "event": content,
                    "source": "国家统计局·最新统计信息发布日程", "url": URL, "confirmed": True,
                })
        i += 2
    events.sort(key=lambda e: (e["date"], e["time"]))
    return events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    as_of = latest_trade_day()
    today = dt.date.fromisoformat(as_of)
    try:
        df = fetch_table()
        events = parse(df, today, a.days)
    except Exception as e:
        print(f"✗ 统计局日程抓取失败：{type(e).__name__}: {str(e)[:120]}")
        print("  该源转 not_crawlable，事件日历降级为人工录入（data/events/manual.md）")
        return 2

    payload = {"as_of": as_of, "horizon_days": a.days, "source": URL,
               "event_count": len(events), "events": events}

    if a.write:
        os.makedirs(OUT, exist_ok=True)
        fp = os.path.join(OUT, f"calendar-{as_of}.json")
        with io.open(fp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    if a.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"与 C1 指针一致：未来 {a.days} 天统计局发布日程 {len(events)} 项（as-of {as_of}）")
    print(f"{'日期':<12}{'时间':<7}发布内容")
    print("-" * 70)
    for e in events:
        print(f"{e['date']:<12}{(e['time'] or '—'):<7}{e['event']}")
    print("-" * 70)
    print("来源：国家统计局·最新统计信息发布日程（官方）；央行 OMO / 交易所公告不在本表 → 不可读")
    return 0


if __name__ == "__main__":
    sys.exit(main())
