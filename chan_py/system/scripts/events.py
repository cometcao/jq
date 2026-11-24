#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""事件面数据：多源抓取「可能的事件」。

两类来源，输出里用 `event_status` 区分：
  1. 未来预定 —— 官方**日程表**（统计局发布日程）。这是真正的"将要发生"。
  2. 已发生   —— 官方**新闻列表**（央行新闻发布、证监会要闻）。政策、会议、公告一发布就能进来。

为什么分开：规则只允许"官方日历明确列出"的入未来预定；新闻是已发生，不能倒推成未来。
**没有官方链接的一律不入**（传闻/媒体日期不进日历，也不另行保留）。

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

# 部委新闻/政策发布（已发生；实测可抓）
DEPT_SOURCES = [
    ("国家发展改革委", "https://www.ndrc.gov.cn/xwdt/xwfb/"),
    ("财政部", "https://www.mof.gov.cn/zhengwuxinxi/caizhengxinwen/"),
    ("国家药监局", "https://www.nmpa.gov.cn/yaowen/ypjgyw/index.html"),
    ("国家能源局", "https://www.nea.gov.cn/xwzx/"),
    # 工信部：首页与电子信息司为 JS 渲染/404，但下列司局子栏目是静态 HTML，可解析
    ("工业和信息化部", "https://www.miit.gov.cn/jgsj/ghs/index.html"),   # 规划司
    ("工业和信息化部", "https://www.miit.gov.cn/jgsj/kjs/index.html"),   # 科技司
    ("工业和信息化部", "https://www.miit.gov.cn/jgsj/ycls/index.html"),  # 原材料司
]



SCHEMA_PATH = os.path.join(ROOT, "schemas", "event.schema.json")


def _schema():
    with io.open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def to_event_record(raw, calendar_version=1):
    """把抓到的原始行转成 event.schema.json 的记录（字段名与枚举严格对齐）。"""
    import hashlib

    date = raw["date"]
    title = (raw.get("title") or "")[:80]
    issuer = raw.get("issuer") or ""
    h = hashlib.md5(f"{date}|{issuer}|{title}".encode("utf-8")).hexdigest()[:6]
    return {
        "event_id": f"EVT-{date.replace('-', '')}-{h}",
        "event_type": raw.get("event_type") or "其他",
        "layer": raw.get("layer") or "市场",
        "event_date": date,
        "event_time": (raw.get("time") or None),
        "scope": title,                      # schema 无 title 字段，标题落 scope
        "data_period": None,
        "event_status": raw.get("event_status") or "已发生",
        "status_changed_at": None,
        "issuer": issuer,
        "entry_mode": raw.get("entry_mode") or "auto",
        "source_tier": "A",                  # 全部抓自官方站点
        "source_link": raw.get("source_link") or None,
        "calendar_version": calendar_version,
        "observation_time": dt.datetime.now().isoformat(timespec="seconds"),
        "missing_type": "none",
    }


def validate_events(records):
    """按 event.schema.json 校验（无 jsonschema 依赖，手写最小校验：必填 + 枚举 + 类型）。"""
    sch = _schema()
    req = sch["required"]
    props = sch["properties"]
    errs = []
    for i, rec in enumerate(records):
        for k in req:
            if k not in rec:
                errs.append(f"#{i} 缺必填 {k}")
        extra = set(rec) - set(props)
        if extra:
            errs.append(f"#{i} 多余字段 {sorted(extra)}")
        for k, v in rec.items():
            spec = props.get(k)
            if not spec:
                continue
            if "enum" in spec and v is not None and v not in spec["enum"]:
                errs.append(f"#{i} {k}={v!r} 不在枚举")
            t = spec.get("type")
            if t == "integer" and not isinstance(v, int):
                errs.append(f"#{i} {k} 应为整数")
            if t == "string" and not isinstance(v, str):
                errs.append(f"#{i} {k} 应为字符串")
    return errs


def latest_trade_day():
    """目标交易日：工作日且已过 15:00 → 当天，否则回退上一工作日。

    不再借指数缓存的数据期——指数源滞后一天时会把日历文件标成前一天。
    """
    now = dt.datetime.now()
    d = now.date()
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    if d == now.date() and now.hour < 15:
        d -= dt.timedelta(days=1)
        while d.weekday() >= 5:
            d -= dt.timedelta(days=1)
    return d.isoformat()


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



def _norm_date(s):
    s = s.strip()
    m = re.match(r"^(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", s)
    if not m:
        return None
    return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def fetch_dept_news(issuer, url, today, horizon):
    """部委新闻列表：标题 + 近 N 天日期。事件类型按标题归类，部委政策文件归“其他”（附 category）。"""
    import requests
    from urllib.parse import urljoin

    r = requests.get(url, headers=UA, timeout=25)
    r.encoding = r.apparent_encoding or "utf-8"
    h = r.text
    pairs = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.{4,90}?)</a>(.{0,400}?)(20\d{2}[-/年]\d{1,2}[-/月]\d{1,2})', h, flags=re.S)
    seen, out = set(), []
    for href, title, _, dstr in pairs:
        t = re.sub(r"<[^>]+>", "", title).strip()
        if not t or len(t) < 6 or t in seen or t.startswith("首页"):
            continue
        d = _norm_date(dstr)
        if not d or not (today - dt.timedelta(days=horizon) <= d <= today):
            continue
        seen.add(t)
        cat = "政策文件" if any(k in t for k in ("通知", "公告", "意见", "办法", "规划", "方案", "细则", "规定")) else "新闻"
        out.append({"date": d.isoformat(), "time": "", "title": t,
                    "event_type": classify(t) if cat == "新闻" else "其他",
                    "category": cat, "event_status": "已发生",
                    "issuer": issuer, "entry_mode": "auto", "source_link": urljoin(url, href)})
    return out[:20]


# ---------------------------------------------------------------- 源：巨潮资讯（证监会指定披露平台）
CNINFO_KEYWORDS = [("解禁", "解禁"), ("回购", "其他"), ("增持", "其他"),
                   ("减持", "其他"), ("定向增发", "其他"), ("业绩预告", "其他")]


def fetch_cninfo(keyword, event_type, today, horizon, limit=8):
    """巨潮公告全文检索：按关键词取近 N 天公告，作为公司层事件（官方披露平台）。"""
    import requests
    from urllib.parse import urljoin
    start = today - dt.timedelta(days=horizon)
    payload = {"pageNum": 1, "pageSize": limit, "column": "szse", "tabName": "fulltext",
               "searchkey": keyword, "seDate": f"{start.isoformat()}~{today.isoformat()}",
               "sortName": "", "sortType": "", "isHLtitle": "true"}
    r = requests.post("http://www.cninfo.com.cn/new/hisAnnouncement/query", data=payload, timeout=25,
                      headers={**UA, "Referer": "http://www.cninfo.com.cn/"})
    j = r.json() or {}
    out = []
    for a in (j.get("announcements") or []):
        title = re.sub(r"</?em>", "", a.get("announcementTitle") or "")[:80]
        d = (a.get("announcementTime") or 0) / 1000
        day = dt.datetime.fromtimestamp(d).date() if d else None
        if not day or not (start <= day <= today):
            continue
        out.append({"date": day.isoformat(), "time": "", "title": title,
                    "event_type": event_type, "category": "公告", "event_status": "已发生",
                    "issuer": "巨潮资讯", "entry_mode": "auto",
                    "source_link": urljoin("http://static.cninfo.com.cn/", a.get("adjunctUrl") or "")})
    return out


# 板块层事件关键词：板块名 + 行业同义词（巨潮全文检索）
SECTOR_KEYWORDS = {
    "半导体": ["半导体", "集成电路", "芯片"],
    "医药": ["医药", "药品", "创新药"],
    "电力": ["电力", "电网", "发电"],
    "基础化工": ["化工", "化学品"],
}


def fetch_cninfo_sector(today, horizon, limit=6):
    """板块层事件：按行业关键词检索巨潮公告（layer=板块，与市场层事件分开）。"""
    out = []
    start = today - dt.timedelta(days=horizon)
    for sector, kws in SECTOR_KEYWORDS.items():
        got = []
        for kw in kws:
            for e in fetch_cninfo(kw, "其他", today, horizon, limit=3):
                e["layer"] = "板块"
                e["scope"] = f"[{sector}] {e.get('title') or e.get('scope','')}"
                got.append(e)
        # 同名去重
        seen, uniq = set(), []
        for e in got:
            k = (e.get("scope") or "")[:40]
            if k in seen:
                continue
            seen.add(k)
            uniq.append(e)
        out += uniq[:limit]
    return out


# ---------------------------------------------------------------- 源：央行公开市场操作公告
PBC_OMO_URL = "http://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/125475/index.html"


def fetch_pbc_omo(today, horizon):
    """央行公开市场业务交易公告（已发生）：入日历，作为政策操作事件。"""
    import requests
    from urllib.parse import urljoin
    r = requests.get(PBC_OMO_URL, headers=UA, timeout=25)
    r.encoding = r.apparent_encoding or "utf-8"
    pairs = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.{6,90}?)</a>(.{0,200}?)(20\d{2}-\d{2}-\d{2})', r.text, flags=re.S)
    out, seen = [], set()
    for href, t, _, dstr in pairs:
        t = re.sub(r"<[^>]+>", "", t).strip()
        d = _norm_date(dstr)
        if not t or not d or not (today - dt.timedelta(days=horizon) <= d <= today):
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append({"date": d.isoformat(), "time": "", "title": t, "event_type": "政策会议",
                    "category": "公开市场操作", "event_status": "已发生", "issuer": "中国人民银行",
                    "entry_mode": "auto", "source_link": urljoin(PBC_OMO_URL, href), "layer": "市场"})
    return out[:20]


# ---------------------------------------------------------------- 源：新股发行（含未来申购/上市）
def fetch_ipo(today, horizon):
    """新股日历：从全量新股表取未来 N 天的申购日/上市日（东方财富，C 类）。"""
    import akshare as ak
    df = ak.stock_xgsglb_em(symbol="全部股票")
    out = []
    for _, r in df.iterrows():
        code = str(r.get("股票代码") or "").zfill(6)
        name = str(r.get("股票简称") or "")
        exch = str(r.get("交易所") or "")
        for col, kind in (("申购日期", "申购"), ("上市日期", "上市")):
            v = str(r.get(col) or "")
            d = _norm_date(v)
            if not d or not (today - dt.timedelta(days=3) <= d <= today + dt.timedelta(days=horizon)):
                continue
            out.append({"date": d.isoformat(), "time": "", "title": f"新股{kind}：{name}（{code}·{exch[:2]}）",
                        "event_type": "其他", "category": "新股发行",
                        "event_status": "未来预定" if d > today else "已发生",
                        "issuer": "交易所·新股发行", "entry_mode": "auto",
        "source_link": "https://www.sse.com.cn/assortment/stock/list/share/", "layer": "市场"})
    out.sort(key=lambda x: x["date"])
    return out[:30]


# ---------------------------------------------------------------- 信息含量分级
# 高信息量：有决定/结果/数字（政策文件、批复、数据、实质公告）
INFO_HIGH = ("印发", "发布", "决定", "通过", "批准", "批复", "签署", "达成", "公布",
             "征求意见", "公告", "通知", "意见", "办法", "规划", "方案", "规定", "细则",
             "标准", "名单", "修订", "实施", "启用", "调整", "处罚", "立案", "问询",
             "回购", "增持", "减持", "解禁", "定向增发", "业绩预告", "分红", "中标", "合同",
             "审评", "审批", "注册", "监管", "整治", "改革", "试点", "补贴", "税收", "招标", "签订")
# 纯行程/活动（无对象、无结果）
INFO_NOISE = ("会见", "调研", "考察", "座谈", "培训班", "举办", "出席", "致辞", "慰问",
              "走访", "庆祝", "参观", "宣讲", "学习", "交流", "亮相")
# 只有动作、没有落点（若同时不含 INFO_HIGH，则判低）
INFO_VERB_ONLY = ("召开", "参加", "率队", "赴", "推进", "开展", "部署", "传达", "巡视",
                  "督导", "启动", "动员")


def info_level(title):
    """判断事件信息含量：有决定/结果 → high；纯行程活动 → low。"""
    t = title or ""
    # 行程词优先：标题是"会见/出席/率队/座谈"这类，无论正文含什么政策词都是低信息
    if any(k in t for k in INFO_NOISE):
        return "low"
    if any(k in t for k in INFO_HIGH):
        return "high"
    if any(k in t for k in INFO_VERB_ONLY):
        return "low"          # 只有"召开/部署/推进"这类动作，没有落点
    return "mid"


COLLECT_STATS = {}


# ---------------------------------------------------------------- 源：央行公开市场操作（解析正文 → 到期日历）
def fetch_pbc_omo_detail(today, horizon, max_docs=25):
    """抓央行公开市场业务交易公告正文，解析逆回购/央票/MLF，并推算到期日。

    逆回购期限以正文为准（隔夜/7 天/14 天…），到期日 = 操作日 + 期限。
    隔夜逆回购次日到期，是未来 1 天最硬的信息。
    """
    import requests
    r = requests.get(PBC_OMO_URL, headers=UA, timeout=25)
    r.encoding = r.apparent_encoding or "utf-8"
    links = re.findall(r'<a[^>]+href="(/zhengcehuobisi/[^"]+)"[^>]*>\s*(公开市场业务交易公告[^<]*?)\s*<', r.text)
    out, seen = [], set()

    def body(href):
        try:
            rr = requests.get("http://www.pbc.gov.cn" + href, headers=UA, timeout=25)
            rr.encoding = rr.apparent_encoding or "utf-8"
            m = re.search(r'<div[^>]*id="zoom"[^>]*>(.*?)</div>', rr.text, flags=re.S)
            if not m:
                return ""
            return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip()
        except Exception:
            return ""

    for href, title in links[:max_docs]:
        if title in seen:
            continue
        seen.add(title)
        b = body(href)
        if not b:
            continue
        mdate = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", b)
        if not mdate:
            continue
        try:
            d0 = dt.date(int(mdate.group(1)), int(mdate.group(2)), int(mdate.group(3)))
        except Exception:
            continue
        # 逆回购：期限 + 中标量
        mrev = re.search(r"开展了([\d,.]+)亿元([^，。]{0,8})逆回购操作", b)
        if mrev:
            amt = mrev.group(1).replace(",", "")
            tenor = mrev.group(2).strip() or "隔夜"
            days = {"隔夜": 1, "7天": 7, "7 天": 7, "14天": 14, "14 天": 14,
                    "21天": 21, "28天": 28}.get(tenor.replace(" ", ""), None)
            kind = f"逆回购 {tenor}"
            maturity = (d0 + dt.timedelta(days=days)) if days else None
        elif "央票" in b:
            kind, amt, maturity = "央行票据", "", None
        elif "中期借贷便利" in b or "MLF" in b:
            kind, amt, maturity = "MLF", "", None
        else:
            continue
        out.append({"date": d0.isoformat(), "time": "", "title": f"公开市场操作：{kind} {amt} 亿元",
                    "event_type": "政策会议", "category": "公开市场操作", "event_status": "已发生",
                    "issuer": "中国人民银行", "entry_mode": "auto", "source_link": PBC_OMO_URL, "layer": "市场"})
        if maturity and amount_ok(amt):
            out.append({"date": maturity.isoformat(), "time": "",
                        "title": f"逆回购到期：{kind} {amt} 亿元（{d0.isoformat()} 操作）",
                        "event_type": "政策会议", "category": "公开市场操作",
                        "event_status": "未来预定" if maturity >= today else "已发生",
                        "issuer": "中国人民银行", "entry_mode": "auto", "source_link": PBC_OMO_URL, "layer": "市场"})
    return out


def amount_ok(a):
    try:
        return 0 < float(a) < 100000
    except Exception:
        return False


# ---------------------------------------------------------------- 源：限售解禁（未来日期）
def fetch_restricted_release(today, horizon):
    """限售解禁日历：未来 N 天每个解禁日一条（家数 + 解禁市值）。"""
    import akshare as ak
    end = today + dt.timedelta(days=horizon)
    try:
        df = ak.stock_restricted_release_summary_em(
            symbol="全部股票", start_date=today.strftime("%Y%m%d"), end_date=end.strftime("%Y%m%d"))
    except Exception:
        return []
    out = []
    for _, r in df.iterrows():
        try:
            d = _norm_date(str(r.get("解禁时间")))
            if not d:
                continue
            n = r.get("当日解禁股票家数")
            mv = r.get("实际解禁市值")
            mv_yi = (float(mv) / 1e8) if mv is not None and str(mv) not in ("nan", "None") else None
            title = f"限售解禁：{int(n) if n == n else '—'} 家" + (f"，解禁市值 {mv_yi:.1f} 亿" if mv_yi else "")
            out.append({"date": d.isoformat(), "time": "", "title": title, "event_type": "解禁",
                        "category": "限售解禁", "event_status": "未来预定" if d >= today else "已发生",
                        "issuer": "交易所·限售解禁", "entry_mode": "auto",
                        "source_link": "https://www.szse.cn/market/periodical/statistic/index.html", "layer": "市场"})
        except Exception:
            continue
    return out[:40]


# ---------------------------------------------------------------- 源：定期报告披露窗口
def _report_period_for(today):
    """按日期挑当前/下一个披露期（预约披露表用“YYYY年报/一季/半年/三季”命名）。"""
    m, d = today.month, today.day
    y = today.year
    if m == 1:
        return f"{y-1}年报"
    if m <= 4:
        return f"{y}一季"
    if m <= 8:
        return f"{y}半年"
    if m <= 10:
        return f"{y}三季"
    return f"{y}年报"


def fetch_report_season(today, horizon, period=None):
    period = period or _report_period_for(today)
    """财报披露窗口：未来 N 天每天的预约披露家数（巨潮预约披露表）。"""
    import akshare as ak
    try:
        df = ak.stock_report_disclosure(market="沪深京", period=period)
    except Exception:
        return []
    col = "实际披露" if "实际披露" in df.columns else "首次预约"
    from collections import Counter
    c = Counter()
    for v in df[col].tolist():
        d = _norm_date(str(v)[:10])
        if d and today <= d <= today + dt.timedelta(days=horizon):
            c[d] += 1
    out = []
    for d in sorted(c):
        out.append({"date": d.isoformat(), "time": "",
                    "title": f"定期报告披露：{c[d]} 家（{period}）", "event_type": "财报披露",
                    "category": "定期报告", "event_status": "未来预定",
                    "issuer": "巨潮资讯·预约披露", "entry_mode": "auto",
        "source_link": "https://www.cninfo.com.cn/new/commonUrl?url=disclosure/yuyue", "layer": "市场"})
    return out[:20]


def collect(today, horizon):
    events, errors = [], []
    tasks = [("统计局日程", lambda: fetch_stats_schedule(today, horizon)),
             ("央行新闻", lambda: fetch_news_list(PBC_URL, "中国人民银行", today, horizon)),
             ("证监会要闻", lambda: _csrc_guard(fetch_news_list, CSRC_URL, "中国证监会", today, horizon)),
             ("央行公开市场操作", lambda: fetch_pbc_omo_detail(today, horizon)),
             ("新股发行", lambda: fetch_ipo(today, horizon)),
             ("限售解禁", lambda: fetch_restricted_release(today, horizon)),
             ("定期报告", lambda: fetch_report_season(today, horizon))]
    tasks += [(issuer, (lambda i=issuer, u=url: fetch_dept_news(i, u, today, horizon))) for issuer, url in DEPT_SOURCES]
    tasks += [(f"巨潮·{kw}", (lambda k=kw, t=et: fetch_cninfo(k, t, today, horizon))) for kw, et in CNINFO_KEYWORDS]
    tasks += [("巨潮·板块", lambda: fetch_cninfo_sector(today, horizon))]
    for name, fn in tasks:
        try:
            got = fn()
            events += got
            print(f"  ✓ {name:<10} {len(got):>2} 条")
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}: {str(e)[:60]}")
            print(f"  ✗ {name:<10} 失败：{type(e).__name__}")
    # 事件层面统一过滤：已发生事件里，纯行程/活动（无决定无结果）不入日历
    before = len(events)
    kept, dropped = [], 0
    for e in events:
        if e.get("event_status") == "未来预定":
            kept.append(e)
            continue
        if e.get("event_type") in ("数据发布", "解禁") or e.get("category") in ("新股发行", "公开市场操作"):
            kept.append(e)
            continue
        if info_level(e.get("title") or "") == "low":
            dropped += 1
            continue
        kept.append(e)
    events = kept
    print(f"  · 信息含量过滤：丢弃 {dropped} 条纯行程/活动（原 {before} 条 → {len(events)} 条）")
    COLLECT_STATS.clear(); COLLECT_STATS.update({"before": before, "dropped": dropped, "after": len(events)})
    order = {"未来预定": 0, "已发生": 1}
    events.sort(key=lambda e: (order.get(e["event_status"], 3), e["date"], e.get("time") or ""))
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

    records = [to_event_record(e) for e in events]
    verrs = validate_events(records)
    if verrs:
        print(f"✗ 事件记录不符合 event.schema.json（{len(verrs)} 处），未写入：")
        for e in verrs[:6]:
            print("   -", e)
        return 3
    payload = {"filter_stats": COLLECT_STATS, "as_of": as_of, "horizon_days": a.days, "event_count": len(records),
               "calendar_version": 1,
               "sources": {"stats_schedule": STATS_URL, "pbc_news": PBC_URL,
                           "depts": [u for _, u in DEPT_SOURCES]},
               "errors": errors, "events": records}
    if a.write:
        os.makedirs(OUT, exist_ok=True)
        with io.open(os.path.join(OUT, f"calendar-{as_of}.json"), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    if a.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    fut = [e for e in records if e["event_status"] == "未来预定"]
    hap = [e for e in records if e["event_status"] == "已发生"]
    print(f"与 C1 指针一致：未来 {a.days} 天预定 {len(fut)} 项 · 近 {a.days} 天已发生 {len(hap)} 项（as-of {as_of}）")
    print(f"\n【未来预定】")
    for e in fut:
        print(f"  {e['event_date']} {(e['event_time'] or '—'):<5} {e['event_type']:<5} {e['scope']}")
    print(f"\n【已发生（近 {a.days} 天）】")
    for e in hap:
        print(f"  {e['event_date']} {'':<5} {e['event_type']:<5} {e['scope'][:40]}  · {e['issuer']}")
    print("\n来源：统计局日程（未来预定）· 央行/部委新闻（已发生）；无官方链接者不入日历")
    return 0


if __name__ == "__main__":
    sys.exit(main())
