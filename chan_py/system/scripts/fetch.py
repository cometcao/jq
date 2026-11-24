#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""取数层：akshare 多源 + 别名解析 + 限速 + 缓存 + 失败降级 + 官方对账。

约束（对应 docs/01 第十节 1 的 D03）：
- akshare 抓来的数据属于 **C 类**（第三方加工）。要进状态词，须有 A/B 佐证或对账后升 B。
- 每个指标声明多个 provider，按顺序尝试；失败降级，全失败写 missing_type。
- 函数名用「别名列表」解析：akshare 改名（1.20 大改）只需在别名里补一条。
- 限速：同源最小间隔，避免被封（实测东财 push2 会封 IP）。

用法：
    python scripts/fetch.py                     # 抓全部
    python scripts/fetch.py POL_LPR MKT_CGB10Y  # 只抓指定指标
    python scripts/fetch.py --as-of 2026-11-20  # 指定 as-of
    python scripts/fetch.py --list              # 列出注册指标
    python scripts/fetch.py --no-cache          # 忽略缓存

输出：
    data/cache/<id>.json         最近一次成功结果
    data/facts/<期>/<id>.json    符合 schemas/fact.schema.json 的事实记录
    data/official/<id>.json      （可选）官方对账 → 记录升 B
"""
import argparse
import datetime as dt
import io
import json
import os
import re
import statistics as st
import sys
import time
import warnings
import inspect
import re

import pandas as pd

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    import akshare as ak
except Exception as e:  # pragma: no cover
    print(f"akshare 不可用：{e}")
    sys.exit(2)

CACHE_DIR = os.path.join(ROOT, "data", "cache")
FACT_DIR = os.path.join(ROOT, "data", "facts")
OFFICIAL_DIR = os.path.join(ROOT, "data", "official")
MIN_INTERVAL = 1.2
TTL_HOURS = {"日": 6, "周": 24, "月": 72, "季": 168, "不定期": 24}
# 新鲜度闸门：数据期距今天超过 N 天则判「疑似截断/过旧」，换下一个源
LAG_DAYS = {"日": 10, "周": 30, "月": 60, "季": 200, "不定期": 400}

_last_call = {}


# ---------------------------------------------------------------- 工具
def resolve(names):
    for n in names:
        if n in LOCAL_FNS:
            return n, LOCAL_FNS[n]
        fn = getattr(ak, n, None)
        if fn is not None:
            return n, fn
    return None, None


def throttled(source):
    gap = time.time() - _last_call.get(source, 0)
    if gap < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - gap)
    _last_call[source] = time.time()



REVIS_DIR = os.path.join(ROOT, "data", "revisions")


def atomic_write_json(path, obj):
    """先写 .tmp 再 os.replace，避免半截文件（截断事故的教训）。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def append_revision(iid, data_period, value, tier, source):
    """把每次写入追加到 data/revisions/<id>/<period>.jsonl（永不覆盖）。"""
    d = os.path.join(REVIS_DIR, iid)
    os.makedirs(d, exist_ok=True)
    fp = os.path.join(d, f"{data_period}.jsonl")
    seq, prev = 0, None
    if os.path.exists(fp):
        rows = [l for l in io.open(fp, encoding="utf-8").read().splitlines() if l.strip()]
        seq = len(rows)
        if rows:
            try:
                prev = json.loads(rows[-1]).get("value")
            except Exception:
                pass
    entry = {"revision_seq": seq, "indicator_id": iid, "data_period": data_period,
             "value": value, "changed_from": prev, "changed": prev is not None and prev != value,
             "source": source, "source_tier": tier,
             "observed_at": dt.datetime.now().isoformat(timespec="seconds")}
    with io.open(fp, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry

def read_json(path, default=None):
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, obj):
    atomic_write_json(path, obj)


def norm_period(raw):
    """把 '2026年10月份' / '202610' / '2026.10' / 8 位数字 / date 统一成 YYYY-MM-DD 或 YYYY-MM-01。"""
    s = str(raw)
    m8 = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", s.strip())
    if m8:
        return f"{m8.group(1)}-{m8.group(2)}-{m8.group(3)}"
    m = re.search(r"(\d{4})\D*(\d{1,2})", s)
    if not m:
        return s[:10]
    y, mo = m.group(1), int(m.group(2))
    day = 1
    d = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", s)
    if d:
        day = int(d.group(3))
    return f"{y}-{mo:02d}-{day:02d}"


def num_of(s):
    m = re.search(r"[-+]?\d+(?:\.\d+)?", str(s or "").replace(",", ""))
    return float(m.group(0)) if m else None



def biz_days_between(period, as_of):
    """按交易日（周一至周五）计相差天数；周末/节假日不把 stale 惩罚放大。"""
    try:
        a = dt.date.fromisoformat(str(period)[:10])
        b = dt.date.fromisoformat(str(as_of)[:10])
    except Exception:
        return None
    if b <= a:
        return 0
    n, cur = 0, a
    while cur < b:
        cur += dt.timedelta(days=1)
        if cur.weekday() < 5:
            n += 1
    return n


def period_lag_days(period):
    try:
        d = dt.date.fromisoformat(str(period)[:10])
        return (dt.date.today() - d).days
    except Exception:
        return None


def last_valid(df, col, date_col="日期"):
    """按 date 升序取最后一个 col 非空的行。"""
    if date_col not in df.columns:
        date_col = df.columns[0]
    d = df.dropna(subset=[col]).sort_values(date_col)
    return d.iloc[-1]


def find_col(df, *kw):
    for c in df.columns:
        if all(k in c for k in kw):
            return c
    return None





MANUAL_DIR = os.path.join(ROOT, "data", "manual")


def read_manual(iid):
    """读 data/manual/<id>.json（人工录入）；未填 value 视为没录入。"""
    c = read_json(os.path.join(MANUAL_DIR, iid + ".json"))
    if not c or not str(c.get("value") or "").strip():
        return None
    return c


def _sector_index_code():
    m = read_json(os.path.join(ROOT, "data", "sector_index_map.json"), {}) or {}
    return (m.get("map") or {}).get(_sector_target())


def _sector_target():
    """当前板块目标（默认半导体）；改 data/sector_target.json 即可换。"""
    c = read_json(os.path.join(ROOT, "data", "sector_target.json"), {}) or {}
    return c.get("name", "半导体")




def history_prev(iid, period, tail=200):
    """从历史序列里取「上一可比期」（严格早于当前数据期）。

    calc 类解析器不吃传入的 df，用「去掉一行重解析」拿不到不同结果，
    必须回到历史序列取前值，否则会把自己当上一期、误判成"不变"。
    """
    fp = os.path.join(ROOT, "data", "history", iid + ".jsonl")
    if not os.path.exists(fp):
        return {}
    try:
        rows = [json.loads(x) for x in io.open(fp, encoding="utf-8").read().splitlines() if x.strip()][1:]
    except Exception:
        return {}
    earlier = [(r["data_period"], r["value"]) for r in rows if str(r.get("data_period", "")) < str(period)]
    if not earlier:
        return {}
    per, val = sorted(earlier)[-1]
    return {"prev_period": per, "prev_value": val}

def _trade_day_of(now=None):
    """当前时点能拿到的最新年线交易日：工作日且已过 15:00 → 当天，否则回退上一工作日。"""
    now = now or dt.datetime.now()
    d = now.date()
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    if d == now.date() and now.hour < 15:
        d -= dt.timedelta(days=1)
        while d.weekday() >= 5:
            d -= dt.timedelta(days=1)
    return d.isoformat()


def _latest_trade_day():
    """用指数日线的数据期作为最近交易日；没有就退回今天（避免周末把快照标成当天）。"""
    c = read_json(os.path.join(CACHE_DIR, "IDX_DAILY.json"))
    if c and c.get("data_period"):
        return c["data_period"]
    return dt.date.today().isoformat()

# ---------------------------------------------------------------- 本地直取（官方站点）
def csindex_direct_xls(symbol="000300"):
    """直取中证指数官方估值 xls，按列名解析（不信位置）。"""
    import requests
    url = (f"https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/"
           f"autofile/indicator/{symbol}indicator.xls")
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    df = pd.read_excel(io.BytesIO(r.content))
    ren = {}
    for c in df.columns:
        s = str(c)
        if s.startswith("日期"):
            ren[c] = "日期"
        elif "股息率1" in s:
            ren[c] = "股息率1"
        elif "股息率2" in s:
            ren[c] = "股息率2"
        elif "市盈率1" in s:
            ren[c] = "市盈率1"
    return df.rename(columns=ren)


LOCAL_FNS = {"csindex_direct_xls": csindex_direct_xls}


def cn_etf_aum_direct():
    """抓 KraneShares 三只中国主题 ETF 的 Net Assets（官网静态页），合计为海外中国 ETF 规模代理。"""
    import requests
    UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
    total, as_of, detail = 0.0, None, []
    for tk in ("kweb", "kba", "kure"):
        r = requests.get(f"https://kraneshares.com/etf/{tk}/", headers=UA, timeout=25)
        txt = re.sub(r"<[^>]+>", " ", r.text)
        m = re.search(r"Net Assets\s*\$([\d,]+)", txt)
        d = re.search(r"Data as of (\d{1,2})/(\d{1,2})/(\d{4})", txt)
        if not m:
            raise ValueError(f"{tk} 未解析到 Net Assets")
        v = float(m.group(1).replace(",", ""))
        total += v
        detail.append(f"{tk.upper()} ${v/1e9:.2f}B")
        if d:
            as_of = f"{d.group(3)}-{int(d.group(1)):02d}-{int(d.group(2)):02d}"
    return total, as_of, "; ".join(detail)


# ---------------------------------------------------------------- 解析器
def p_lpr(df):
    row = last_valid(df, "1年期LPR")
    d = norm_period(row["日期"])
    prev = df.dropna(subset=["1年期LPR"]).sort_values("日期").iloc[-2]
    return {"指标": "1 年期 LPR", "值": f"{float(row['1年期LPR']):.2f}%",
            "对比": f"上一期 {float(prev['1年期LPR']):.2f}%"}, {"data_period": d}


def p_m2(df):
    r = df.iloc[0]                      # 最新在前
    col = find_col(df, "M2", "同比增长")
    return {"指标": "M2 同比", "值": f"{float(r[col]):.2f}%",
            "对比": f"上一期 {float(df.iloc[1][col]):.2f}%"}, {"data_period": norm_period(r["月份"])}


def p_m1(df):
    r = df.iloc[0]
    col = find_col(df, "M1", "同比增长")
    return {"指标": "M1 同比", "值": f"{float(r[col]):.2f}%", "对比": ""}, {"data_period": norm_period(r["月份"])}


def p_tsf(df):
    r = df.iloc[-1]                     # 最旧在前
    return {"指标": "社融增量（当月）", "值": f"{float(r['社会融资规模增量']):.0f} 亿元", "对比": ""}, \
           {"data_period": norm_period(r["月份"])}


def p_fisc_dep(df):
    r = df.iloc[0]                      # 最新在前
    return {"指标": "政府存款（财政存款）", "值": f"{float(r['政府存款']):.0f} 亿元", "对比": ""}, \
           {"data_period": norm_period(r["统计时间"])}


def p_cgb10y(df):
    col = find_col(df, "中国国债收益率10年")
    d = df.dropna(subset=[col]).sort_values("日期")
    r, prev = d.iloc[-1], d.iloc[-2]
    return {"指标": "中国 10Y 国债收益率", "值": f"{float(r[col]):.4f}%",
            "对比": f"上一期 {float(prev[col]):.4f}%"}, {"data_period": norm_period(r["日期"])}


def p_dr007(df):
    col = find_col(df, "FDR007") or find_col(df, "FR007")
    d = df.dropna(subset=[col]).sort_values("date")
    r = d.iloc[-1]
    return {"指标": f"{col}（DR007 定盘代理）", "值": f"{float(r[col]):.2f}%", "对比": ""}, \
           {"data_period": norm_period(r["date"])}


def p_fx(df):
    d = df.dropna(subset=["美元"]).sort_values("日期")
    r = d.iloc[-1]
    return {"指标": "USD/CNY 中间价", "值": f"{float(r['美元']) / 100:.4f}", "对比": ""}, \
           {"data_period": norm_period(r["日期"])}


def p_div(df):
    d = df.sort_values("日期")
    r = d.iloc[-1]
    return {"指标": "沪深300 股息率", "值": f"{float(r['股息率1']):.2f}%",
            "对比": f"PE {float(r['市盈率1']):.2f}"}, {"data_period": norm_period(r["日期"])}


def p_margin(df):
    d = df.dropna(subset=["融资余额"]).sort_values("日期")
    r = d.iloc[-1]
    return {"指标": "融资余额（全市场）", "值": f"{float(r['融资余额']):.2f} 亿元", "对比": ""}, \
           {"data_period": norm_period(r["日期"])}


def p_sector_amt_old(df):
    r = df.sort_values("日期").iloc[-1]
    return {"指标": "半导体板块成交额", "值": f"{float(r['成交额']) / 1e8:.2f} 亿元", "对比": ""}, \
           {"data_period": norm_period(r["日期"])}


def p_index(df):
    date_col = "date" if "date" in df.columns else "日期"
    d = df.copy()
    d["_d"] = pd.to_datetime(d[date_col], errors="coerce")
    r = d.loc[d["_d"].idxmax()]
    return {"指标": "上证指数收盘", "值": f"{float(r['close']):.2f}", "对比": ""}, \
           {"data_period": norm_period(r[date_col])}



def p_loan_yoy(df):
    d = df.dropna(subset=["累计人民币贷款-同比"])
    r = d.iloc[-1]
    return ({"指标": "人民币贷款累计余额同比（社融替代）", "值": str(r["累计人民币贷款-同比"]), "对比": "仅贷款口径"},
            {"data_period": norm_period(r["月份"])})


def p_margin_inv(df):
    d = df.dropna(subset=["个人投资者数量"]).sort_values("日期")
    r = d.iloc[-1]
    val = float(r["个人投资者数量"])
    debt = float(r.get("有融资融券负债的投资者数量") or 0) / 1e4
    return ({"指标": "两融个人投资者数量（开户替代，窄口径）", "值": f"{val:.2f} 万户", "对比": f"有负债 {debt:.1f} 万户"},
            {"data_period": norm_period(r["日期"])})

def _hosts_of(fn):
    """探测 akshare 函数源码里内联的域名，用于判断是否直连官方站点。"""
    try:
        src = inspect.getsource(fn)
    except Exception:
        return []
    return sorted(set(re.findall(r"https?://([a-zA-Z0-9.\-]+)", src)))



def p_lhb_inst(df):
    col = find_col(df, "机构买入净额")
    total = float(df[col].fillna(0).sum()) / 1e8
    n = int(len(df))
    return ({"指标": "龙虎榜机构净买额（区间汇总）", "值": f"{total:.2f} 亿元", "对比": f"上榜 {n} 只"},
            {"data_period": norm_period(df.iloc[0].get("交易日期") or _latest_trade_day())})


def p_block_amt(df):
    if "大宗交易成交总额" in df.columns:      # sctj：全历史市场统计
        d = pd.to_datetime(df["交易日期"], errors="coerce")
        r = df.loc[d.idxmax()]
        period = norm_period(r["交易日期"])
        val = float(r["大宗交易成交总额"]) / 1e8
        # 大宗交易盘后汇总（约 18:00 后齐备）：当日未汇总完的残值不落盘，避免低报
        if period == dt.date.today().isoformat() and dt.datetime.now().hour < 18:
            raise ValueError(f"大宗交易当日盘后汇总未完成（当前 {dt.datetime.now():%H:%M}，{val:.2f} 亿），暂不落盘")
        return ({"指标": "大宗交易成交额（当日）", "值": f'{val:.2f} 亿元',
                 "对比": f'溢价占比 {float(r.get("溢价成交总额占比") or 0):.2f}%'},
                {"data_period": period})
    if "成交额" in df.columns:
        amt = df["成交额"].fillna(0)
    else:                                   # 某些窗口返回的明细表列不同，退化用 量×价
        amt = df["成交量"].fillna(0) * df["成交价"].fillna(0)
    total = float(amt.sum()) / 1e8
    d = df["交易日期"].max()
    return ({"指标": "大宗交易成交额（区间汇总）", "值": f"{total:.2f} 亿元", "对比": f"{len(df)} 笔"},
            {"data_period": norm_period(d)})


def p_block_prem(df):
    col = find_col(df, "折溢")
    if col is not None:
        prem = float(df[col].dropna().mean())
    elif "收盘价" in df.columns and "成交价" in df.columns:
        prem = float(((df["成交价"] / df["收盘价"] - 1) * 100).dropna().mean())
    else:
        raise ValueError(f"该窗口返回的表缺折溢率/收盘价列：{list(df.columns)}")
    d = df["交易日期"].max()
    return ({"指标": "大宗交易平均折溢率", "值": f"{prem:.2f}%", "对比": "相对收盘价"},
            {"data_period": norm_period(d)})


def p_breadth(df):
    items, stat_date = {}, None
    for _, r in df.iterrows():
        k, v = str(r["item"]).strip(), r["value"]
        if k == "统计日期":
            stat_date = str(v)
            continue
        try:
            items[k] = float(str(v).replace("%", ""))
        except Exception:
            pass
    up, down = items.get("上涨", 0.0), items.get("下跌", 0.0)
    total = (up + down) or 1.0
    return ({"指标": "上涨家数占比", "值": f"{up / total * 100:.1f}%", "对比": f"上涨 {int(up)} / 下跌 {int(down)}"},
            {"data_period": norm_period(stat_date or dt.date.today())})


def p_sector_conc(df):
    """板块间成交额集中度：Top5 占全部行业板块成交额的比重（须声明 Top-N）。"""
    col = find_col(df, "总成交额")
    vals = pd.to_numeric(df[col], errors="coerce").dropna()
    tot, top5 = float(vals.sum()), float(vals.sort_values(ascending=False).head(5).sum())
    return ({"指标": "板块成交额集中度", "值": f"{top5 / tot * 100:.1f}%",
             "对比": f"Top5 {top5:.0f} / 全部 {tot:.0f} 亿（N={len(vals)} 板块）"},
            {"data_period": norm_period(_trade_day_of())})


def p_turnover(df):
    col = find_col(df, "总成交额")
    total = float(pd.to_numeric(df[col], errors="coerce").dropna().sum())
    # 合理性检查：与近 60 期历史中位数比，低于 50% 视为源异常（如今日同花顺只回了部分板块）
    med = None
    try:
        rows = [json.loads(x) for x in io.open(os.path.join(ROOT, "data", "history", "MKT_TURNOVER.jsonl"),
                                               encoding="utf-8").read().splitlines() if x.strip()][1:]
        vals = [r["value"] for r in rows][-60:]
        med = st.median(vals) if vals else None
    except Exception:
        med = None
    if total <= 0 or (med and total < med * 0.5):
        raise ValueError(f"板块成交额加总 {total:.0f} 亿异常（历史中位 {med:.0f} 亿），改走备源")
    return ({"指标": "全市场成交额（板块汇总）", "值": f"{total:.2f} 亿元", "对比": f"{len(df)} 个行业板块加总"},
            {"data_period": _trade_day_of()})


def p_sector_amt(df, sector=None):
    """单板块成交额；板块名由 data/sector_target.json 决定，不写死。"""
    name = sector or _sector_target()
    r = df.sort_values("日期").iloc[-1]
    return ({"指标": f"{name}板块成交额", "值": f"{float(r['成交额']) / 1e8:.2f} 亿元", "对比": ""},
            {"data_period": norm_period(r["日期"])})


def p_margin_collateral(df):
    d = df.dropna(subset=["担保物总价值"]).sort_values("日期")
    r = d.iloc[-1]
    return ({"指标": "两融担保物总价值", "值": f'{float(r["担保物总价值"]) / 1e4:.2f} 万亿',
             "对比": f'平均维持担保比例 {float(r.get("平均维持担保比例") or 0):.1f}%'},
            {"data_period": norm_period(r["日期"])})


def p_sector_pct(df):
    d = df.sort_values("日期")
    r, prev = d.iloc[-1], d.iloc[-2]
    pct = (float(r["收盘价"]) / float(prev["收盘价"]) - 1) * 100
    return ({"指标": f"{_sector_target()}板块涨跌幅", "值": f"{pct:+.2f}%", "对比": f'前收 {float(prev["收盘价"]):.2f}'},
            {"data_period": norm_period(r["日期"])})


def p_sector_breadth(df):
    name = _sector_target()
    row = df[df["板块"].astype(str) == name]
    if row.empty:
        raise ValueError(f"行业一览里没有板块：{name}")
    r = row.iloc[0]
    up, down = float(r.get("上涨家数") or 0), float(r.get("下跌家数") or 0)
    tot = (up + down) or 1.0
    return ({"指标": f"{name}板块上涨家数占比", "值": f"{up / tot * 100:.1f}%", "对比": f"涨跌幅 {float(r.get('涨跌幅') or 0):+.2f}%"},
            {"data_period": norm_period(_trade_day_of())})


def p_sector_share(_df=None):
    """板块成交额 ÷ 全市场成交额（读缓存里的两个值，不重新请求）。"""
    a = read_json(os.path.join(CACHE_DIR, "SECTOR_AMT.json"), {}) or {}
    b = read_json(os.path.join(CACHE_DIR, "MKT_TURNOVER.json"), {}) or {}
    av = num_of(a.get("current_state", {}).get("数值"))
    bv = num_of(b.get("current_state", {}).get("数值"))
    if not av or not bv:
        raise ValueError("缺少板块成交额或全市场成交额缓存")
    return ({"指标": f"{_sector_target()}板块成交额占比", "值": f"{av / bv * 100:.2f}%",
             "对比": f"{av:.2f} / {bv:.2f} 亿"},
            {"data_period": a.get("data_period") or _latest_trade_day()})



def p_mmf_scale(df):
    col = "货币型"
    if col not in df.columns:
        raise ValueError(f"缺列 货币型：{list(df.columns)}")
    total = float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum()) / 1e4   # 亿元 → 万亿
    return ({"指标": "货币基金规模（代理现金池）", "值": f"{total:.2f} 万亿", "对比": f"{len(df.dropna(subset=[col]))} 家管理人合计"},
            {"data_period": norm_period(_trade_day_of())})


def p_cn_etf_aum(_df=None):
    total, as_of, detail = cn_etf_aum_direct()
    return ({"指标": "海外中国主题 ETF 规模（代理）", "值": f"{total/1e9:.2f} 十亿美元", "对比": detail},
            {"data_period": as_of or _latest_trade_day()})


def p_sector_val(_df=None):
    """板块 PE ÷ 沪深300 PE：按 data/sector_index_map.json 里的**所有**映射批量计算，
    结果写 data/cache/sector_val_by_sector.json（按板块名索引），同时返回目标板块那一条。"""
    import requests
    target = _sector_target()
    try:
        with io.open(os.path.join(ROOT, "data", "sector_index_map.json"), encoding="utf-8") as f:
            mapping = (json.load(f).get("map") or {})
    except Exception:
        mapping = {}
    if not mapping:
        raise ValueError("sector_index_map.json 为空")

    def pe_of(sym, cache={}):
        if sym in cache:
            return cache[sym]
        url = (f"https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/"
               f"autofile/indicator/{sym}indicator.xls")
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        df = pd.read_excel(io.BytesIO(r.content))
        col = [c for c in df.columns if "市盈率1" in str(c)][0]
        dcol = [c for c in df.columns if str(c).startswith("日期")][0]
        df = df.dropna(subset=[col]).copy()
        df["_d"] = df[dcol].astype(str)
        row = df.sort_values("_d").iloc[-1]
        cache[sym] = (float(row[col]), str(row["_d"]))
        return cache[sym]

    # 6 小时内复用上次批量结果（45 个 xls 全拉约 30 秒，不宜每次刷新都跑）
    _cache_fp = os.path.join(CACHE_DIR, "sector_val_by_sector.json")
    try:
        with io.open(_cache_fp, encoding="utf-8") as f:
            _c = json.load(f)
        _age = (dt.datetime.now() - dt.datetime.fromisoformat(_c["generated_at"])).total_seconds() / 3600
        if _age < 6 and _c.get("by_sector"):
            _by = _c["by_sector"]
            if target in _by:
                b = _by[target]
                return ({"指标": f"{target}板块估值倍数", "值": f"{b['ratio']:.2f}×",
                         "对比": f"板块 PE {b['sec_pe']:.2f} / 沪深300 PE {b['mkt_pe']:.2f}"},
                        {"data_period": b["period"]})
    except Exception:
        pass
    mkt_pe, mkt_d = pe_of("000300")
    by = {}
    for name, code in mapping.items():
        try:
            sec_pe, period = pe_of(code)
        except Exception:
            continue
        by[name] = {"ratio": round(sec_pe / mkt_pe, 2), "sec_pe": round(sec_pe, 2),
                    "mkt_pe": round(mkt_pe, 2), "period": norm_period(period)}
    with io.open(os.path.join(CACHE_DIR, "sector_val_by_sector.json"), "w", encoding="utf-8") as f:
        json.dump({"generated_at": dt.datetime.now().isoformat(timespec="seconds"), "by_sector": by},
                  f, ensure_ascii=False, indent=2)
    if target not in by:
        raise ValueError(f"板块「{target}」未配置中证指数代码")
    b = by[target]
    return ({"指标": f"{target}板块估值倍数", "值": f"{b['ratio']:.2f}×",
             "对比": f"板块 PE {b['sec_pe']:.2f} / 沪深300 PE {b['mkt_pe']:.2f}"},
            {"data_period": b["period"]})


def p_sector_inst(_df=None):
    """板块层 C5：按中证成分股过滤龙虎榜机构净买额（区间汇总）。"""
    code = _sector_index_code()
    if not code:
        raise ValueError(f"板块「{_sector_target()}」未配置中证指数代码")
    cons = ak.index_stock_cons_csindex(symbol=code)
    codes = set(str(x).zfill(6) for x in cons["成分券代码"].tolist())
    cons_date = str(cons["日期"].iloc[0]) if "日期" in cons.columns else _latest_trade_day()
    end = _ymd(None)
    start = str(int(end) - 7)
    lhb = ak.stock_lhb_jgmmtj_em(start_date=start, end_date=end)
    col = find_col(lhb, "机构买入净额")
    sub = lhb[lhb["代码"].astype(str).str.zfill(6).isin(codes)]
    total = float(sub[col].fillna(0).sum()) / 1e8
    return ({"指标": f"{_sector_target()}板块内龙虎榜机构净买额", "值": f"{total:+.2f} 亿元",
             "对比": f"成分 {len(codes)} 只中上榜 {len(sub)} 只；成分表 {cons_date}"},
            {"data_period": norm_period(_trade_day_of())})


def _macro_month(df, month_col, val_col, n=1, period_shift=0):
    """取最近 n 期月度值：月份列形如 2026年10月份 → 2026-10-01。"""
    out = []
    for _, r in df.head(n).iterrows():
        mm = "".join(ch for ch in str(r[month_col]) if ch.isdigit())
        v = str(r[val_col]).replace("%", "").strip()
        if len(mm) >= 6 and v not in ("", "nan"):
            out.append((f"{mm[:4]}-{mm[4:6]}-01", float(v)))
    return sorted(out)


def p_cpi_yoy(_df=None):
    df = ak.macro_china_cpi()
    rows = _macro_month(df, "月份", "全国-同比增长", 1)
    return ({"指标": "CPI 同比", "值": f"{rows[-1][1]:.2f}%", "对比": "国家统计局月度发布"},
            {"data_period": rows[-1][0]})


def p_ppi_yoy(_df=None):
    df = ak.macro_china_ppi()
    rows = _macro_month(df, "月份", "当月同比增长", 1)
    return ({"指标": "PPI 同比", "值": f"{rows[-1][1]:.2f}%", "对比": "国家统计局月度发布"},
            {"data_period": rows[-1][0]})


def p_pmi(_df=None):
    df = ak.macro_china_pmi()
    rows = _macro_month(df, "月份", "制造业-指数", 1)
    return ({"指标": "制造业 PMI", "值": f"{rows[-1][1]:.2f}", "对比": "国家统计局月度发布；50 为荣枯线"},
            {"data_period": rows[-1][0]})


def p_gdp_yoy(_df=None):
    df = ak.macro_china_gdp()
    r = df.iloc[0]
    q = str(r["季度"])
    mm = re.findall(r"\d+", q)
    per = f"{mm[0]}-12-31" if "1-4" in q or "全年" in q else (f"{mm[0]}-09-30" if "1-3" in q else (f"{mm[0]}-06-30" if "1-2" in q else f"{mm[0]}-03-31"))
    return ({"指标": "GDP 同比", "值": f"{float(r['国内生产总值-同比增长']):.2f}%", "对比": q},
            {"data_period": per})


def p_ip_yoy(_df=None):
    df = ak.macro_china_industrial_value_added()
    r = df.iloc[-1]
    mm = "".join(ch for ch in str(r["月份"]) if ch.isdigit())
    return ({"指标": "规模以上工业增加值同比", "值": f"{float(r['同比增长']):.2f}%", "对比": str(r["月份"])},
            {"data_period": f"{mm[:4]}-{mm[4:6]}-01"})


def p_retail_yoy(_df=None):
    df = ak.macro_china_consumer_goods_retail()
    r = df.iloc[0]
    mm = "".join(ch for ch in str(r["月份"]) if ch.isdigit())
    return ({"指标": "社会消费品零售总额同比", "值": f"{float(r['同比增长']):.2f}%", "对比": str(r["月份"])},
            {"data_period": f"{mm[:4]}-{mm[4:6]}-01"})


def p_fai_yoy(_df=None):
    df = ak.macro_china_fixed_asset_investment()
    r = df.iloc[0]
    mm = "".join(ch for ch in str(r["月份"]) if ch.isdigit())
    return ({"指标": "固定资产投资同比", "值": f"{float(r['同比增长']):.2f}%", "对比": str(r["月份"])},
            {"data_period": f"{mm[:4]}-{mm[4:6]}-01"})


def p_house_price_yoy(_df=None):
    df = ak.macro_china_new_house_price()
    last = df["日期"].max()
    d = df[df["日期"] == last]
    v = float(d["新建商品住宅价格指数-同比"].astype(float).mean())
    v = v - 100 if v > 50 else v          # 指数形态 101.8 → +1.8%
    return ({"指标": "新建商品住宅价格指数同比（70 城均值）", "值": f"{v:.2f}%",
             "对比": f"{last} · {len(d)} 城"}, {"data_period": str(last)[:10]})


def p_realestate(_df=None):
    df = ak.macro_china_real_estate()
    df = df.dropna(subset=["最新值"]).sort_values("日期")
    r = df.iloc[-1]
    return ({"指标": "国房景气指数", "值": f"{float(r['最新值']):.2f}", "对比": str(r["日期"])[:10]},
            {"data_period": str(r["日期"])[:7] + "-01"})


def p_elec_yoy(_df=None):
    df = ak.macro_china_society_electricity()
    df = df.copy()
    df["t"] = df["统计时间"].astype(str).str.replace(".", "-", regex=False)
    r = df.sort_values("t").iloc[-1]
    mm = "".join(ch for ch in str(r["统计时间"]) if ch.isdigit())
    return ({"指标": "全社会用电量同比（能源生产代理）", "值": f"{float(r['全社会用电量同比']):.2f}%",
             "对比": str(r["统计时间"])}, {"data_period": f"{mm[:4]}-{int(mm[4:6]):02d}-01"})


def p_turnover_tx(_df=None):
    """全市场成交额备源：沪指 + 深成指成交额合计（与 history.py 同口径，实测与两市成交额吻合）。"""
    import datetime as _dt
    total, day = 0.0, None
    end = _ymd(None)
    start = (dt.date.today() - dt.timedelta(days=120)).strftime("%Y%m%d")
    for sym in ("sh000001", "sz399001"):
        df = ak.index_zh_daily_tx(symbol=sym, start_date=start, end_date=end)
        df = df.dropna(subset=["amount"])
        r = df.iloc[-1]
        total += float(r["amount"]) / 1e8
        day = str(r["date"])[:10]
    return ({"指标": "两市成交额（沪指+深成指合计）", "值": f"{total:.2f} 亿元", "对比": day},
            {"data_period": day})


def _cninfo_search(keyword, start, end, page_size=1):
    """巨潮全文检索：返回 (总条数, 前几条标题)。法定披露平台，可作官方源候选。"""
    import requests
    url = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
    payload = {"pageNum": 1, "pageSize": page_size, "column": "szse", "tabName": "fulltext",
               "searchkey": keyword, "seDate": f"{start}~{end}", "sortName": "", "sortType": "",
               "isHLtitle": "true"}
    r = requests.post(url, data=payload, timeout=25,
                      headers={"User-Agent": "Mozilla/5.0", "Referer": "http://www.cninfo.com.cn/"})
    j = r.json() or {}
    total = int(j.get("totalRecordNum") or 0)
    titles = [(a.get("announcementTitle") or "").replace("<em>", "").replace("</em>", "")[:40]
              for a in (j.get("announcements") or [])]
    return total, titles


def p_insider_net(_df=None):
    """产业资本增减持：近 30 天「减持」与「增持」公告条数之差（正=减持公告更多）。"""
    import datetime as _dt
    end = _dt.date.today()
    start = end - _dt.timedelta(days=30)
    cut, ctitles = _cninfo_search("减持", start.isoformat(), end.isoformat())
    bct, btitles = _cninfo_search("增持", start.isoformat(), end.isoformat())
    net = cut - bct
    return ({"指标": "产业资本增减持（公告条数口径）",
             "值": f"{net:+d} 条",
             "对比": f"近 30 天 减持公告 {cut} 条 / 增持公告 {bct} 条（巨潮全文检索）"},
            {"data_period": _trade_day_of()})


def p_cgb_official(_df=None):
    """中债登官方收益率曲线（到期）：直连 ycDetail 取 10 年期。

    实测 workTime 参数不影响返回值——接口始终回最新一条曲线，
    因此数据期按抓取当日交易日记录，历史需逐日累积。
    """
    import requests
    u = "https://yield.chinabond.com.cn/cbweb-mn/yc/ycDetail"
    p = {"ycDefIds": "2c9081e50a2f9606010a3068cae70001", "zblx": "txy",
         "workTime": _trade_day_of(), "dxbj": "", "qxlx": "", "yqqxN": "", "yqqxK": "",
         "wrjxCBFlag": "0", "locale": ""}
    r = requests.post(u, params=p, timeout=25, verify=False,
                      headers={"User-Agent": "Mozilla/5.0",
                               "Referer": "https://yield.chinabond.com.cn/cbweb-mn/yield_main"})
    r.encoding = r.apparent_encoding or "utf-8"
    txt = re.sub(r"<[^>]+>", " ", r.text)
    m = re.search(r"10\.0y\s+([0-9.]+)", txt)
    if not m:
        raise ValueError("中债页面未解析到 10 年期数值")
    v = float(m.group(1))
    if not (0.5 < v < 10):
        raise ValueError(f"中债 10Y 数值异常：{v}")
    return ({"指标": "中债国债收益率曲线（到期）· 10 年", "值": f"{v:.4f}%",
             "对比": "中债登官方 ycDetail 曲线"}, {"data_period": _trade_day_of()})


def p_margin_sz_official(_df=None):
    """深交所官方两融汇总（融资融券交易总量）：直连 ShowReport 报表 1837_xxpl。

    T+1 披露：当天晚上通常还没有当日数据 → 从交易日往前回退，取最近有数据的一天。
    单位：亿元。
    """
    import requests
    u = "http://www.szse.cn/api/report/ShowReport/data"
    import datetime as _dt
    d = _dt.date.fromisoformat(_trade_day_of())
    last_err = None
    for _ in range(8):
        if d.weekday() < 5:
            p = {"SHOWTYPE": "JSON", "CATALOGID": "1837_xxpl", "TABKEY": "tab1", "PAGENO": 1,
                 "txtDate": d.isoformat(), "random": "0.5"}
            try:
                r = requests.get(u, params=p, timeout=25,
                                 headers={"User-Agent": "Mozilla/5.0", "Referer": "http://www.szse.cn/"})
                j = r.json() or []
                rows = (j[0].get("data") or []) if isinstance(j, list) and j else []
            except Exception as e:
                last_err = e
                rows = []
            if rows and len(rows) == 1:
                row = rows[0]
                def num(k):
                    return float(str(row.get(k) or 0).replace(",", ""))
                fin = num("jrrzye")
                if 100 < fin < 100000:
                    return ({"指标": "深市融资余额（交易所官方）", "值": f"{fin:,.2f} 亿元",
                             "对比": f"融券余额 {num('jrrjye'):,.2f} 亿；两融合计 {num('jrrzrjye'):,.2f} 亿（T+1 披露）"},
                            {"data_period": d.isoformat()})
        d -= _dt.timedelta(days=1)
    raise ValueError(f"深交所两融报表近 8 天无数据{'' if last_err is None else '：' + type(last_err).__name__}")



def _sw_codes_of_target():
    """目标板块 → 申万二级代码列表（支持一级行业按 parent 展开）。"""
    try:
        with io.open(os.path.join(ROOT, "data", "sector_target.json"), encoding="utf-8-sig") as f:
            name = json.load(f).get("name", "半导体")
        with io.open(os.path.join(ROOT, "data", "sw", "sectors.json"), encoding="utf-8") as f:
            secs = (json.load(f).get("sectors") or [])
    except Exception:
        return []
    alias = {"医药": "医药生物", "化工": "基础化工", "电力": "公用事业", "券商": "非银金融", "保险": "非银金融"}
    n = alias.get(name, name)
    exact = [x["code"] for x in secs if x.get("name") == n]
    return exact or [x["code"] for x in secs if x.get("parent") == n]


def p_sector_lhb_sw(_df=None):
    """板块内龙虎榜净买额：全市场龙虎榜明细 × 申万二级成分（多板块批量）。"""
    import akshare as ak
    import datetime as _dt
    end = _dt.date.fromisoformat(_trade_day_of())
    start = end - _dt.timedelta(days=7)
    try:
        df = ak.stock_lhb_detail_em(start_date=start.strftime("%Y%m%d"), end_date=end.strftime("%Y%m%d"))
    except Exception as e:
        raise RuntimeError(f"龙虎榜明细失败：{type(e).__name__}")
    net = {}
    for _, r in df.iterrows():
        code = str(r.get("代码") or "").zfill(6)
        try:
            amt = float(r.get("龙虎榜净买额") or 0)
        except Exception:
            continue
        net[code] = net.get(code, 0.0) + amt
    with io.open(os.path.join(ROOT, "data", "sw", "constituents.json"), encoding="utf-8") as f:
        cons = (json.load(f).get("sectors") or {})
    by = {}
    for cid, meta in cons.items():
        codes = meta.get("codes") or []
        vals = [net[c] for c in codes if c in net]
        if vals:
            by[cid] = {"name": meta.get("name"), "net": round(sum(vals) / 1e8, 2), "n": len(vals)}
    with io.open(os.path.join(CACHE_DIR, "sector_lhb_by_sector.json"), "w", encoding="utf-8") as f:
        json.dump({"generated_at": dt.datetime.now().isoformat(timespec="seconds"),
                   "data_period": _trade_day_of(), "by_sector": by}, f, ensure_ascii=False, indent=2)
    target = _sw_codes_of_target()
    if not target:
        raise ValueError("目标板块没有申万成分")
    tot = sum(by.get(c, {}).get("net", 0) for c in target)
    n = sum(by.get(c, {}).get("n", 0) for c in target)
    return ({"指标": "板块内龙虎榜净买额（申万成分口径）", "值": f"{tot:+.2f} 亿元",
             "对比": f"{n} 只上榜（近 7 日累计）"}, {"data_period": _trade_day_of()})


# ---------------------------------------------------------------- 指标声明
SPECS = [
    dict(id="POL_LPR", channel="C1", subject="政策", freq="不定期", value_kind="level", layer="市场", tier_default="C",
         providers=[("akshare/em", ["interest_rate_lpr_em"], p_lpr)],
         official_source="中国货币网·LPR报价（全国银行间同业拆借中心）", official_url="https://www.chinamoney.com.cn/chinese/bklpr/",
         proves="政策利率设定值及其变动", does_not_prove="不说明传导效果"),
    dict(id="MKT_M2_YOY", channel="C2", subject="公共池", freq="月", value_kind="ratio", layer="市场", tier_default="C",
         providers=[("akshare/em", ["macro_china_money_supply_em"], p_m2),
                    ("akshare/sina", ["macro_china_money_supply_sina", "macro_china_money_supply"], p_m2)],
         official_source="中国人民银行《金融统计数据报告》", official_url="http://www.pbc.gov.cn/diaochatongjisi/116219/116319/index.html",
         proves="货币总量同比为正/负", does_not_prove="不证明资金入市"),
    dict(id="MKT_M1_YOY", channel="C2", subject="公共池", freq="月", value_kind="ratio", layer="市场", tier_default="C",
         providers=[("akshare/em", ["macro_china_money_supply_em"], p_m1),
                    ("akshare/sina", ["macro_china_money_supply_sina", "macro_china_money_supply"], p_m1)],
         official_source="中国人民银行《金融统计数据报告》", official_url="http://www.pbc.gov.cn/diaochatongjisi/116219/116319/index.html",
         proves="狭义货币同比", does_not_prove="不证明活化程度的变化原因"),
    dict(id="MKT_TSF_YOY", channel="C2", subject="公共池", freq="月", value_kind="ratio", layer="市场", tier_default="C",
         providers=[("akshare", ["macro_china_social_financing", "macro_china_shrzgm"], p_tsf)],
         official_source="中国人民银行《社会融资规模统计数据报告》", official_url="http://www.pbc.gov.cn/diaochatongjisi/116219/116319/index.html",
         proves="信用扩张的当月增量", does_not_prove="不等于资金进入股市"),
    dict(id="FISC_DEP", channel="C2", subject="政策", freq="月", value_kind="level", layer="市场", tier_default="C",
         providers=[("akshare/pbc", ["macro_china_central_bank_balance"], p_fisc_dep)],
         official_source="中国人民银行《货币当局资产负债表》", official_url="http://www.pbc.gov.cn/diaochatongjisi/116219/116317/index.html",
         proves="财政资金停在央行账上的规模", does_not_prove="不说明财政投放的方向"),
    dict(id="MKT_CGB10Y", channel="C3", subject="公共池", freq="日", value_kind="level", layer="市场", tier_default="C",
         providers=[("calc", ["__cgb__"], p_cgb_official),
                    ("akshare/em", ["bond_zh_us_yield_em", "bond_zh_us_rate"], p_cgb10y)],
         official_source="中债·国债收益率曲线（中央国债登记结算）", official_url="https://yield.chinabond.com.cn/",
         proves="长端无风险利率水平", does_not_prove="不说明估值会重估"),
    dict(id="MKT_DR007", channel="C3", subject="公共池", freq="日", value_kind="level", layer="市场", tier_default="C",
         providers=[("akshare/cfets", ["interest_rate_repo_hist_cm", "repo_rate_hist"], p_dr007)],
         official_source="同业拆借中心·回购定盘利率", official_url="https://www.chinamoney.com.cn/chinese/bkfrr/",
         proves="短端资金批发价格", does_not_prove="不等于长端利率同向"),
    dict(id="FX_CNY_MID", channel="C3", subject="公共池", freq="日", value_kind="level", layer="市场", tier_default="C",
         providers=[("akshare/safe", ["fx_central_parity_safe", "currency_boc_safe"], p_fx)],
         official_source="中国外汇交易中心·人民币汇率中间价", official_url="https://www.chinamoney.com.cn/chinese/bkccpr/",
         proves="人民币对美元中间价", does_not_prove="不说明外资流向"),
    dict(id="MKT_DIV_YIELD", channel="C3", subject="公共池", freq="日", value_kind="level", layer="市场", tier_default="C",
         providers=[("direct/csindex", ["csindex_direct_xls"], p_div),
                    ("akshare/csindex", ["index_value_csindex"], p_div)],
         official_source="中证指数有限公司·指数估值", official_url="https://www.csindex.com.cn/",
         proves="权益的现金回报率", does_not_prove="不说明相对债券的吸引力结论"),
    dict(id="MKT_MARGIN_BAL", channel="C4", subject="散户", freq="日", value_kind="level", layer="市场", tier_default="C",
         providers=[("akshare/exchange", ["stock_margin_account_info"], p_margin)],
         official_source="沪深交易所·融资融券汇总", official_url="http://www.sse.com.cn/market/othersdata/margin/sum/",
         proves="场内杠杆存量", does_not_prove="不说明是新资金"),
    dict(id="SECTOR_AMT", channel="C6", subject="公共池", freq="日", value_kind="level", layer="板块", tier_default="C",
         providers=[("akshare/ths", ["stock_board_industry_index_ths"], p_sector_amt)],
         official_source="同花顺板块指数（底层为交易所行情，聚合口径）", official_url="https://q.10jqka.com.cn/thshy/",
         proves="板块成交额（用于份额与结构）", does_not_prove="不说明资金流入"),
    dict(id="IDX_DAILY", channel="C6", subject="公共池", freq="日", value_kind="price", layer="市场", tier_default="C",
         providers=[("akshare/tx", ["index_zh_daily_tx"], p_index),
                    ("akshare/sina", ["index_zh_daily_sina", "stock_zh_index_daily"], p_index),
                    ("akshare/em", ["index_zh_daily_em"], p_index)],
         official_source="上海证券交易所·上证指数", official_url="http://www.sse.com.cn/market/price/trends/",
         proves="指数收盘（仅数据层）", does_not_prove="不进入呈现；只用于收益率计算"),
    dict(id="MKT_RMB_LOAN_YOY", channel="C2", subject="公共池", freq="月", value_kind="ratio", layer="市场", tier_default="C",
         providers=[("akshare/ths", ["macro_china_rmb_loan_ths"], p_loan_yoy)],
         official_source="中国人民银行《金融机构信贷收支表》（同花顺整理）", official_url="http://www.pbc.gov.cn/diaochatongjisi/116219/116319/index.html",
         proves="信用扩张（仅人民币贷款口径）", does_not_prove="不等于社融存量同比，仅同属性窄口径替代"),
    dict(id="RTL_MARGIN_INVESTORS", channel="C5", subject="散户", freq="日", value_kind="count", layer="市场", tier_default="C",
         providers=[("akshare/exchange", ["stock_margin_account_info"], p_margin_inv)],
         official_source="沪深交易所·两融投资者统计", official_url="http://www.sse.com.cn/market/othersdata/margin/sum/",
         proves="杠杆散户的户数变化（窄口径）", does_not_prove="不等于新增开户数，仅覆盖两融投资者"),
    dict(id="INST_LHB_NET", channel="C5", subject="机构", freq="日", value_kind="level", layer="市场", tier_default="C",
         providers=[("akshare/em", ["stock_lhb_jgmmtj_em"], p_lhb_inst)],
         official_source="东方财富·龙虎榜机构买卖统计（原始披露为交易所）", official_url="https://data.eastmoney.com/stock/lhb.html",
         proves="机构席位在龙虎榜上的净买方向与规模", does_not_prove="仅覆盖上榜个股，不代表全市场机构行为"),
    dict(id="INST_BLOCK_AMT", channel="C5", subject="机构", freq="日", value_kind="level", layer="市场", tier_default="C",
         providers=[("akshare/em", ["stock_dzjy_sctj", "stock_dzjy_mrmx"], p_block_amt)],
         official_source="东方财富·大宗交易每日明细（原始披露为交易所）", official_url="https://data.eastmoney.com/dzjy/mrmx.html",
         proves="大宗交易的规模", does_not_prove="不说明买卖双方意图"),
    dict(id="INST_BLOCK_PREM", channel="C5", subject="机构", freq="日", value_kind="ratio", layer="市场", tier_default="C",
         providers=[("akshare/em", ["stock_dzjy_mrtj", "stock_dzjy_mrmx"], p_block_prem)],
         official_source="东方财富·大宗交易每日明细（原始披露为交易所）", official_url="https://data.eastmoney.com/dzjy/mrmx.html",
         proves="大宗成交相对收盘价的折溢价", does_not_prove="不说明接盘方性质"),
    dict(id="MKT_BREADTH", channel="C6", subject="公共池", freq="日", value_kind="count", layer="市场", tier_default="C",
         providers=[("akshare/legu", ["stock_market_activity_legu"], p_breadth)],
         official_source="乐咕乐股·市场活跃度（交易所涨跌家数口径）", official_url="https://legulegu.com/stockdata/market-activity",
         proves="当日上涨家数占全部有交易家数的比例", does_not_prove="不说明上涨幅度与结构"),
    dict(id="SECTOR_AMT_CONC", channel="C6", subject="公共池", freq="日", value_kind="ratio", layer="板块", tier_default="C",
         providers=[("akshare/ths", ["stock_board_industry_summary_ths"], p_sector_conc)],
         official_source="同花顺行业板块一览（交易所行情聚合，快照）", official_url="https://q.10jqka.com.cn/thshy/",
         proves="成交额在各行业板块之间的集中程度（须声明 Top-N）", does_not_prove="不说明资金去向与轮动方向"),
    dict(id="MKT_TURNOVER", channel="C6", subject="公共池", freq="日", value_kind="level", layer="市场", tier_default="C",
         providers=[("akshare/ths", ["stock_board_industry_summary_ths"], p_turnover),
                    ("calc", ["__turnover_tx__"], p_turnover_tx)],
         official_source="同花顺行业板块一览加总（交易所行情）；备源为沪深指数成交额合计", official_url="https://q.10jqka.com.cn/thshy/",
         proves="全市场当日成交额（板块加总口径；备源为沪深指数成交额合计）", does_not_prove="不说明资金方向"),
    dict(id="MKT_MARGIN_COLLATERAL", channel="C4", subject="散户", freq="日", value_kind="level", layer="市场", tier_default="C",
         providers=[("akshare/exchange", ["stock_margin_account_info"], p_margin_collateral)],
         official_source="交易所两融汇总·担保物总价值", official_url="http://www.sse.com.cn/market/othersdata/margin/sum/",
         proves="两融账户抵押品（现金+证券）总量", does_not_prove="不等于场内现金池"),
    dict(id="MKT_MARGIN_DEP", channel="C4", subject="公共池", freq="月", value_kind="level", layer="市场", tier_default="C",
         manual=True, providers=[],
         official_source="投保基金·证券市场交易结算资金余额（人工月度）", official_url="http://www.sipf.com.cn/",
         proves="场内现金池（客户结算资金）", does_not_prove="不等于杠杆，也不等于成交额"),
    dict(id="MKT_NORTH_AMT", channel="C5", subject="外部", freq="日", value_kind="level", layer="市场", tier_default="C",
         manual=True, providers=[],
         official_source="北向盘后成交总额（官方 2024-08 起停止日度披露）", official_url="http://www.sse.com.cn/",
         proves="外部资金成交规模", does_not_prove="无净额、无买卖拆分"),
    dict(id="SECTOR_SHARE", channel="C2", subject="公共池", freq="日", value_kind="ratio", layer="板块", tier_default="C",
         providers=[("calc", ["__share__"], p_sector_share)],
         official_source="自算：板块成交额 ÷ 全市场成交额", official_url="",
         proves="该板块在全市场成交中的份额", does_not_prove="不说明资金流向量"),
    dict(id="SECTOR_PCT", channel="C6", subject="公共池", freq="日", value_kind="return", layer="板块", tier_default="C",
         providers=[("akshare/ths", ["stock_board_industry_index_ths"], p_sector_pct)],
         official_source="同花顺板块指数（交易所行情）", official_url="https://q.10jqka.com.cn/thshy/",
         proves="板块当日涨跌幅", does_not_prove="不说明板块内个股结构"),
    dict(id="SECTOR_BREADTH", channel="C6", subject="公共池", freq="日", value_kind="ratio", layer="板块", tier_default="C",
         providers=[("akshare/ths", ["stock_board_industry_summary_ths"], p_sector_breadth)],
         official_source="同花顺行业板块一览（交易所行情）", official_url="https://q.10jqka.com.cn/thshy/",
         proves="板块内上涨家数占比", does_not_prove="不说明上涨幅度"),
    dict(id="MKT_MMF_SCALE", channel="C4", subject="公共池", freq="月", value_kind="level", layer="市场", tier_default="C",
         providers=[("akshare/em", ["fund_aum_hist_em"], p_mmf_scale)],
         official_source="中基协口径·货币基金规模（经东财汇总）", official_url="https://www.amac.org.cn/",
         proves="闲钱停放在货币基金的总规模（保证金停发后的代理）", does_not_prove="不等于客户保证金，也不等于场内现金"),
    dict(id="EXT_CN_ETF_AUM", channel="C5", subject="外部", freq="日", value_kind="level", layer="市场", tier_default="C",
         providers=[("direct/kraneshares", ["__cn_etf_aum__"], p_cn_etf_aum)],
         official_source="KraneShares 官网·KWEB/KBA/KURE 的 Net Assets（基金披露）", official_url="https://kraneshares.com/etf/kweb/",
         proves="海外上市中国主题 ETF 的资产规模（外资配置中国的存量代理）", does_not_prove="不等于北向资金，也不等于外资对 A 股的净买入"),
    dict(id="SECTOR_VAL", channel="C3", subject="公共池", freq="日", value_kind="ratio", layer="板块", tier_default="C",
         providers=[("calc", ["__sector_val__"], p_sector_val)],
         official_source="中证指数·行业指数估值（板块 PE）与沪深300 PE", official_url="https://www.csindex.com.cn/",
         proves="板块估值相对全市场的倍数（基准：沪深300）", does_not_prove="不说明估值会回归；差值与分位归比价层"),
    dict(id="SECTOR_INST_FLOW", channel="C5", subject="机构", freq="日", value_kind="level", layer="板块", tier_default="C",
         providers=[("calc", ["__sector_inst__"], p_sector_inst)],
         official_source="中证指数成分 + 龙虎榜机构买卖统计（按成分过滤加总）", official_url="https://www.csindex.com.cn/",
         proves="板块成分股在龙虎榜上的机构净买方向与规模", does_not_prove="仅覆盖上榜个股，不代表板块内全部机构行为"),
    dict(id="MKT_CPI_YOY", channel="背景", subject="公共池", freq="月", value_kind="ratio", layer="市场", tier_default="C",
         providers=[("calc", ["__cpi__"], p_cpi_yoy)],
         official_source="国家统计局·居民消费价格指数", official_url="https://www.stats.gov.cn/sj/zxfb/",
         proves="CPI 同比水平", does_not_prove="不说明通胀预期或政策取向"),
    dict(id="MKT_PPI_YOY", channel="背景", subject="公共池", freq="月", value_kind="ratio", layer="市场", tier_default="C",
         providers=[("calc", ["__ppi__"], p_ppi_yoy)],
         official_source="国家统计局·工业生产者出厂价格指数", official_url="https://www.stats.gov.cn/sj/zxfb/",
         proves="PPI 同比水平", does_not_prove="不说明企业盈利或政策取向"),
    dict(id="MKT_PMI", channel="背景", subject="公共池", freq="月", value_kind="level", layer="市场", tier_default="C",
         providers=[("calc", ["__pmi__"], p_pmi)],
         official_source="国家统计局·采购经理指数", official_url="https://www.stats.gov.cn/sj/zxfb/",
         proves="制造业 PMI 水平（50 为荣枯线）", does_not_prove="不说明景气变化方向"),
    dict(id="MKT_GDP_YOY", channel="背景", subject="公共池", freq="季", value_kind="ratio", layer="市场", tier_default="C",
         providers=[("calc", ["__gdp__"], p_gdp_yoy)],
         official_source="国家统计局·国内生产总值", official_url="https://www.stats.gov.cn/sj/zxfb/",
         proves="GDP 同比水平", does_not_prove="不说明增长质量"),
    dict(id="MKT_IP_YOY", channel="背景", subject="公共池", freq="月", value_kind="ratio", layer="市场", tier_default="C",
         providers=[("calc", ["__ip__"], p_ip_yoy)],
         official_source="国家统计局·规模以上工业增加值", official_url="https://www.stats.gov.cn/sj/zxfb/",
         proves="工业生产同比", does_not_prove="不说明企业利润"),
    dict(id="MKT_RETAIL_YOY", channel="背景", subject="公共池", freq="月", value_kind="ratio", layer="市场", tier_default="C",
         providers=[("calc", ["__retail__"], p_retail_yoy)],
         official_source="国家统计局·社会消费品零售总额", official_url="https://www.stats.gov.cn/sj/zxfb/",
         proves="消费同比", does_not_prove="不说明消费结构"),
    dict(id="MKT_FAI_YOY", channel="背景", subject="公共池", freq="月", value_kind="ratio", layer="市场", tier_default="C",
         providers=[("calc", ["__fai__"], p_fai_yoy)],
         official_source="国家统计局·固定资产投资", official_url="https://www.stats.gov.cn/sj/zxfb/",
         proves="投资同比", does_not_prove="不说明投资效率"),
    dict(id="MKT_HOUSE_PRICE_YOY", channel="背景", subject="公共池", freq="月", value_kind="ratio", layer="市场", tier_default="C",
         providers=[("calc", ["__house__"], p_house_price_yoy)],
         official_source="国家统计局·70 个大中城市新建商品住宅销售价格指数", official_url="https://www.stats.gov.cn/sj/zxfb/",
         proves="房价同比（70 城均值）", does_not_prove="不说明成交量"),
    dict(id="MKT_REALESTATE", channel="背景", subject="公共池", freq="月", value_kind="level", layer="市场", tier_default="C",
         providers=[("calc", ["__re__"], p_realestate)],
         official_source="国家统计局·国房景气指数", official_url="https://www.stats.gov.cn/sj/zxfb/",
         proves="房地产景气水平（国房景气指数，官方最后披露 2025-12）", does_not_prove="不说明房价；该指数已停止更新"),
    dict(id="MKT_ELEC_YOY", channel="背景", subject="公共池", freq="月", value_kind="ratio", layer="市场", tier_default="C",
         providers=[("calc", ["__elec__"], p_elec_yoy)],
         official_source="国家能源局·全社会用电量", official_url="https://www.nea.gov.cn/",
         proves="用电量同比（能源生产同属性代理）", does_not_prove="不等于能源生产总量"),
    dict(id="INST_INSIDER_NET", channel="C5", subject="公共池", freq="日", value_kind="count", layer="市场", tier_default="C",
         providers=[("calc", ["__insider__"], p_insider_net)],
         official_source="巨潮资讯·上市公司公告全文检索（证监会指定披露平台）", official_url="http://www.cninfo.com.cn/",
         official_hosts=["www.cninfo.com.cn"],
         proves="近 30 天产业资本增减持公告条数之差", does_not_prove="不说明增减持金额与方向强度；条数口径"),
    dict(id="MKT_MARGIN_BAL_SZ", channel="C4", subject="公共池", freq="日", value_kind="level", layer="市场", tier_default="C",
         providers=[("calc", ["__margin_sz__"], p_margin_sz_official)],
         official_source="深圳证券交易所·融资融券交易总量（ShowReport 1837_xxpl）",
         official_url="http://www.szse.cn/disclosure/margin/margin/index.html",
         official_hosts=["www.szse.cn"],
         proves="深市当日融资余额（官方汇总）", does_not_prove="不含沪市；不等于全市场两融余额"),
    dict(id="SECTOR_LHB_SW", channel="C5", subject="公共池", freq="日", value_kind="level", layer="板块", tier_default="C",
         providers=[("calc", ["__lhb_sw__"], p_sector_lhb_sw)],
         official_source="交易所·龙虎榜明细 × 申万二级成分（自算汇总）",
         official_url="https://data.eastmoney.com/stock/lhb.html",
         proves="板块内上榜个股的龙虎榜净买额（申万成分口径）", does_not_prove="只覆盖上榜个股"),
]

SPEC_MAP = {s["id"]: s for s in SPECS}

OFFICIAL_DOMAINS = ("pbc.gov.cn", "chinamoney.com.cn", "chinabond.com.cn", "csindex.com.cn", "sse.com.cn",
                    "szse.cn", "safe.gov.cn", "stats.gov.cn", "mof.gov.cn", "csrc.gov.cn", "chinaclear.cn")


# ---------------------------------------------------------------- 抓取
def _ymd(s):
    """把 2026-11-21 / 20261121 / None 统一成 YYYYMMDD（部分接口只认紧凑格式）。"""
    s = s or dt.date.today().isoformat()
    return str(s).replace("-", "")[:8]


def call_kwargs(spec, as_of):
    if spec["id"] == "IDX_DAILY":
        # 腾讯源默认 symbol 是 sz980017，必须显式指定
        return {"symbol": "sh000001"}
    if spec["id"] == "MKT_MMF_SCALE":
        return {"year": str(dt.date.today().year)}
    if spec["id"] == "MKT_CGB10Y":
        return {"start_date": "20260101"}
    if spec["id"] in ("SECTOR_PCT",):
        return {"symbol": _sector_target(), "start_date": "20260901", "end_date": _ymd(as_of)}
    if spec["id"] == "SECTOR_AMT":
        return {"symbol": _sector_target(), "start_date": "20260901", "end_date": _ymd(as_of)}
    if spec["id"] == "INST_BLOCK_AMT":
        return {}                     # 市场统计：返回全历史
    if spec["id"] in ("INST_LHB_NET", "INST_BLOCK_PREM"):
        end = _ymd(as_of)
        start = str(int(end[:8]) - 7)
        return {"start_date": start, "end_date": end}
    if spec["id"] == "MKT_DR007":
        return {"start_date": "20261001", "end_date": _ymd(as_of)}
    return {}


def fetch_one(spec, args, as_of):
    if spec.get("manual"):
        m = read_manual(spec["id"])
        if not m:
            return {"indicator_id": spec["id"], "source": None,
                    "errors": ["人工录入未填（data/manual/）"], "missing_type": "not_available",
                    "fetched_at": dt.datetime.now().isoformat(timespec="seconds")}
        return {"indicator_id": spec["id"], "source": "manual", "function": None,
                "current_state": {"指标": spec["official_source"].split("·")[0], "数值": f"{m['value']}",
                                  "数据所属期": m.get("data_period", "")},
                "data_period": m.get("data_period", ""), "release_date": m.get("data_period", ""),
                "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
                "fallback_flag": False, "fallback_path": None, "rows": 1,
                "official_source": spec.get("official_source"), "official_url": spec.get("official_url")}
    if not args.no_cache:
        cached = read_json(os.path.join(CACHE_DIR, spec["id"] + ".json"))
        if cached and cached.get("fetched_at"):
            age_h = (dt.datetime.now() - dt.datetime.fromisoformat(cached["fetched_at"])).total_seconds() / 3600
            if age_h < TTL_HOURS.get(spec["freq"], 24):
                return dict(cached, cache_hit=True)

    errors = []
    for source, aliases, parser in spec["providers"]:
        if source in ("calc", "direct/kraneshares"):                      # 纯计算指标：不发请求，直接算
            try:
                cur, meta = parser(None)
                rec = {"indicator_id": spec["id"], "source": source, "function": None,
                       "current_state": {"指标": cur["指标"], "数值": cur["值"], "数据所属期": meta["data_period"]},
                       "data_period": meta["data_period"], "release_date": meta["data_period"],
                       "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
                       "fallback_flag": bool(errors), "fallback_path": "; ".join(errors) if errors else None,
                       "rows": 0, "official_source": spec.get("official_source"),
                       "official_url": spec.get("official_url")}
                write_json(os.path.join(CACHE_DIR, spec["id"] + ".json"), rec)
                return rec
            except Exception as e:
                errors.append(f"calc: {type(e).__name__}: {str(e)[:60]}")
                continue
        name, fn = resolve(aliases)
        if fn is None:
            errors.append(f"{source}: 无可用函数")
            continue
        for attempt in (1, 2, 3):
            try:
                throttled(source)
                df = fn(**call_kwargs(spec, as_of))
                if df is None or len(df) == 0:
                    errors.append(f"{source}: 空数据")
                    break
                cur, meta = parser(df)
                # 通用「上一期」提取：把同一解析器作用在去掉最新一行的子表上，
                # 若得到的所属期更早，就当作前一可比期（无需要求每个解析器单独实现）。
                prev = {}
                for alt in (df.iloc[1:], df.iloc[:-1]):
                    if len(alt) == 0:
                        continue
                    try:
                        pcur, pmeta = parser(alt)
                    except Exception:
                        continue
                    if str(pmeta.get("data_period", "")) and str(pmeta["data_period"]) < str(meta["data_period"]):
                        prev = {"prev_period": pmeta["data_period"], "prev_value": pcur.get("值")}
                        break
                # calc 类或「上期=本期」时，回历史序列取上一可比期
                if not prev or str(prev.get("prev_period", "")) >= str(meta["data_period"]):
                    hp = history_prev(spec["id"], meta["data_period"])
                    if hp:
                        prev = hp
                lag = period_lag_days(meta["data_period"])
                limit = LAG_DAYS.get(spec["freq"], 60)
                if lag is not None and lag > limit:
                    # 疑似截断/过旧：隔 2 秒重试一次，仍不行就降级到下一源
                    errors.append(f"{source}: 数据过旧 {lag} 天 > {limit}（疑似截断）")
                    if attempt < 3:
                        time.sleep(8)   # 新浪/部分源限流后需静默约 10 秒才恢复全量
                        continue
                    break
                rec = {"indicator_id": spec["id"], "source": source, "function": name,
                       "current_state": {"指标": cur["指标"], "数值": cur["值"], "数据所属期": meta["data_period"]},
                       "data_period": meta["data_period"], "release_date": meta["data_period"],
                       "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
                       "fallback_flag": bool(errors), "fallback_path": "; ".join(errors) if errors else None,
                       "rows": int(len(df)), **prev,
                       "official_source": spec.get("official_source"), "official_url": spec.get("official_url")}
                write_json(os.path.join(CACHE_DIR, spec["id"] + ".json"), rec)
                return rec
            except Exception as e:
                errors.append(f"{source}/{name}: {type(e).__name__}: {str(e)[:70]}")
                break
    return {"indicator_id": spec["id"], "source": None, "errors": errors,
            "missing_type": "source_unavailable",
            "fetched_at": dt.datetime.now().isoformat(timespec="seconds")}


def official_tier(indicator_id, spec=None):
    """已人工对账 → B；否则记 C。核对历史以 jsonl 追加为准，兼容旧 json。"""
    off = None
    jl = os.path.join(OFFICIAL_DIR, indicator_id + ".jsonl")
    if os.path.exists(jl):
        rows = [l for l in io.open(jl, encoding="utf-8").read().splitlines() if l.strip()]
        for line in reversed(rows):
            try:
                cand = json.loads(line)
                if cand.get("value") and cand.get("source_url") and cand.get("matched", True):
                    off = cand
                    break
            except Exception:
                continue
    if off is None:
        off = read_json(os.path.join(OFFICIAL_DIR, indicator_id + ".json"))
    if off and off.get("value") and off.get("source_url"):
        return "B", off
    return "C", None


def to_record(spec, res, as_of):
    tier, off = official_tier(spec["id"], spec)
    ok = "current_state" in res
    rec = {"record_id": f"{spec['id']}-{res.get('data_period') or 'NA'}", "layer": spec.get("layer", "市场"),
           "indicator_id": spec["id"], "channel": spec["channel"], "subject": spec["subject"],
           "derived_type": "聚合值", "value_kind": spec["value_kind"],
           "observation_time": res["fetched_at"], "release_date": res.get("release_date") or "",
           "data_period": res.get("data_period") or "", "update_frequency": spec["freq"],
           "source_tier": tier, "fallback_flag": bool(res.get("fallback_flag")),
           "missing_type": "none" if ok else "source_unavailable", "value_type": "初值",
           "proves": spec["proves"], "does_not_prove": spec["does_not_prove"],
           "rule_status": "ratified", "status": "active"}
    if res.get("fallback_path"):
        rec["fallback_path"] = res["fallback_path"]
    if ok:
        rec["current_state"] = res["current_state"]
    if off:
        rec["verified_by"] = off.get("source_url")
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    if args.list:
        for s in SPECS:
            print(f"{s['id']:<16}{s['channel']:<4}{s['subject']:<5}{s['freq']:<3}{','.join(p[0] for p in s['providers'])}")
        return 0

    # 导出溯源表（供 state.py 与报告使用）
    prov = {}
    for s in SPECS:
        hosts = []
        for _src, aliases, _p in s["providers"]:
            if _src == "calc":
                hosts += _hosts_of(_p)          # 自算指标：探测解析器源码里的官方域名
                continue
            _n, _fn = resolve(aliases)
            if _fn is not None:
                hosts += _hosts_of(_fn)
        hosts = sorted(set(hosts))
        prov[s["id"]] = {"official_source": s.get("official_source"), "official_url": s.get("official_url"),
                         "tier_default": s.get("tier_default"), "channel": s["channel"],
                         "hosts": hosts,
                         "direct_official": bool(hosts) and all(h.endswith(OFFICIAL_DOMAINS) for h in hosts)}
    write_json(os.path.join(ROOT, "data", "provenance.json"), prov)

    ids = args.ids or [s["id"] for s in SPECS]
    print(f"{'指标':<16}{'源':<16}{'数据期':<12}{'值':<26}备注")
    print("-" * 96)
    ok = miss = 0
    for i in ids:
        spec = SPEC_MAP.get(i)
        if not spec:
            print(f"{i:<16}未注册")
            continue
        res = fetch_one(spec, args, args.as_of)
        rec = to_record(spec, res, args.as_of)
        # stale 闸门（第十节 2）：>3 倍 → 不可读、不落盘；>2 倍 → 标 stale
        FREQ_DAYS = {"日": 1, "周": 5, "月": 21, "季": 63}
        lag = biz_days_between(rec.get("data_period"), args.as_of or dt.date.today().isoformat())
        ratio = (lag / FREQ_DAYS[spec["freq"]]) if (lag is not None and spec["freq"] in FREQ_DAYS) else None
        if ratio is not None and ratio > 3:
            print(f"{spec['id']:<16}{'—':<16}{rec['data_period']:<12}{'不可读（超 3 倍时效）':<26}未落盘")
            miss += 1
            continue
        if ratio is not None and ratio > 2:
            rec["missing_type"] = "stale"
        if rec["data_period"]:
            write_json(os.path.join(FACT_DIR, rec["data_period"], f"{spec['id']}.json"), rec)
            append_revision(spec["id"], rec["data_period"],
                            (rec.get("current_state") or {}).get("数值"),
                            rec["source_tier"], res.get("source"))
        val = (rec.get("current_state") or {}).get("数值", "—")
        note = "缓存" if res.get("cache_hit") else ("降级" if rec.get("fallback_flag") else "")
        if rec["missing_type"] == "stale":
            note = (note + " " if note else "") + "stale（超 2 倍时效）"
        elif rec["missing_type"] != "none":
            note = (note + " " if note else "") + "失败：" + str(res.get("errors"))[:36]
        print(f"{spec['id']:<16}{str(res.get('source') or '—'):<16}{rec['data_period']:<12}{str(val):<26}{note}")
        ok += rec["missing_type"] == "none"
        miss += rec["missing_type"] != "none"
    print("-" * 96)
    print(f"成功 {ok} / 失败 {miss}（C 类源；对账后升 B 见 scripts/README.md）")
    return 0 if miss == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
