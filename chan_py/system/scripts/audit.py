#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""指标复评（audit）：检查六环现行指标是否失效、是否有更合适的数据。

回答三个问题，不改任何数据：
  1. 这只指标**还在更新吗**？—— 数据期落后几期、源是否还通
  2. 它**还能用吗**？—— 官方入口可达性、最近一次抓取是否降级/失败
  3. **有没有更合适的**？—— akshare 里同主题函数候选、注册表里的备源数量

用法：
    python scripts/audit.py              # 全量复评，写 reports/audit-<date>.md
    python scripts/audit.py --ring C4    # 只看某一环
    python scripts/audit.py --no-net     # 不检查官方 URL 可达性（快）
"""
import argparse
import datetime as dt
import glob
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "cache")
HIST = os.path.join(ROOT, "data", "history")
REPORTS = os.path.join(ROOT, "reports")
DIST_REF = os.path.join(ROOT, "dist", "market-state", "references")

FREQ_DAYS = {"日": 1, "周": 5, "月": 21, "季": 63, "年": 252}

# 指标名里的主题词 → akshare 函数名关键词
TOPIC_HINTS = [
    ("CPI", ["cpi"]), ("PPI", ["ppi"]), ("PMI", ["pmi"]), ("GDP", ["gdp"]),
    ("M2", ["money_supply", "m2"]), ("M1", ["money_supply", "m1"]),
    ("社融", ["social_financing"]), ("贷款", ["loan", "rmb_loan"]),
    ("LPR", ["lpr"]), ("Shibor", ["shibor", "interbank"]),
    ("国债", ["bond", "yield", "treasury"]), ("回购", ["repo"]),
    ("融资", ["margin"]), ("北向", ["north", "hk"]), ("ETF", ["etf"]),
    ("基金", ["fund"]), ("龙虎榜", ["lhb", "dragon"]), ("大宗", ["block"]),
    ("估值", ["valuation", "pe"]), ("股息", ["dividend"]), ("换手", ["turnover"]),
    ("房价", ["house", "estate"]), ("用电", ["electricity"]),
    ("存款", ["deposit"]), ("准备", ["reserve"]), ("汇率", ["fx", "currency"]),
    ("VIX", ["vix"]), ("美元", ["dxy", "dollar"]),
]


def load_json(p, default=None):
    try:
        with io.open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def provenance():
    """官方链接与直连标记在 data/provenance.json，不在 registry。"""
    d = load_json(os.path.join(ROOT, "data", "provenance.json"), {})
    return d if isinstance(d, dict) else {}


def registry():
    r = load_json(os.path.join(DIST_REF, "registry.json"), {})
    return r if isinstance(r, dict) else {}


def fetch_specs():
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import fetch as F
    return {s["id"]: s for s in F.SPECS}


def cache_of(iid):
    return load_json(os.path.join(CACHE, iid + ".json"), {}) or {}


def hist_of(iid):
    fp = os.path.join(HIST, iid + ".jsonl")
    if not os.path.exists(fp):
        return 0, None
    try:
        rows = [json.loads(x) for x in io.open(fp, encoding="utf-8").read().splitlines() if x.strip()][1:]
    except Exception:
        return 0, None
    return len(rows), (rows[-1].get("data_period") if rows else None)


def biz_days(d0, d1):
    d0, d1 = dt.date.fromisoformat(d0), dt.date.fromisoformat(d1)
    if d1 <= d0:
        return 0
    n, d = 0, d0
    while d < d1:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def lag_periods(period, freq, today):
    if not period:
        return None
    try:
        gap = biz_days(period, today)
    except Exception:
        return None
    unit = FREQ_DAYS.get(freq, 21)
    return gap / unit


def url_alive(url, timeout=6):
    if not url:
        return None, "无官方链接"
    try:
        import requests
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"}, verify=False)
        return r.status_code < 400, f"HTTP {r.status_code}"
    except Exception as e:
        return False, f"{type(e).__name__}"


def ak_candidates(name, iid, limit=4):
    """在 akshare 里按主题词找同主题函数，作为"可能有更合适数据"的线索。"""
    try:
        import akshare as ak
    except Exception:
        return []
    names = [x for x in dir(ak) if x.startswith(("macro_china", "bond_", "rate_", "fund_", "stock_"))]
    keys = []
    for topic, kws in TOPIC_HINTS:
        if topic in name or topic in iid:
            keys += kws
    if not keys:
        return []
    def hit(fn, key):
        toks = fn.lower().split("_")
        return key in toks if len(key) <= 4 else key in fn.lower()

    out = [n for n in names if any(hit(n, k) for k in keys)]
    return sorted(out)[:limit]



# ---------------------------------------------------------------- 口径适配（第四件事）
# 每环要回答的"资金问题"，以及能回答它所需的口径特征
RING_QUESTION = {
    "C1": ("资金的价格基准动没动", {"level", "ratio", "qualitative"}, "月"),
    "C2": ("钱的总量够不够、以什么形态存在", {"level", "ratio", "count"}, "月"),
    "C3": ("借钱的成本与期限补偿", {"level", "ratio"}, "日"),
    "C4": ("借钱的条件松不松、池子里有多少钱", {"level", "ratio", "count"}, "日"),
    "C5": ("谁在动钱：加杠杆的、减仓的、外部的", {"level", "ratio", "count"}, "月"),
    "C6": ("钱落到哪：多少、多广、集不集中", {"level", "ratio", "count", "return", "price"}, "日"),
}
FREQ_RANK = {"日": 3, "周": 2, "月": 1, "季": 0, "年": 0}


def meaning_fit(iid, meta, spec, used_in_state):
    """从"数据意思"角度判断：这个指标还在回答本环的资金问题吗？

    返回 (适配结论, 说明)。规则判定，需人复核。
    """
    ch = meta.get("channel") or ""
    q, want_kinds, need_freq = RING_QUESTION.get(ch, ("", set(), "月"))
    vk = (meta.get("value_kind") or "").lower()
    freq = meta.get("frequency") or "月"
    name = meta.get("name") or iid

    notes = []
    verdict = "直接回答"
    has_cands = bool(ak_candidates(name, iid, 3))

    # 1) 频率够不够（日频环用月频数据 → 结论天生滞后）
    #    但"慢"本身不是缺陷：没有更高频替代时，这就是当下最有说服力的数据
    if FREQ_RANK.get(freq, 1) < FREQ_RANK.get(need_freq, 1):
        if has_cands:
            verdict = "口径可改进"
            notes.append(f"该环要{need_freq}频，这只指标是{freq}频；akshare 有同主题候选，需人工确认是否更高频")
        else:
            verdict = "口径受限（接受）"
            notes.append(f"该环要{need_freq}频，这只指标是{freq}频；目前没有同主题替代，按现状使用并在状态里标出滞后")

    # 2) 口径类型对不对
    if want_kinds and vk and vk not in want_kinds:
        verdict = "口径偏移"
        notes.append(f"环内需要 {('/'.join(sorted(want_kinds)))} 口径，实际是 {vk}")

    # 3) 是不是代理（代理能回答，但要在状态里标出来）
    prov = (spec or {}).get("proves") or ""
    if "代理" in prov or "替代" in prov:
        if verdict == "直接回答":
            verdict = "代理回答"
        notes.append("这是代理指标，状态里必须标替代关系")

    # 4) 用了没有
    if not used_in_state:
        notes.append("当前状态页没有引用它")

    if not notes:
        notes.append("直接对应本环的资金问题")
    return verdict, "；".join(notes)


def verdict(lag, alive, degraded, has_alt_provider, cands, direct_official=False):
    """给结论：保留 / 观察 / 建议替换 / 已失效。只描述判断依据，不自动改。"""
    if lag is None:
        return "无法判断", "没有数据期"
    if lag > 3:
        return "已失效", f"落后 {lag:.1f} 个周期（>3），按规则不落盘"
    if lag > 2:
        return "建议替换", f"落后 {lag:.1f} 个周期（>2），可能已停更"
    if lag > 1.2:
        return "观察", f"落后 {lag:.1f} 个周期，接近阈值"
    if alive is False and degraded:
        return "观察", "官方入口不通且最近抓取降级"
    if cands and has_alt_provider <= 1 and not direct_official:
        return "留意替代", f"只有 {has_alt_provider} 个来源且非官方直连，akshare 有同主题候选"
    return "保留", "更新正常"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ring", default="")
    ap.add_argument("--no-net", action="store_true")
    a = ap.parse_args()

    reg = registry()
    prov = provenance()
    specs = fetch_specs()
    # 状态页用的是中文名，不是 id —— 按名字匹配
    used_ids = set()
    try:
        _latest = sorted(glob.glob(os.path.join(ROOT, "reports", "*market-state.md")))[-1]
        _txt = io.open(_latest, encoding="utf-8").read()
    except Exception:
        _txt = ""
    for _iid, _m in reg.items():
        _nm = (_m.get("name") or "").split("（")[0].strip()
        if _nm and _nm in _txt:
            used_ids.add(_iid)
    today = dt.date.today().isoformat()
    rows = []

    for iid, meta in sorted(reg.items()):
        ch = meta.get("channel") or ""
        if a.ring and ch.lower() != a.ring.lower():
            continue
        if ch not in ("C1", "C2", "C3", "C4", "C5", "C6"):
            continue
        c = cache_of(iid)
        period = c.get("data_period") or (hist_of(iid)[1])
        freq = meta.get("frequency") or "月"
        lag = lag_periods(period, freq, today)
        n_hist, _ = hist_of(iid)
        spec = specs.get(iid)
        has_prov = len(spec["providers"]) if spec else 0
        pm = prov.get(iid) or {}
        alive, why = (None, "未检查") if a.no_net else url_alive(pm.get("official_url"))
        degraded = bool(c.get("fallback_flag"))
        cands = ak_candidates(meta.get("name") or "", iid)
        fit, fit_reason = meaning_fit(iid, meta, spec, iid in used_ids)
        if spec is None:
            v, reason = "未接入", "注册了但没有取数器，状态里不会出现"
        else:
            v, reason = verdict(lag, alive, degraded, has_prov, cands, bool(pm.get("direct_official")))

        rows.append({
            "id": iid, "ring": ch, "name": meta.get("name") or iid,
            "period": period or "—", "freq": freq,
            "lag": None if lag is None else round(lag, 1),
            "hist": n_hist, "providers": has_prov,
            "alive": "—" if alive is None else ("通" if alive else "不通"),
            "why": why, "degraded": degraded,
            "verdict": v, "reason": reason, "cands": cands,
            "fit": fit, "fit_reason": fit_reason,
        })

    order = {"已失效": 0, "建议替换": 1, "观察": 2, "留意替代": 3, "保留": 4, "未接入": 5, "无法判断": 6}
    rows.sort(key=lambda r: (order.get(r["verdict"], 9), r["ring"], r["id"]))

    # 控制台
    print(f"{'环':<4}{'状态':<8}{'口径':<10}{'指标':<24}{'数据期':<12}{'落后':<5}{'结论依据'}")
    print("-" * 116)
    for r in rows:
        print(f"{r['ring']:<4}{r['verdict']:<8}{r['fit']:<10}{r['name'][:22]:<24}{r['period']:<12}"
              f"{(str(r['lag']) if r['lag'] is not None else '—'):<5}{r['reason']}")
        if r["fit_reason"] and r["fit"] != "直接回答":
            print(f"    口径：{r['fit_reason']}")
        if r["cands"]:
            print(f"    候选数据源：{'、'.join(r['cands'])}")

    # 报告
    os.makedirs(REPORTS, exist_ok=True)
    fp = os.path.join(REPORTS, f"audit-{today}.md")
    n_bad = sum(1 for r in rows if r["verdict"] in ("已失效", "建议替换"))
    with io.open(fp, "w", encoding="utf-8") as f:
        f.write(f"# 指标复评 · {today}\n\n")
        f.write(f"共 {len(rows)} 个六环指标，其中 **{n_bad}** 个需要处理"
                f"（已失效 / 建议替换）。本报告只做诊断，不改任何数据与规则。\n\n")
        f.write("| 环 | 结论 | 口径适配 | 指标 | 数据期 | 落后(周期) | 官方入口 | 结论依据 | 候选来源 |\n")
        f.write("|---|---|---|---|---|---|---|---|---|\n")
        for r in rows:
            f.write(f"| {r['ring']} | {r['verdict']} | {r['fit']} | {r['name']} | {r['period']} | "
                    f"{r['lag'] if r['lag'] is not None else '—'} | {r['alive']} | {r['reason']} | "
                    f"{'、'.join(r['cands']) or '—'} |\n")
        f.write("\n## 口径适配（从数据意思看还能不能回答本环的资金问题）\n\n")
        f.write("| 环 | 指标 | 适配结论 | 说明 |\n|---|---|---|---|\n")
        for r in rows:
            if r["fit"] != "直接回答":
                f.write(f"| {r['ring']} | {r['name']} | {r['fit']} | {r['fit_reason']} |\n")
        f.write("\n> 口径适配为规则判定（环需要什么频率/口径 vs 指标实际提供什么），需人复核。\n")
        f.write("> 候选函数只是「可能有更合适数据」的线索，频率与口径都要人工确认，不能由函数名推断。\n")
    print(f"\n报告已写入：{os.path.relpath(fp, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
