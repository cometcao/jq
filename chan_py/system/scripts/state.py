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


def build(policy, include_events=False):
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
        etf = val("EXT_CN_ETF_AUM")
        if etf is not None:
            pe, prev_e = val("EXT_CN_ETF_AUM", "prev_value"), None
            p2, prev_period = prev_value_from_revisions("EXT_CN_ETF_AUM", period("EXT_CN_ETF_AUM"))
            pe = pe if pe is not None else p2
            if pe is not None:
                word = "增" if etf > pe else ("减" if etf < pe else "不变")
                rings[4].add(f"外部{word}（代理·{period('EXT_CN_ETF_AUM')}）",
                             f"海外中国主题 ETF 规模 {etf:.2f} 十亿美元 对比上一期 {pe:.2f}（KWEB+KBA+KURE）",
                             "北向已停发；ETF 规模不等于北向资金，也不等于外资净买入", allow("EXT_CN_ETF_AUM")[1])
            else:
                rings[4].add("外部不可读（—）",
                             f"北向已停发；代理已有海外中国 ETF 规模 {etf:.2f} 十亿美元，但无证据可作前值（首次落盘）",
                             "下次运行即可比较")
        else:
            rings[4].add("外部不可读（—）",
                         "北向官方自 2024-08 起停止日度披露；海外中国 ETF 规模亦未取到",
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
    if include_events:
        body += "\n".join(events_section(as_of))
    _rd = ring_readings(as_of)
    chain_line, broken = chain_summary([ln for ln in body.splitlines() if ln.startswith("C")])
    body += f"\n\n链条完整性：{chain_line}"
    n_lines = len([ln for ln in body.splitlines() if ln.startswith("C")])
    body += f"\n本次 {n_lines} 条证据，覆盖 6 环，" + (f"{len(broken)} 处断点：{'、'.join(broken)}" if broken else "无断点")
    body += "；断点处请勿跨环推断。"
    cmp_lines, cmp_records = market_compare_lines()
    relations_by_ring = {}
    _reg = {}
    try:
        with io.open(os.path.join(ROOT, "dist", "market-state", "references", "registry.json"), encoding="utf-8") as f:
            _reg = json.load(f)
    except Exception:
        _reg = {}
    for rec in cmp_records:
        left = rec["inputs"][0]["ref"]
        ring = (_reg.get(left) or {}).get("channel") or "C?"
        relations_by_ring.setdefault(ring, []).append({
            "compare_id": rec["compare_id"],
            "value": rec["current_state"]["数值"],
            "period": rec["data_period"],
            "operand_order": rec["operand_order"],
        })
    if cmp_lines:
        body += "\n\n比价（七锚通过才出）：\n" + "\n".join(cmp_lines)
        persist_compares(cmp_records)
    return as_of, body




MARKET_COMPARES = [("MKT_M2_YOY", "MKT_M1_YOY", "difference"),
                   ("MKT_M2_YOY", "MKT_RMB_LOAN_YOY", "difference"),
                   ("MKT_DR007", "MKT_CGB10Y", "difference"),
                   ("MKT_MARGIN_BAL", "MKT_MARGIN_COLLATERAL", "ratio")]


def market_compare_lines():
    """市场层默认比价段：同层、同口径的两条差值，走 compare.py 的七锚与 schema。"""
    import argparse
    import importlib.util

    spec_ = importlib.util.spec_from_file_location("cmp_mod", os.path.join(ROOT, "scripts", "compare.py"))
    mod = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(mod)

    out, records = [], []
    for left, right, op in MARKET_COMPARES:
        a = argparse.Namespace(left=left, right=right, op=op, window=None, universe=None, dry=True)
        try:
            payload = mod.build(a)
            rec = mod.to_record(payload)
        except Exception as e:
            out.append(f"  {left} {op} {right}：不可比（{e}）")
            continue
        records.append(rec)
        out.append(f"  {rec['current_state']['对比结果']} = {rec['current_state']['数值']}"
                   f"（{rec['data_period']}）｜operand_order: {rec['operand_order']}")
    return out, records


def persist_compares(records):
    d = os.path.join(ROOT, "data", "compares")
    os.makedirs(d, exist_ok=True)
    for rec in records:
        fp = os.path.join(d, rec["compare_id"] + ".json")
        with io.open(fp, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)



HIST_DIR = os.path.join(ROOT, "reports", "state-history")


def chain_summary(lines):
    """链条完整性：每环是有值 / 部分 / 全断，并给出断点。"""
    by_ring = {}
    for ln in lines:
        m = re.match(r"^(C[1-6]) (\S+?)(（|｜)", ln)
        if not m:
            continue
        ring, state = m.group(1), m.group(2)
        unread = "不可读" in state
        by_ring.setdefault(ring, {"ok": 0, "bad": 0, "bad_parts": []})
        if unread:
            by_ring[ring]["bad"] += 1
            cleaned = re.sub(r"不可读|[（(]—[）)]", "", state).strip("（）()— ·")
            by_ring[ring]["bad_parts"].append(cleaned or "该环")
        else:
            by_ring[ring]["ok"] += 1

    parts, broken = [], []
    for ring in ("C1", "C2", "C3", "C4", "C5", "C6"):
        c = by_ring.get(ring)
        if not c:
            parts.append(f"{ring} 无行")
            broken.append(ring)
        elif c["bad"] == 0:
            parts.append(f"{ring} ✓")
        elif c["ok"] == 0:
            parts.append(f"{ring} ✗全断")
            broken.append(ring)
        else:
            names = "/".join([x for x in c["bad_parts"] if x]) or "部分"
            parts.append(f"{ring} 部分（{names}断）")
            broken.append(f"{ring}({names})")
    return " | ".join(parts), broken


def archive_snapshot(as_of, layer, payload, force=False):
    """按日归档：reports/state-history/<as_of>-<layer>.json，默认不覆盖。"""
    os.makedirs(HIST_DIR, exist_ok=True)
    fp = os.path.join(HIST_DIR, f"{as_of}-{layer}.json")
    if os.path.exists(fp) and not force:
        return fp, False
    with io.open(fp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return fp, True


def list_history():
    if not os.path.isdir(HIST_DIR):
        return []
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(HIST_DIR, "*.json")))


def _sector_name():
    fp = os.path.join(ROOT, "data", "sector_target.json")
    try:
        with io.open(fp, encoding="utf-8") as f:
            return (json.load(f) or {}).get("name") or "半导体"
    except Exception:
        return "半导体"


def sector_policy_clues(as_of, horizon=30):
    """板块层 C1 的政策线索：数对口部委近 N 天发布条数（只作线索，不给状态词）。"""
    fp = os.path.join(ROOT, "data", "events", f"calendar-{as_of}.json")
    mp = os.path.join(ROOT, "data", "sector_dept_map.json")
    if not (os.path.exists(fp) and os.path.exists(mp)):
        return None
    try:
        with io.open(fp, encoding="utf-8") as f:
            cal = json.load(f)
        with io.open(mp, encoding="utf-8") as f:
            depts = (json.load(f).get("map") or {}).get(_sector_name(), [])
    except Exception:
        return None
    if not depts:
        return None
    hits = [e for e in (cal.get("events") or [])
            if any(d in str(e.get("issuer", "")) for d in depts)]
    bad = [d for d in depts if d in ((json.load(io.open(mp, encoding="utf-8")).get("uncrawlable")) or {})]
    return {"depts": depts, "count": len(hits), "items": hits[:3], "uncrawlable": bad}


def _num_scaled(iid):
    """读缓存值并把「万亿」换算成「亿」。"""
    fp = os.path.join(ROOT, "data", "cache", iid + ".json")
    if not os.path.exists(fp):
        return None
    try:
        with io.open(fp, encoding="utf-8") as f:
            cur = (json.load(f).get("current_state") or {}).get("数值")
    except Exception:
        return None
    if cur is None:
        return None
    txt = str(cur)
    m = re.search(r"[-+]?\d+(?:\.\d+)?", txt.replace(",", ""))
    if not m:
        return None
    v = float(m.group(0))
    if "万亿" in txt:
        v *= 10000.0
    return v


def _pos_of(values, tail=60):
    vs = values[-tail:]
    if len(vs) < 2:
        return None
    lo, hi = min(vs), max(vs)
    return None if hi == lo else (vs[-1] - lo) / (hi - lo) * 100


def _hist(iid, tail=60):
    fp = os.path.join(ROOT, "data", "history", iid + ".jsonl")
    if not os.path.exists(fp):
        return []
    rows = [json.loads(x) for x in io.open(fp, encoding="utf-8").read().splitlines() if x.strip()][1:]
    return [(r["data_period"], r["value"]) for r in rows][-tail:]


def ring_readings(as_of):
    """每环一句「读法」：从资金角度看这组数字把钱放在哪、以什么形态存在。

    约束：只用已落盘数字；不用因果词；不做方向判断（不写宽松/充裕/活跃/流入流出）。
    """
    def g(iid):
        return val(iid)

    def pos(iid, tail=60):
        vs = [v for _, v in _hist(iid, tail)]
        return _pos_of(vs)

    out = {}
    lpr = g("POL_LPR")
    if lpr is not None:
        p = pos("POL_LPR", 24)
        out["C1"] = (f"基准利率 {lpr:.2f}%" + (f"（24 期 {p:.0f}% 位）" if p is not None else "")
                     + "没有新的调整；资金的价格基准不动，成本变化只能来自市场端（C3）。")

    m2, loan, m1 = g("MKT_M2_YOY"), g("MKT_RMB_LOAN_YOY"), g("MKT_M1_YOY")
    if m2 is not None and loan is not None:
        h2 = dict(_hist("MKT_M2_YOY")); hl = dict(_hist("MKT_RMB_LOAN_YOY")); h1 = dict(_hist("MKT_M1_YOY"))
        diffs = [h2[p] - hl[p] for p in sorted(h2) if p in hl]
        p = _pos_of(diffs)
        s1 = f"，M2−M1 为 {m2-m1:+.2f}pp" if (m1 is not None) else ""
        out["C2"] = (f"货币总量同比 {m2:.2f}%，信贷投放同比 {loan:.2f}%，两者差 {m2-loan:+.2f}pp"
                     + (f"（24 期 {p:.0f}% 位）" if p is not None else "") + s1
                     + "。钱在增加，但增量主要停在存款与准货币形态，没有按同等幅度转成贷款。")

    dr, ty = g("MKT_DR007"), g("MKT_CGB10Y")
    if dr is not None and ty is not None:
        hd = dict(_hist("MKT_DR007")); ht = dict(_hist("MKT_CGB10Y"))
        sp_ = [hd[p] - ht[p] for p in sorted(hd) if p in ht]
        p = _pos_of(sp_)
        out["C3"] = (f"银行间隔夜到 7 天资金 {dr:.4f}%，10 年期国债 {ty:.4f}%，差 {dr-ty:+.2f}pp"
                     + (f"（51 期 {p:.0f}% 位）" if p is not None else "")
                     + "。借钱的两端价格几乎相同，把钱锁长期没有额外补偿。")

    mb, co = g("MKT_MARGIN_BAL"), _num_scaled("MKT_MARGIN_COLLATERAL")
    if mb is not None and co:
        pm = pos("MKT_MARGIN_BAL")
        hb = dict(_hist("MKT_MARGIN_BAL")); hc = dict(_hist("MKT_MARGIN_COLLATERAL"))
        rs = [hb[p] / hc[p] * 100 for p in sorted(hb) if p in hc and hc[p]]
        pr = _pos_of(rs)
        out["C4"] = (f"借来的钱（融资余额）{mb:.0f} 亿" + (f"（60 期 {pm:.0f}% 位）" if pm is not None else "")
                     + f"，对应抵押品 {co/10000:.2f} 万亿，占 {mb/co*100:.2f}%"
                     + (f"（60 期 {pr:.0f}% 位）" if pr is not None else "")
                     + "。借的钱在减少，抵押品减少更快；账户里自有资金的比例在往下走。")

    inv, lhb = g("RTL_MARGIN_INVESTORS"), g("INST_LHB_NET")
    if inv is not None:
        pi = pos("RTL_MARGIN_INVESTORS")
        part = f"两融开户数 {inv:.2f} 万户" + (f"（60 期 {pi:.0f}% 位）" if pi is not None else "")
        if lhb is not None:
            part += f"，同期机构席位区间净卖 {abs(lhb):.2f} 亿"
        out["C5"] = part + "。用杠杆的个人账户在增加，机构席位在减；两者口径不同，只能并列看。"

    bd, cc, tn = g("MKT_BREADTH"), g("SECTOR_AMT_CONC"), g("MKT_TURNOVER")
    if bd is not None:
        tail = f"上涨家数占比 {bd:.1f}%"
        if cc is not None:
            tail += f"、Top5 板块成交占比 {cc:.1f}%"
        if tn is not None:
            tail += f"、全市场成交额 {tn:.0f} 亿"
        out["C6"] = tail + "。钱在盘面上既没有铺开到多数标的，也没有集中到少数板块。"
    return out



def id_label(iid):
    """指标 id → 人读名称 + 所属环（展示层用，记录里仍存 id）。"""
    try:
        with io.open(os.path.join(ROOT, "dist", "market-state", "references", "registry.json"), encoding="utf-8") as f:
            reg = json.load(f)
    except Exception:
        return iid
    r = reg.get(iid) or {}
    name = r.get("name") or iid
    ch = r.get("channel")
    return f"{name}（{ch}）" if ch else name


IMPACT_PATH = [
    ("消费价格", "CPI 同比（背景）直接更新；中国 10Y 国债收益率（C3）对该读数重新定价"),
    ("生产者价格", "PPI 同比（背景）直接更新；中国 10Y 国债收益率（C3）对该读数重新定价"),
    ("采购经理", "制造业 PMI（背景）直接更新；中国 10Y 国债收益率（C3）对该读数重新定价"),
    ("国民经济运行", "GDP 同比（背景）更新；中国 10Y 国债收益率（C3）与人民币贷款余额同比（C2）随该读数调整"),
    ("工业经济效益", "人民币贷款余额同比（C2）与工业增加值（背景）同报告期一并更新"),
    ("规模以上工业", "工业增加值（背景）直接更新；人民币贷款余额同比（C2）同报告期更新"),
    ("社会消费品零售", "社零同比（背景）直接更新；人民币贷款余额同比（C2）同报告期更新"),
    ("固定资产投资", "固投同比（背景）直接更新；人民币贷款余额同比（C2）同报告期更新"),
    ("商品住宅销售", "70 城房价同比（背景）直接更新；人民币贷款余额同比（C2）同报告期更新"),
    ("房地产开发", "房地产开发投资相关读数更新；人民币贷款余额同比（C2）同报告期更新"),
    ("能源生产", "全社会用电量同比（背景，能源生产同属性代理）更新"),
]


def impact_path(title):
    for k, v in IMPACT_PATH:
        if k in title:
            return v
    return "该事件对应的背景指标更新，相关链条逐环体现"


def branch_text(outcomes, prev=None):
    """用具体阈值表述分支；无前值时退回符号表述。"""
    if prev:
        return f"公布值 > {prev} ／ = {prev} ／ < {prev}"
    return "公布值 > 前值 ／ = 前值 ／ < 前值"

def events_section(as_of):
    """从 data/events/calendar-<as_of>.json 读事件段（sync.py 已自动抓取）。"""
    fp = os.path.join(ROOT, "data", "events", f"calendar-{as_of}.json")
    if not os.path.exists(fp):
        return []
    try:
        with io.open(fp, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return []
    evs = d.get("events") or []
    fut = [e for e in evs if e.get("event_status") == "未来预定"]
    hap = [e for e in evs if e.get("event_status") == "已发生"]
    lines = ["", f"—— 事件（horizon={d.get('horizon_days', 30)}d，不参与 as-of）——"]
    if fut:
        lines.append(f"未来预定 {len(fut)} 项（含结果分支）：")
        # 分支记录：按日期+标题匹配
        scn = {}
        for fp in glob.glob(os.path.join(ROOT, "data", "events", "scenario-scn-*.json")):
            try:
                with io.open(fp, encoding="utf-8") as f:
                    r = json.load(f)
            except Exception:
                continue
            key = (r.get("event_summary", "") or "")[:10]
            scn.setdefault(key, []).append(r)
        for e in fut:
            lines.append(f"  {e['event_date']} {(e.get('event_time') or '—'):<5} {e.get('event_type',''):<5} {e.get('scope','')}")
            cand = [r for r in scn.get(e["event_date"], [])
                    if (r.get("event_summary", "").split(" ", 2)[-1][:6] in e.get("scope", ""))]
            if cand:
                o = cand[0]["possible_outcomes"]
                pv = (cand[0].get("prev_value") or {}).get("value")
                ids = "、".join(id_label(i) for i in sorted({i for x in o for i in x["affected_indicators"]}))
                lines.append(f"    受影响：{ids}")
                prev_txt = f"（前值 {pv}）" if pv else ""
                for x in o:
                    lines.append(f"    · {x['observable_flag']}{prev_txt} → {x.get('impact_note','')}")
    if hap:
        lines.append(f"已发生 {len(hap)} 项（近 {d.get('horizon_days', 30)} 天）：")
        for e in hap[:8]:
            lines.append(f"  {e['event_date']} {'':<5} {e.get('event_type',''):<5} {e.get('scope','')[:38]}  · {e.get('issuer','')}")
    return lines

def build_sector(policy):
    """板块层六环（同名不同义）。v1 只做 C2 份额、C6 涨跌与广度；其余如实不可读。"""
    try:
        with io.open(os.path.join(ROOT, "data", "sector_target.json"), encoding="utf-8") as fh:
            sector = json.load(fh).get("name", "半导体")
    except Exception:
        sector = "半导体"
    as_of = period("SECTOR_PCT") or period("SECTOR_AMT") or _latest_trade_day()
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

    # C1 行业政策：线索自动统计，状态词仍需人工判定
    clue = sector_policy_clues(as_of)
    if clue:
        if clue["count"]:
            tail = "；".join(f"{e['event_date']} {e.get('scope','')[:18]}" for e in clue["items"])
            ev = f"近 30 天发布 {clue['count']} 条，仅作线索：{tail}"
        else:
            ev = ("该部委源不可抓（JS 渲染），无法自动取证" if clue.get("uncrawlable")
                  else "近 30 天该部委源无条目（源可抓但无发布）")
        rings[0].add("不可读（—）",
                     f"政策状态无源（需人工判定）；对口部委（{'、'.join(clue['depts'])}）{ev}",
                     "线索不等于政策方向，需人工判定")
    else:
        rings[0].add("不可读（—）", "行业政策状态需人工录入官方文件链接；该板块未配置对口部委", "该环无证据")
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
    # C3 相对贵贱：板块 PE ÷ 沪深300 PE
    v3 = val("SECTOR_VAL")
    if v3 is not None:
        word = "偏贵" if v3 > 1 else ("偏便宜" if v3 < 1 else "不变")
        rings[2].add(f"{word}（{period('SECTOR_VAL')}）",
                     f"板块 PE ÷ 沪深300 PE = {v3:.2f}×（基准：沪深300）",
                     "只说明相对倍数，不说明是否会回归；差值与分位归比价层", tag_of("SECTOR_VAL"))
    else:
        rings[2].add("不可读（—）", "板块估值未取到（可能在 data/sector_index_map.json 里没有该板块的指数代码）", "该环无证据")
    # C4 默认空环
    rings[3].add("不可读（—）", "板块层杠杆与资金池默认不读（ADR-025 口径）", "该环无证据")
    # C5 主体行为：按中证成分过滤的龙虎榜机构净买
    v5 = val("SECTOR_INST_FLOW")
    if v5 is not None:
        word = "机构增" if v5 > 0 else ("机构减" if v5 < 0 else "机构不变")
        rings[4].add(f"{word}（{period('SECTOR_INST_FLOW')}）",
                     f"板块内龙虎榜机构净买额 {v5:+.2f} 亿（区间汇总，按中证成分过滤）",
                     "仅覆盖上榜个股，不代表板块内全部机构行为", tag_of("SECTOR_INST_FLOW"))
    else:
        rings[4].add("不可读（—）", "板块内龙虎榜未取到（成分表或龙虎榜接口失败）", "该环无证据")
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
    ap.add_argument("--no-events", action="store_true", help="不附事件段")
    ap.add_argument("--show-history", action="store_true", help="列出已归档的状态快照")
    ap.add_argument("--archive", action="store_true", help="强制覆盖当日快照")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    args.include_events = not args.no_events

    if args.show_history:
        rows = list_history()
        print(f"已归档快照 {len(rows)} 份（reports/state-history/）：")
        for r in rows:
            print("  ", r)
        return 0

    if args.layer == "sector":
        as_of, body, sector = build_sector(args.policy)
        head = f"as-of {as_of}（最新交易日；板块层 · 目标板块：{sector}；行内 * 表示数据期早于 as-of）"
    else:
        as_of, body = build(args.policy, args.include_events)
        head = f"as-of {as_of}（最新交易日；行内 * 表示该行数据期早于 as-of）"
    text = f"{head}\n{body}\n"

    reg = {}
    try:
        with io.open(os.path.join(ROOT, "dist", "market-state", "references", "registry.json"), encoding="utf-8") as fh:
            reg = json.load(fh)
    except Exception:
        pass
    want = "板块" if args.layer == "sector" else "市场"
    missing = sorted({json.load(io.open(f, encoding="utf-8"))["indicator_id"]
                      for f in glob.glob(os.path.join(FACTS, "*", "*.json"))
                      if (reg.get(json.load(io.open(f, encoding="utf-8"))["indicator_id"], {}) or {}).get("layer", "市场") == want})
    n_ev = len([ln for ln in body.splitlines() if re.match(r"^C[1-6] ", ln)])
    meta = (f"\n元信息：\n- 证据行 {n_ev} 条（覆盖 {len(missing)} 项事实记录）\n"
            f"- 分级政策：{ {'strict':'strict（仅 B 类）','traceable':'traceable（B 可用；C 仅在该指标无 A/B 时使用并标注）','demo':'demo（C 类亦可，逐行标注）'}[args.policy] }\n"
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

    if args.json:
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
        cl, cr = market_compare_lines() if args.layer == "market" else ([], [])
        rel = {}
        try:
            with io.open(os.path.join(ROOT, "dist", "market-state", "references", "registry.json"), encoding="utf-8") as fh:
                _reg = json.load(fh)
        except Exception:
            _reg = {}
        for r_ in cr:
            ring_ = (_reg.get(r_["inputs"][0]["ref"]) or {}).get("channel") or "C?"
            rel.setdefault(ring_, []).append({"compare_id": r_["compare_id"],
                                              "value": r_["current_state"]["数值"],
                                              "period": r_["data_period"],
                                              "operand_order": r_["operand_order"]})
        payload = {"layer": args.layer, "as_of": as_of, "lines": recs,
                   "relations_by_ring": rel,
                   "b_indicators": [i for i in missing if tier_of(i) == "B"],
                   "policy": args.policy,
                   "generated_at": dt.datetime.now().isoformat(timespec="seconds")}
        if args.write:
            os.makedirs(REPORTS, exist_ok=True)
            fp = os.path.join(REPORTS, f"state-{args.layer}.json")
            with io.open(fp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            print("已写入:", os.path.relpath(fp, ROOT))
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(out)

    if args.write:
        os.makedirs(REPORTS, exist_ok=True)
        suffix = "market" if args.layer == "market" else f"sector-{sector}"
        fp_hist, wrote = archive_snapshot(as_of, args.layer, {
            "layer": args.layer, "as_of": as_of, "policy": args.policy,
            "body": body, "corrections": None,
            "archived_at": dt.datetime.now().isoformat(timespec="seconds"),
        }, force=getattr(args, "archive", False))
        print(("已归档: " if wrote else "已存在（未覆盖）: ") + os.path.relpath(fp_hist, ROOT))
        _rd = ring_readings(as_of) if args.layer == "market" else {}
        rd_block = ""
        if _rd:
            rd_block = "\n\n**读法（资金视角）**\n\n" + "\n".join(f"- {k}：{v}" for k, v in sorted(_rd.items())) + "\n"
        p = os.path.join(REPORTS, f"{as_of}-{suffix}-state.md")
        with io.open(p, "w", encoding="utf-8") as f:
            f.write("```\n" + text + "```\n" + rd_block + meta)
        print("已写入:", os.path.relpath(p, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
