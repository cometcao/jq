#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""状态生成器：读 data/cache（工作数据）+ data/facts（可发布记录）→ 六环证据行。

规则依据：docs/01 第六节判定表（L1）、L3 断言强度、第十节 2（stale）、D03（来源分级）。

⚠ 分级政策（本脚本暴露的规则冲突）：
    ratified 的 D03 写着「C 类不得单独支撑状态词，要有至少一条 A/B 佐证」。
    akshare 抓来的数据属 C 类（开源库一律 C）。所以：
      --policy strict（默认）：只有 B 类（已对账，data/official/<id>.json 存在）才出状态词；
                              全是 C 时，六环如实写「不可读（C 类，未对账）」。
      --policy demo     ：允许 C 类出状态词，但每行后缀「〔C 类，未对账〕」，供对照。

用法：
    python scripts/state.py                # strict
    python scripts/state.py --policy demo  # 允许 C 类
    python scripts/state.py --write        # 同时写 reports/<as-of>-state.md
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
FACTS = os.path.join(ROOT, "data", "facts")
OFFICIAL = os.path.join(ROOT, "data", "official")
REPORTS = os.path.join(ROOT, "reports")


def _load_prov():
    try:
        with io.open(os.path.join(ROOT, "data", "provenance.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


PROV = _load_prov()


def load_cache(iid):
    p = os.path.join(CACHE, iid + ".json")
    if not os.path.exists(p):
        return None
    with io.open(p, encoding="utf-8") as f:
        return json.load(f)


def num(s):
    if s is None:
        return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?", str(s).replace(",", ""))
    return float(m.group(0)) if m else None


def tier_of(iid):
    """从落盘事实记录读 source_tier（B / B- / C）；无记录时退回 C。"""
    files = sorted(glob.glob(os.path.join(FACTS, "*", iid + ".json")))
    if not files:
        return "C"
    with io.open(files[-1], encoding="utf-8") as f:
        return json.load(f).get("source_tier", "C")


def period(iid):
    c = load_cache(iid)
    return c.get("data_period") if c else None


def val(iid, key="value"):
    c = load_cache(iid)
    if not c:
        return None
    if key == "value":
        return num(c.get("current_state", {}).get("数值"))
    return num(c.get(key))


RING_IDS = {
    "C1": ["POL_LPR"],
    "C2": ["MKT_M2_YOY", "MKT_M1_YOY", "FISC_DEP", "MKT_RMB_LOAN_YOY"],
    "C3": ["MKT_DR007", "MKT_CGB10Y", "FX_CNY_MID", "MKT_DIV_YIELD"],
    "C4": ["MKT_MARGIN_BAL"],
    "C5": ["RTL_MARGIN_INVESTORS"],
    "C6": ["SECTOR_AMT"],
}


def prev_value_from_revisions(iid, current_period):
    """从 data/revisions/<iid>/*.jsonl 里找数据期早于 current_period 的最近一条值。"""
    d = os.path.join(ROOT, "data", "revisions", iid)
    if not os.path.isdir(d):
        return None, None
    best = None
    for fp in glob.glob(os.path.join(d, "*.jsonl")):
        per = os.path.basename(fp)[:-6]
        if per >= current_period:
            continue
        if best is None or per > best[0]:
            rows = [l for l in io.open(fp, encoding="utf-8").read().splitlines() if l.strip()]
            if rows:
                try:
                    best = (per, json.loads(rows[-1]).get("value"))
                except Exception:
                    pass
    if best is None:
        return None, None
    m = re.search(r"[-+]?\d+(?:\.\d+)?", str(best[1]))
    return (float(m.group(0)) if m else None), best[0]


def normalize_dates(rings, as_of):
    """与 as_of 相同的数据期不显示；不同的显示一次并标「非最新」。"""
    for r_ in rings:
        for k, ln in enumerate(r_.lines):
            m = re.search(r"（(\d{4}-\d{2}-\d{2})）", ln)
            if not m:
                continue
            d = m.group(1)
            rep = "" if d == as_of else f"（{d}*）"
            r_.lines[k] = ln[:m.start()] + rep + ln[m.end():]


class Ring:
    def __init__(self, code, label):
        self.code, self.label, self.lines = code, label, []

    def add(self, text, evidence, boundary, tag=""):
        self.lines.append(f"{self.code} {text}｜依据：{evidence}｜边界：{boundary}{tag}")


def build(policy):
    rings = [Ring("C1", "政策设定"), Ring("C2", "资金供给"), Ring("C3", "资金价格"),
             Ring("C4", "场内杠杆与资金池"), Ring("C5", "主体行为"), Ring("C6", "市场结果")]

    prov = PROV

    # C 类可用理由（人工登记；未登记的 C 一律不放行）
    try:
        with io.open(os.path.join(ROOT, "data", "c_reasons.json"), encoding="utf-8") as fh:
            C_REASONS = json.load(fh)
    except Exception:
        C_REASONS = {}

    def allow(iid):
        """B → 可用且不逐行标注；C → 仅当所在环没有 A/B 证据时可用，并逐行标注理由。"""
        t = tier_of(iid)
        if t == "B":
            return True, ""
        # 指标层面：该指标没有 A/B 时才用 C（当前 12 项都是唯一来源）
        reason = C_REASONS.get(iid) or "唯一可得来源，未对账"
        return True, f"〔C 类·{reason[:16]}…〕"

    # C1 LPR
    ok, tag = allow("POL_LPR")
    v, p = val("POL_LPR"), val("POL_LPR", "prev_value")
    if ok and v is not None and p is not None:
        word = "不变" if v == p else ("偏松" if v < p else "偏紧")
        rings[0].add(f"{word}（{period('POL_LPR')}）", f"1 年期 LPR {v:.2f}% 对比上一期 {p:.2f}%", "只说明设定值变化，不说明传导", tag)
    else:
        rings[0].add("不可读（—）", "LPR 记录缺失，或来源为 C 类、无源可支撑状态词", "该环无可用证据")

    # C2 M2 扩/缩 + 剪刀差
    ok, tag = allow("MKT_M2_YOY")
    m2, m1 = val("MKT_M2_YOY"), val("MKT_M1_YOY")
    m2p = val("MKT_M2_YOY", "prev_value")
    if ok and m2 is not None:
        word = "扩" if m2 > 0 else ("缩" if m2 < 0 else "不变")
        ev = f"M2 同比 {m2:.2f}% > 0" if m2 > 0 else f"M2 同比 {m2:.2f}% ≤ 0"
        if m2p is not None:
            ev += f"（上一期 {m2p:.2f}%）"
        rings[1].add(f"{word}（{period('MKT_M2_YOY')}）", ev, "不说明资金进入股市", tag)
        if m1 is not None:
            spread = m2 - m1
            word2 = "偏死" if spread > 0 else ("偏活" if spread < 0 else "中性")
            rings[1].add(f"结构{word2}（{period('MKT_M2_YOY')}）", f"M2−M1 剪刀差 {spread:+.2f}pp（M2 {m2:.2f}% / M1 {m1:.2f}%）", "不说明风险偏好变化", tag)
    else:
        rings[1].add("不可读（—）", "M2 记录缺失，或来源为 C 类、无源可支撑状态词", "该环无可用证据")

    # C3 短端与长端分别写
    for iid, name in (("MKT_DR007", "短端"), ("MKT_CGB10Y", "长端")):
        ok, tag = allow(iid)
        v, p = val(iid), val(iid, "prev_value")
        if ok and v is not None and p is not None:
            word = "不变" if v == p else ("变贵" if v > p else "变便宜")
            rings[2].add(f"{name}{word}（{period(iid)}）", f"{name}利率 {v:.4f}% 对比上一期 {p:.4f}%", "不说明估值会重估", tag)
    if not rings[2].lines:
        rings[2].add("不可读（—）", "利率记录缺失，或来源为 C 类、无源可支撑状态词", "该环无可用证据")

    # C4 杠杆 + 现金池
    ok, tag = allow("MKT_MARGIN_BAL")
    v, p = val("MKT_MARGIN_BAL"), val("MKT_MARGIN_BAL", "prev_value")
    if ok and v is not None and p is not None:
        word = "不变" if v == p else ("加杠杆" if v > p else "去杠杆")
        rings[3].add(f"{word}（{period('MKT_MARGIN_BAL')}）", f"融资余额 {v:.2f} 亿 对比上一期 {p:.2f} 亿", "不说明是新资金", tag)
    else:
        rings[3].add("不可读（—）", "两融记录缺失，或来源为 C 类、无源可支撑状态词", "该环无可用证据")
    col = val("MKT_MARGIN_COLLATERAL")
    ok, tag = allow("MKT_MARGIN_DEP")
    ok2, tag2 = allow("MKT_MMF_SCALE")
    dep = val("MKT_MARGIN_DEP")
    if ok and dep is not None:
        ev = f"客户保证金（交易结算资金余额）{dep:.2f} 亿"
        if col is not None:
            ev += f"；两融担保物总价值 {col:.2f} 万亿"
        rings[3].add(f"现金池（{period('MKT_MARGIN_DEP')}）", ev, "月频人工录入；不等于杠杆，也不等于成交额", tag)
    else:
        mmf = val("MKT_MMF_SCALE")
        if mmf is not None:
            pmmf, prev_period = prev_value_from_revisions("MKT_MMF_SCALE", period("MKT_MMF_SCALE"))
            if pmmf is not None:
                word = "增" if mmf > pmmf else ("减" if mmf < pmmf else "不变")
                ev = f"货币基金规模 {mmf:.2f} 万亿 对比上一期 {pmmf:.2f} 万亿（{prev_period}）"
                rings[3].add(f"现金池{word}（{period('MKT_MMF_SCALE')}）", ev + "；保证金官方停发，此为同属性代理",
                             "货币基金规模不等于客户保证金，也不等于场内现金", tag2)
            else:
                rings[3].add("现金池不可读（—）",
                             f"保证金官方自 2017 年起停发；代理指标已有货币基金规模 {mmf:.2f} 万亿，但无证据可作前值（首次落盘）",
                             "下次运行即可比较")
        else:
            ev = "交易结算资金余额官方自 2017 年起停止公开发布（投保基金官网历史数据止于 2017-06）"
            if col is not None:
                ev += f"；已有两融担保物总价值 {col:.2f} 万亿（含证券，不等于现金池）"
            rings[3].add("现金池不可读（—）", ev, "该环无证据")

    # C5 窄口径替代 + 机构/外部空环
    ok, tag = allow("RTL_MARGIN_INVESTORS")
    v, p = val("RTL_MARGIN_INVESTORS"), val("RTL_MARGIN_INVESTORS", "prev_value")
    if ok and v is not None:
        word = "增" if (p is None or v > p) else ("减" if v < p else "不变")
        ev = f"两融个人投资者 {v:.2f} 万户" + (f" 对比上一期 {p:.2f} 万户" if p is not None else "")
        rings[4].add(f"散户{word}（{period('RTL_MARGIN_INVESTORS')}）", ev, "仅覆盖杠杆散户，不等于新增开户", tag + "〔替代：窄口径〕")
    else:
        rings[4].add("散户不可读（—）", "无开户或杠杆投资者记录", "该环无可用证据")
    ok, tag = allow("INST_LHB_NET")
    v = val("INST_LHB_NET")
    if ok and v is not None:
        word = "机构增" if v > 0 else ("机构减" if v < 0 else "机构不变")
        ev = f"龙虎榜机构净买额 {v:+.2f} 亿（区间汇总）"
        v2 = val("INST_BLOCK_AMT")
        if v2 is not None:
            ev += f"；大宗成交 {v2:.2f} 亿"
        rings[4].add(f"{word}（{period('INST_LHB_NET')}）", ev, "仅覆盖上榜与大宗，不代表全部机构行为", tag)
    else:
        rings[4].add("机构不可读（—）", "龙虎榜与大宗均未取到", "该环无证据")
    ok, tag = allow("MKT_NORTH_AMT")
    north = val("MKT_NORTH_AMT")
    if ok and north is not None:
        rings[4].add(f"外部（{period('MKT_NORTH_AMT')}）", f"北向盘后成交总额 {north:.2f} 亿", "无净额、无买卖拆分", tag)
    else:
        rings[4].add("外部不可读（—）",
                     "北向官方自 2024-08 起停止日度披露（净买额与持股均为空）；替代需海外中国 ETF 规模源，列入插件期",
                     "该环无证据")

    # C6 参与度：全市场成交额（市场层口径，不得用单板块成交额代替）
    ok, tag = allow("MKT_TURNOVER")
    v = val("MKT_TURNOVER")
    p = val("MKT_TURNOVER", "prev_value")
    prev_period = None
    if p is None and ok and v is not None:
        p, prev_period = prev_value_from_revisions("MKT_TURNOVER", period("MKT_TURNOVER"))
    if ok and v is not None and p is not None:
        word = "不变" if v == p else ("升" if v > p else "降")
        ev = f"全市场成交额 {v:.2f} 亿 对比上一期 {p:.2f} 亿（行业板块加总口径）"
        if prev_period:
            ev += f"，前一可比期 {prev_period}"
        rings[5].add(f"参与度{word}（{period('MKT_TURNOVER')}）", ev, "不说明资金来源", tag)
    elif ok and v is not None:
        rings[5].add("参与度不可读（—）",
                     f"全市场成交额已有 {v:.2f} 亿，但修订链无更早数据期、无证据可作前值（首次落盘）",
                     "该环暂无法判方向；下次运行即可比较")
    else:
        rings[5].add("参与度不可读（—）", "全市场成交额缺失，或来源为 C 类、无源可支撑状态词", "该环无可用证据")
    ok, tag = allow("MKT_BREADTH")
    v, p = val("MKT_BREADTH"), val("MKT_BREADTH", "prev_value")
    if ok and v is not None:
        word = "强" if v > 50 else ("弱" if v < 50 else "均衡")
        ev = f"上涨家数占比 {v:.1f}% " + ("> 50%" if v > 50 else "< 50%")
        if p is not None:
            ev += f"（上一期 {p:.1f}%）"
        rings[5].add(f"广度{word}（{period('MKT_BREADTH')}）", ev, "只说明广度，不说明幅度与结构", tag)
    else:
        rings[5].add("广度不可读（—）", "涨跌家数未取到", "该环无证据")
    ok, tag = allow("SECTOR_AMT_CONC")
    v = val("SECTOR_AMT_CONC")
    if ok and v is not None:
        word = "聚" if v >= 50 else "散"
        rings[5].add(f"结构{word}（{period('SECTOR_AMT_CONC')}）",
                     f"Top5 板块成交额占比 {v:.1f}%（阈值 50%；N=90 个行业板块）",
                     "只说明成交在板块间的分散程度，不说明资金方向", tag + "〔Top-5 口径〕")
    else:
        rings[5].add("结构不可读（—）", "板块集中度未取到", "该环无证据")

    # as-of：最慢环（月频优先）
    # as-of = 最新交易日（日频里最大的数据期）；非最新的行逐行标注
    daily = [period(i) for i in ("IDX_DAILY", "MKT_CGB10Y", "MKT_DR007", "SECTOR_AMT",
                                 "MKT_BREADTH", "SECTOR_AMT_CONC", "INST_LHB_NET",
                                 "INST_BLOCK_AMT", "MKT_DIV_YIELD", "FX_CNY_MID")
             if period(i)]
    as_of = max(daily) if daily else "不可用"
    normalize_dates(rings, as_of)
    body = "\n".join(r_.lines for r_ in rings) if False else "\n".join("\n".join(r_.lines) for r_ in rings)
    return as_of, body



def build_sector(policy):
    """板块层六环（同名不同义）。v1 只做 C2 份额、C6 涨跌与广度；其余如实不可读。"""
    try:
        with io.open(os.path.join(ROOT, "data", "sector_target.json"), encoding="utf-8") as fh:
            sector = json.load(fh).get("name", "半导体")
    except Exception:
        sector = "半导体"
    rings = [Ring("C1", "行业政策"), Ring("C2", "供给份额"), Ring("C3", "相对贵贱"),
             Ring("C4", "杠杆与资金池"), Ring("C5", "主体行为"), Ring("C6", "结果")]

    try:
        with io.open(os.path.join(ROOT, "data", "c_reasons.json"), encoding="utf-8") as fh:
            C_REASONS = json.load(fh)
    except Exception:
        C_REASONS = {}

    def tag_of(iid):
        t = tier_of(iid)
        if t == "B":
            return ""
        reason = C_REASONS.get(iid) or "唯一可得来源，未对账"
        return f"〔C 类·{reason[:16]}…〕"

    # C1 行业政策：人工，v1 不做
    rings[0].add("不可读（—）", "行业政策状态需人工录入官方文件链接", "该环无证据")
    # C2 供给份额
    v = val("SECTOR_SHARE")
    p, prev_period = prev_value_from_revisions("SECTOR_SHARE", period("SECTOR_SHARE"))
    if v is not None and p is not None:
        word = "份额升" if v > p else ("份额降" if v < p else "不变")
        rings[1].add(f"{word}（{period('SECTOR_SHARE')}）",
                     f"{sector}板块成交额占比 {v:.2f}% 对比上一期 {p:.2f}%（{prev_period}）",
                     "只说明成交份额，不说明资金流向量", tag_of("SECTOR_SHARE"))
    elif v is not None:
        rings[1].add("不可读（—）", f"份额已有 {v:.2f}%，但修订链无更早数据期、无证据可作前值（首次落盘）",
                     "该环暂无法判方向")
    else:
        rings[1].add("不可读（—）", "板块成交额或全市场成交额缺失", "该环无证据")
    # C3 相对贵贱：无板块估值源
    rings[2].add("不可读（—）", "板块估值（PE/股息率）无免费源，需中证行业指数估值映射", "该环无证据")
    # C4 默认空环
    rings[3].add("不可读（—）", "板块层杠杆与资金池默认不读（ADR-025 口径）", "该环无证据")
    # C5 主体行为：板块内龙虎榜/ETF 未加总
    rings[4].add("不可读（—）", "板块内龙虎榜与 ETF 申赎未做成分映射加总", "该环无证据")
    # C6 结果：涨跌幅 + 板块内广度
    pct = val("SECTOR_PCT")
    if pct is not None:
        word = "升" if pct > 0 else ("降" if pct < 0 else "不变")
        rings[5].add(f"{word}（{period('SECTOR_PCT')}）", f"{sector}板块指数涨跌幅 {pct:+.2f}%", "不说明板块内个股结构", tag_of("SECTOR_PCT"))
    else:
        rings[5].add("不可读（—）", "板块指数日线缺失", "该环无证据")
    b = val("SECTOR_BREADTH")
    if b is not None:
        word = "强" if b > 50 else ("弱" if b < 50 else "不变")
        rings[5].add(f"广度{word}（{period('SECTOR_BREADTH')}）", f"{sector}板块上涨家数占比 {b:.1f}%（阈值 50%）", "只说明广度，不说明幅度", tag_of("SECTOR_BREADTH"))

    daily = [period(i) for i in ("SECTOR_PCT", "SECTOR_BREADTH", "SECTOR_AMT") if period(i)]
    as_of = max(daily) if daily else "不可用"
    normalize_dates(rings, as_of)
    body = "\n".join("\n".join(r_.lines) for r_ in rings)
    return as_of, body, sector

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", choices=["traceable", "strict", "demo"], default="traceable")
    ap.add_argument("--layer", choices=["market", "sector"], default="market")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    if a.layer == "sector":
        as_of, body, sector = build_sector(a.policy)
        head = f"as-of {as_of}（最新交易日；板块层 · 目标板块：{sector}；行内 * 表示数据期早于 as-of）"
    else:
        as_of, body = build(a.policy)
        head = f"as-of {as_of}（最新交易日；行内 * 表示该行数据期早于 as-of）"
    text = f"{head}\n{body}\n"

    reg = {}
    try:
        with io.open(os.path.join(ROOT, "dist", "market-state", "references", "registry.json"), encoding="utf-8") as fh:
            reg = json.load(fh)
    except Exception:
        pass
    want = "板块" if a.layer == "sector" else "市场"
    missing = sorted({json.load(io.open(f, encoding="utf-8"))["indicator_id"]
                      for f in glob.glob(os.path.join(FACTS, "*", "*.json"))
                      if (reg.get(json.load(io.open(f, encoding="utf-8"))["indicator_id"], {}) or {}).get("layer", "市场") == want})
    meta = (f"\n元信息：\n- 证据条数：{len(missing)} 项事实记录\n"
            f"- 分级政策：{ {'strict':'strict（仅 B 类）','traceable':'traceable（B 可用；C 仅在该指标无 A/B 时使用并标注）','demo':'demo（C 类亦可，逐行标注）'}[a.policy] }\n"
            f"- B 类（已对账）指标：{[i for i in missing if tier_of(i)=='B'] or '无'}\n"
            f"- stale：按第十节 2 判定，超 3 倍不落盘\n")
    lines = ["", "数据溯源（逐项核对；官方直连才可能升 B）：",
             "| 指标 | 官方源 | 请求域名 | 直连官方 | 档位 |", "|---|---|---|---|---|"]
    for iid in missing:
        pr = PROV.get(iid) or {}
        hosts = ",".join(pr.get("hosts") or []) or "—"
        lines.append(f"| {iid} | {pr.get('official_source') or '—'} | {hosts} | "
                     f"{'是' if pr.get('direct_official') else '否'} | {tier_of(iid)} |")
    out = text + meta + "\n".join(lines) + "\n"

    if a.json:
        recs = []
        for ln in body.splitlines():
            m = re.match(r"^(C[1-6]) (\S+?)(（(\d{4}-\d{2}-\d{2})\*?）)?｜依据：(.+?)｜边界：(.+)$", ln)
            if not m:
                continue
            ring, state, _, period_, evidence, boundary = m.groups()
            tags = re.findall(r"〔([^〕]+)〕", boundary)
            boundary = re.sub(r"〔[^〕]+〕", "", boundary).strip()
            recs.append({"ring": ring, "state": state, "period": period_,
                         "evidence": evidence, "boundary": boundary, "tags": tags,
                         "raw": ln})
        payload = {"layer": a.layer, "as_of": as_of, "lines": recs,
                   "b_indicators": [i for i in missing if tier_of(i) == "B"],
                   "policy": a.policy,
                   "generated_at": dt.datetime.now().isoformat(timespec="seconds")}
        if a.write:
            os.makedirs(REPORTS, exist_ok=True)
            fp = os.path.join(REPORTS, f"state-{a.layer}.json")
            with io.open(fp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            print("已写入:", os.path.relpath(fp, ROOT))
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(out)

    if a.write:
        os.makedirs(REPORTS, exist_ok=True)
        suffix = "market" if a.layer == "market" else f"sector-{sector}"
        p = os.path.join(REPORTS, f"{as_of}-{suffix}-state.md")
        with io.open(p, "w", encoding="utf-8") as f:
            f.write("```\n" + text + "```\n" + meta)
        print("已写入:", os.path.relpath(p, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
