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
        fn = getattr(ak, n, None)
        if fn is not None:
            return n, fn
    return None, None


def throttled(source):
    gap = time.time() - _last_call.get(source, 0)
    if gap < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - gap)
    _last_call[source] = time.time()


def read_json(path, default=None):
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def norm_period(raw):
    """把 '2026年10月份' / '202610' / '2026.10' / date 统一成 YYYY-MM-01 或 YYYY-MM-DD。"""
    s = str(raw)
    m = re.search(r"(\d{4})\D*(\d{1,2})", s)
    if not m:
        return s[:10]
    y, mo = m.group(1), int(m.group(2))
    day = 1
    d = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", s)
    if d:
        day = int(d.group(3))
    return f"{y}-{mo:02d}-{day:02d}"


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


def p_sector_amt(df):
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
            {"data_period": norm_period(df.iloc[0].get("交易日期") or dt.date.today())})


def p_block_amt(df):
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
            {"data_period": norm_period(dt.date.today())})

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
         providers=[("akshare/em", ["bond_zh_us_yield_em", "bond_zh_us_rate"], p_cgb10y)],
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
         providers=[("akshare/csindex", ["index_value_csindex"], p_div)],
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
         providers=[("akshare/em", ["stock_dzjy_mrmx"], p_block_amt)],
         official_source="东方财富·大宗交易每日明细（原始披露为交易所）", official_url="https://data.eastmoney.com/dzjy/mrmx.html",
         proves="大宗交易的规模", does_not_prove="不说明买卖双方意图"),
    dict(id="INST_BLOCK_PREM", channel="C5", subject="机构", freq="日", value_kind="ratio", layer="市场", tier_default="C",
         providers=[("akshare/em", ["stock_dzjy_mrmx"], p_block_prem)],
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
    if spec["id"] == "MKT_CGB10Y":
        return {"start_date": "20260101"}
    if spec["id"] == "SECTOR_AMT":
        return {"symbol": "半导体", "start_date": "20260901", "end_date": _ymd(as_of)}
    if spec["id"] in ("INST_LHB_NET", "INST_BLOCK_AMT", "INST_BLOCK_PREM"):
        end = _ymd(as_of)
        start = str(int(end[:8]) - 7)
        return {"start_date": start, "end_date": end}
    if spec["id"] == "MKT_DR007":
        return {"start_date": "20261001", "end_date": _ymd(as_of)}
    return {}


def fetch_one(spec, args, as_of):
    if not args.no_cache:
        cached = read_json(os.path.join(CACHE_DIR, spec["id"] + ".json"))
        if cached and cached.get("fetched_at"):
            age_h = (dt.datetime.now() - dt.datetime.fromisoformat(cached["fetched_at"])).total_seconds() / 3600
            if age_h < TTL_HOURS.get(spec["freq"], 24):
                return dict(cached, cache_hit=True)

    errors = []
    for source, aliases, parser in spec["providers"]:
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
    """已人工对账 → B；否则记 C（akshare 一律 C，能否使用看 c_reasons 白名单）。"""
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
        FREQ_DAYS = {"日": 1, "周": 7, "月": 30, "季": 90}
        lag = period_lag_days(rec.get("data_period"))
        ratio = (lag / FREQ_DAYS[spec["freq"]]) if (lag is not None and spec["freq"] in FREQ_DAYS) else None
        if ratio is not None and ratio > 3:
            print(f"{spec['id']:<16}{'—':<16}{rec['data_period']:<12}{'不可读（超 3 倍时效）':<26}未落盘")
            miss += 1
            continue
        if ratio is not None and ratio > 2:
            rec["missing_type"] = "stale"
        if rec["data_period"]:
            write_json(os.path.join(FACT_DIR, rec["data_period"], f"{spec['id']}.json"), rec)
        val = (rec.get("current_state") or {}).get("数值", "—")
        note = "缓存" if res.get("cache_hit") else ("降级" if rec.get("fallback_flag") else "")
        if rec["missing_type"] != "none":
            note = (note + " " if note else "") + "失败：" + str(res.get("errors"))[:36]
        print(f"{spec['id']:<16}{str(res.get('source') or '—'):<16}{rec['data_period']:<12}{str(val):<26}{note}")
        ok += rec["missing_type"] == "none"
        miss += rec["missing_type"] != "none"
    print("-" * 96)
    print(f"成功 {ok} / 失败 {miss}（C 类源；对账后升 B 见 scripts/README.md）")
    return 0 if miss == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
