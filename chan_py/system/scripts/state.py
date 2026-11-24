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

    # C4 深市融资余额（交易所官方，T+1 披露）
    ok, tag = allow("MKT_MARGIN_BAL_SZ")
    v = val("MKT_MARGIN_BAL_SZ")
    _pv = val("MKT_MARGIN_BAL_SZ", "prev_value")
    if ok and v is not None and _pv is not None:
        word = "不变" if v == _pv else ("加杠杆" if v > _pv else "去杠杆")
        rings[3].add(f"深市{word}（{period('MKT_MARGIN_BAL_SZ')}）",
                     f"深市融资余额 {v:,.2f} 亿元 对比上一期 {_pv:,.2f} 亿元（深交所官方，T+1）",
                     "只覆盖深市，不含沪市；不与全市场口径相加", tag)
    elif ok and v is not None:
        rings[3].add("不可读（—）",
                     f"无证据可判方向：深市融资余额 {v:,.2f} 亿元（深交所官方，T+1），仅单日数据",
                     "只覆盖深市，不含沪市；次日累积后即可判方向", tag)

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

    # C5 产业资本（巨潮公告条数口径）
    ok, tag = allow("INST_INSIDER_NET")
    v = val("INST_INSIDER_NET")
    if ok and v is not None:
        word = "净减持" if v > 0 else ("净增持" if v < 0 else "持平")
        rings[4].add(f"产业资本{word}（{period('INST_INSIDER_NET')}）",
                     f"近 30 天减持公告与增持公告条数之差 {v:+.0f} 条（巨潮全文检索）",
                     "只说明公告条数，不代表金额与规模", tag)

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
            _verb = {"difference": "减", "ratio": "除"}.get(op, "对比")
            _l, _r = id_label(left).split("（")[0], id_label(right).split("（")[0]
            msg = str(e)
            for _iid, _nm in ((left, _l), (right, _r)):
                msg = msg.replace(_iid, _nm)
            msg = (msg.replace("平铺会把不同口径混在一个数里", "两者不同日期，混在一起算会失真")
                      .replace("口径锚：", "口径不同："))
            out.append(f"  {_l} {_verb} {_r}：暂不可比——{msg}")
            continue
        records.append(rec)
        verb = {"difference": "减", "ratio": "除", "spread": "减", "rank": "排名于"}.get(op, "对比")
        lhs, rhs = id_label(left).split("（")[0], id_label(right).split("（")[0]
        _names = {"MKT_M2_YOY": "M2 同比", "MKT_M1_YOY": "M1 同比",
                  "MKT_RMB_LOAN_YOY": "人民币贷款余额同比", "MKT_DR007": "DR007",
                  "MKT_CGB10Y": "10Y 国债收益率", "MKT_MARGIN_BAL": "两融余额",
                  "MKT_MARGIN_COLLATERAL": "两融担保物总价值"}
        _op_txt = rec["operand_order"]
        for _k, _v in _names.items():
            _op_txt = _op_txt.replace(_k, _v)
        out.append(f"  {lhs} {verb} {rhs} = {rec['current_state']['数值']}"
                   f"（数据期 {rec['data_period']}；口径顺序 {_op_txt}）")
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
            parts.append(f"{ring} 缺{names}")
            broken.append(f"{ring} 的{names}")
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


def sector_policy_clues(as_of, horizon=30, sector=None):
    """板块层 C1 的政策线索：数对口部委近 N 天发布条数（只作线索，不给状态词）。"""
    mp = os.path.join(ROOT, "data", "sector_dept_map.json")
    if not os.path.exists(mp):
        return None
    # 政策线索是"近 30 天"，与板块 as_of 无关 → 一律用最新一份日历
    cals = sorted(glob.glob(os.path.join(ROOT, "data", "events", "calendar-*.json")))
    cal = json.load(io.open(cals[-1], encoding="utf-8")) if cals else None
    if not cal:
        return None
    try:
        with io.open(mp, encoding="utf-8") as f:
            depts = (json.load(f).get("map") or {}).get(sector or _sector_name(), [])
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
    """每环一句「读法」：先说数字与位置，再说这些数字在钱上意味着什么。

    硬约束：只用已落盘数字；不用因果词；不做方向判断；
    **不复述证据行里已写过的"边界"、不写免责声明、不出现同义重复。**
    """
    def g(iid):
        return val(iid)

    def pos(iid, tail=60):
        vs = [v for _, v in _hist(iid, tail)]
        return _pos_of(vs)

    def prev(iid):
        h = _hist(iid, 400)
        return h[-2][1] if len(h) >= 2 else None

    out = {}
    lpr = g("POL_LPR")
    if lpr is not None:
        p = pos("POL_LPR", 24)
        out["C1"] = (f"基准利率 {lpr:.2f}%" + (f"，24 期最低档" if p is not None and p < 5 else "")
                     + "。政策端的价格没有动，资金成本的任何变化都只能来自市场端（C3）。")

    m2, loan, m1 = g("MKT_M2_YOY"), g("MKT_RMB_LOAN_YOY"), g("MKT_M1_YOY")
    if m2 is not None and loan is not None:
        h2 = dict(_hist("MKT_M2_YOY")); hl = dict(_hist("MKT_RMB_LOAN_YOY"))
        diffs = [h2[p] - hl[p] for p in sorted(h2) if p in hl]
        p = _pos_of(diffs)
        d = m2 - loan
        head = (f"货币同比 {m2:.2f}%，信贷同比 {loan:.2f}%，"
                f"货币多放 {abs(d):.2f}pp" + (f"（24 期 {p:.0f}% 位）" if p is not None else ""))
        if m1 is not None and m2 - m1 > 0:
            head += f"，活期比总量又低 {m2-m1:.2f}pp"
        if d > 0:
            tail = "钱多出来的部分留在存款和准货币里，没有按同样幅度变成贷款。"
        elif d < 0:
            tail = "信贷比货币跑得快，钱更多是以贷款形式放出去的。"
        else:
            tail = "两条线同速，谁也没有跑在前面。"
        out["C2"] = head + "。" + tail

    dr, ty = g("MKT_DR007"), g("MKT_CGB10Y")
    if dr is not None and ty is not None:
        hd = dict(_hist("MKT_DR007")); ht = dict(_hist("MKT_CGB10Y"))
        sp_ = [hd[p] - ht[p] for p in sorted(hd) if p in ht]
        p = _pos_of(sp_)
        sp = dr - ty
        head = (f"短端 {dr:.2f}%、长端 {ty:.2f}%，长端只比短端高 {abs(sp)*100:.0f}bp"
                + (f"（51 期 {p:.0f}% 高位）" if p is not None else ""))
        if abs(sp) < 0.05:
            tail = "两头几乎一个价，把钱锁长期基本没有额外回报。"
        elif sp > 0:
            tail = "借短钱反而更贵，期限出现倒挂。"
        else:
            tail = "锁长期能多拿一点，但这点补偿很薄。"
        out["C3"] = head + "。" + tail

    mb, co = g("MKT_MARGIN_BAL"), _num_scaled("MKT_MARGIN_COLLATERAL")
    if mb is not None and co:
        pm = pos("MKT_MARGIN_BAL")
        hb = dict(_hist("MKT_MARGIN_BAL")); hc = dict(_hist("MKT_MARGIN_COLLATERAL"))
        rs = [hb[p] / hc[p] * 100 for p in sorted(hb) if p in hc and hc[p]]
        pr = _pos_of(rs)
        pv = prev("MKT_MARGIN_BAL")
        trend = ("借钱的人在减少" if (pv is not None and mb < pv) else
                 ("借钱的人在增加" if (pv is not None and mb > pv) else "借钱的人没有变化"))
        out["C4"] = (f"融资余额 {mb:.0f} 亿" + (f"，处 60 期最低" if pm is not None and pm < 5 else "")
                     + f"；抵押品 {co/10000:.2f} 万亿，余额占抵押品的 {mb/co*100:.2f}%"
                     + (f"，处 60 期最高" if pr is not None and pr > 95 else "")
                     + f"。{trend}，抵押品缩得更快，账户里的自有部分被压薄。")

    inv, lhb = g("RTL_MARGIN_INVESTORS"), g("INST_LHB_NET")
    if inv is not None:
        pi = pos("RTL_MARGIN_INVESTORS")
        pvi = prev("RTL_MARGIN_INVESTORS")
        inv_txt = ("还在增加" if (pvi is not None and inv > pvi) else
                   ("在减少" if (pvi is not None and inv < pvi) else "持平"))
        head = f"两融开户 {inv:.2f} 万户" + (f"，处 60 期最高" if pi is not None and pi > 95 else "")
        tail = f"，且{inv_txt}"
        if lhb is not None:
            tail += ("；机构席位 7 日净卖 " + f"{abs(lhb):.2f} 亿") if lhb < 0 else ("；机构席位 7 日净买 " + f"{abs(lhb):.2f} 亿")
        out["C5"] = head + tail + "。散户在加杠杆，机构在另一边。"

    bd, cc, tn = g("MKT_BREADTH"), g("SECTOR_AMT_CONC"), g("MKT_TURNOVER")
    if bd is not None:
        head = f"上涨家数 {bd:.1f}%"
        if cc is not None:
            head += f"，成交最多的 5 个板块占 {cc:.1f}%"
        pt = prev("MKT_TURNOVER")
        if tn is not None:
            head += f"，全市场 {tn:.0f} 亿"
            if pt is not None and abs(tn - pt) > 1:
                head += f"（较上一交易日 {'+' if tn > pt else '−'}{abs(tn-pt):.0f} 亿）"
        breadth_txt = "钱铺到了大多数标的" if bd >= 50 else "钱没能铺开到多数标的"
        conc_txt = "，但没有聚在少数板块里。" if (cc is not None and cc < 50) else (
                   "，并且集中在少数板块。" if cc is not None else "。")
        out["C6"] = head + "。" + breadth_txt + conc_txt
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

def _calendar_for(as_of):
    """取日历：优先当天；没有就退到最新一份，并返回其 as_of。"""
    fs = sorted(glob.glob(os.path.join(ROOT, "data", "events", "calendar-*.json")))
    exact = os.path.join(ROOT, "data", "events", f"calendar-{as_of}.json")
    fp = exact if os.path.exists(exact) else (fs[-1] if fs else None)
    if not fp:
        return None, None
    try:
        with io.open(fp, encoding="utf-8") as f:
            cal = json.load(f)
    except Exception:
        return None, None
    return cal, (cal.get("as_of") or os.path.basename(fp)[9:-5])


def sector_events_section(as_of, sector):
    """板块层事件段：只出与本板块相关的事件（关键词命中的板块公告 + 对口部委）。"""
    d, cal_as_of = _calendar_for(as_of)
    if not d:
        return []
    evs = d.get("events") or []
    kw = [sector]
    try:
        with io.open(os.path.join(ROOT, "data", "sector_dept_map.json"), encoding="utf-8") as f:
            depts = (json.load(f).get("map") or {}).get(sector, [])
    except Exception:
        depts = []
    hits = [e for e in evs
            if (e.get("layer") == "板块" and sector in (e.get("scope") or ""))
            or any(x in (e.get("issuer") or "") for x in depts)]
    if not hits:
        return []
    fut = [e for e in hits if e.get("event_status") == "未来预定"]
    past = [e for e in hits if e.get("event_status") == "已发生"]
    out = ["", f"—— 板块事件（{sector}；horizon={d.get('horizon_days', 30)}d；日历 {cal_as_of}）——",
           f"共 {len(hits)} 条：未来预定 {len(fut)} · 已发生 {len(past)}"]
    for e in (fut + past)[:12]:
        out.append(f"  {e.get('event_date')} {(e.get('event_time') or '—'):<5} {e.get('issuer','')[:10]:<10} {e.get('scope','')[:52]}")
    if len(hits) > 12:
        out.append(f"  … 另 {len(hits)-12} 条")
    return out


def events_section(as_of):
    """读事件段：优先当天日历；没有就用最新一份，并在段首标出日历日期。"""
    d, cal_as_of = _calendar_for(as_of)
    if not d:
        return []
    evs = [e for e in (d.get("events") or []) if (e.get("layer") or "市场") == "市场"]
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
                    lines.append(f"    · {x.get('impact_note') or x['observable_flag']}")
    if hap:
        lines.append(f"已发生 {len(hap)} 项（近 {d.get('horizon_days', 30)} 天）：")
        for e in hap[:8]:
            lines.append(f"  {e['event_date']} {'':<5} {e.get('event_type',''):<5} {e.get('scope','')[:38]}  · {e.get('issuer','')}")
    return lines


# ---------------------------------------------------------------- 申万二级板块（SW）
SW_DIR = os.path.join(ROOT, "data", "sw")



SW_ALIAS = {"医药": "医药生物", "化工": "基础化工", "电力": "公用事业",
            "银行": "银行", "券商": "非银金融", "保险": "非银金融"}


def _sw_sectors_of(name):
    """板块名 → 申万二级列表：先按二级名精确匹配，退回按一级行业(parent)匹配多只。"""
    name = SW_ALIAS.get(name, name)
    try:
        with io.open(os.path.join(SW_DIR, "sectors.json"), encoding="utf-8") as f:
            secs = (json.load(f) or {}).get("sectors") or []
    except Exception:
        return []
    exact = [x for x in secs if x.get("name") == name]
    if exact:
        return exact
    return [x for x in secs if x.get("parent") == name]


def _sw_sector_of(name):
    """板块名 → 申万二级代码（按名称精确/包含匹配）。"""
    try:
        with io.open(os.path.join(SW_DIR, "sectors.json"), encoding="utf-8") as f:
            secs = (json.load(f) or {}).get("sectors") or []
    except Exception:
        return None
    for x in secs:
        if x.get("name") == name:
            return x
    for x in secs:
        if name and (name in (x.get("name") or "") or (x.get("name") or "") in name):
            return x
    return None


def _sw_panel(latest=True):
    """最近一份申万二级当日面板（价/量/成交额/PE）。"""
    d = os.path.join(SW_DIR, "daily")
    if not os.path.isdir(d):
        return None
    fs = sorted(glob.glob(os.path.join(d, "*.json")))
    if not fs:
        return None
    try:
        with io.open(fs[-1], encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _sw_hist_amount(code):
    """板块成交额历史（亿元）：返回 [(date, amount)]。"""
    fp = os.path.join(SW_DIR, "history", f"{code}.jsonl")
    if not os.path.exists(fp):
        return []
    out = []
    with io.open(fp, encoding="utf-8") as f:
        next(f, None)
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if r.get("amount") is not None:
                    out.append((r["date"], r["amount"]))   # index_hist_sw 的成交额已是亿元
            except Exception:
                continue
    return out



def _sw_breadth(code):
    """申万板块内上涨家数占比（当日），来自 data/sw/breadth/<date>.json。"""
    d = os.path.join(SW_DIR, "breadth")
    if not os.path.isdir(d):
        return None, None
    fs = sorted(glob.glob(os.path.join(d, "*.json")))
    if not fs:
        return None, None
    try:
        with io.open(fs[-1], encoding="utf-8") as f:
            obj = json.load(f)
    except Exception:
        return None, None
    for r in obj.get("sectors") or []:
        if r.get("code") == code:
            return r.get("breadth"), obj.get("date")
    return None, obj.get("date")



def _sw_margin_of(code):
    """申万板块内个股（深市部分）融资余额合计：返回 (合计亿元, 覆盖只数, 数据日)。"""
    mdir = os.path.join(SW_DIR, "margin")
    if not os.path.isdir(mdir):
        return None, 0, None
    fs = sorted(glob.glob(os.path.join(mdir, "*.json")))
    if not fs:
        return None, 0, None
    try:
        with io.open(fs[-1], encoding="utf-8") as f:
            m = json.load(f)
    except Exception:
        return None, 0, None
    cons = {}
    try:
        with io.open(os.path.join(SW_DIR, "constituents.json"), encoding="utf-8") as f:
            cons = (json.load(f).get("sectors") or {})
    except Exception:
        return None, 0, None
    codes = (cons.get(code) or {}).get("codes") or []
    bal = m.get("fin_bal") or {}
    hit = [bal[c] for c in codes if c in bal]
    if not hit:
        return None, 0, m.get("date")
    return sum(hit), len(hit), m.get("date")



def _sector_val_of(sector):
    """板块估值倍数：从 data/cache/sector_val_by_sector.json 按板块名取。"""
    fp = os.path.join(ROOT, "data", "cache", "sector_val_by_sector.json")
    if not os.path.exists(fp):
        return None
    try:
        with io.open(fp, encoding="utf-8") as f:
            by = (json.load(f) or {}).get("by_sector") or {}
    except Exception:
        return None
    return by.get(sector)



def _sector_lhb_sw(sector):
    """板块内龙虎榜净买（申万成分口径）：按板块（支持一级行业展开）汇总。"""
    fp = os.path.join(ROOT, "data", "cache", "sector_lhb_by_sector.json")
    if not os.path.exists(fp):
        return None, None, 0
    try:
        with io.open(fp, encoding="utf-8") as f:
            obj = json.load(f)
        by = obj.get("by_sector") or {}
    except Exception:
        return None, None, 0
    codes = [x["code"] for x in _sw_sectors_of(sector)]
    vals = [by[c] for c in codes if c in by]
    if not vals:
        return None, obj.get("data_period"), 0
    return sum(v["net"] for v in vals), obj.get("data_period"), sum(v["n"] for v in vals)


def sector_readings(sector, rings_data):
    """板块层「读法」：用资金视角解释六环数字（对齐市场层 R11）。

    rings_data 里放本环已算出的数：份额/倍数/两融/龙虎榜/涨跌/广度/成交额。
    约束同 R11：只用已落盘数字；先数字后含义；不用因果词；不做方向判断。
    """
    d = rings_data or {}
    out = {}

    # C1 政策
    if d.get("clue"):
        c = d["clue"]
        out["C1"] = (f"对口部委近 30 天高信息量发布 {c['count']} 条（政策类 {c.get('pol', 0)} 条）。"
                     f"政策方向不在数据里，需要人工给结论。")

    # C2 份额
    if d.get("share") is not None:
        sh, pv, pos = d["share"], d.get("share_prev"), d.get("share_pos")
        head = f"这个板块吃下全市场成交额的 {sh:.2f}%"
        if pv is not None:
            head += f"，上一交易日 {pv:.2f}%"
        if pos is not None:
            head += f"（{d.get('share_n', 0)} 期 {pos:.0f}% 位）"
        tail = ("钱分给它的比例在变多。" if (pv is not None and sh > pv + 0.05) else
                ("钱分给它的比例在变少。" if (pv is not None and sh < pv - 0.05) else
                 "钱分给它的比例没有明显变化。"))
        out["C2"] = head + "。" + tail

    # C3 贵贱
    if d.get("ratio") is not None:
        r = d["ratio"]
        word = "贵" if r > 1 else "便宜"
        out["C3"] = (f"板块 PE {d.get('sec_pe', 0):.2f}，是沪深300 的 {r:.2f} 倍，"
                     f"相对全市场{word} {abs(r-1)*100:.0f}%。倍数本身不说明会不会回去。")

    # C4 杠杆
    if d.get("margin") is not None:
        out["C4"] = (f"板块内 {d.get('margin_n', 0)} 只深市标的融资余额合计 {d['margin']:,.2f} 亿元，"
                     f"这是场内借来的钱在板块里的规模（沪市未纳入，也没有前值可比）。")

    # C5 主体
    if d.get("lhb") is not None:
        side = "净卖出" if d["lhb"] < 0 else ("净买入" if d["lhb"] > 0 else "净额为零")
        out["C5"] = (f"近 7 日板块内 {d.get('lhb_n', 0)} 只个股上榜龙虎榜，合计{side} {abs(d['lhb']):.2f} 亿元。"
                     f"只覆盖上榜的少数个股。")

    # C6 结果
    parts = []
    if d.get("pct") is not None:
        parts.append(f"成交额加权涨跌 {d['pct']:+.2f}%")
    if d.get("breadth") is not None:
        parts.append(f"上涨家数 {d['breadth']:.1f}%")
    if d.get("amount") is not None:
        parts.append(f"成交 {d['amount']:.0f} 亿")
    if parts:
        bd = d.get("breadth")
        tail = ("" if bd is None else
                ("钱铺到了板块内多数标的。" if bd >= 50 else "钱只落在板块内少数标的上。"))
        out["C6"] = "、".join(parts) + "。" + tail
    return out


def build_sector(policy, sector=None):
    """板块层六环（同名不同义）。sector 为空时读 data/sector_target.json。"""
    if not sector:
        try:
            with io.open(os.path.join(ROOT, "data", "sector_target.json"), encoding="utf-8-sig") as fh:
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

    _rd_data = {}          # 读法用：把证据行里算出的数字同步存一份，避免重算不一致

    def tag_of(iid):
        t = tier_of(iid)
        if t == "B":
            return ""
        reason = C_REASONS.get(iid) or "唯一可得来源，未对账"
        return f"〔C 类·{reason[:16]}…〕"

    # C1 行业政策：线索自动统计，状态词仍需人工判定
    clue = sector_policy_clues(as_of, sector=sector)
    if clue:
        if clue["count"]:
            # 政策类优先展示全称，最多 3 条；其余折叠为条数
            _items = sorted([e for e in clue["items"]], key=lambda e: (
                0 if any(k in (e.get("scope") or "") for k in ("通知", "意见", "办法", "规划", "方案", "规定", "公告"))
                else 1, e.get("event_date") or ""))
            try:
                import importlib.util as _ilu
                _sp = _ilu.spec_from_file_location("ev_mod", os.path.join(ROOT, "scripts", "events.py"))
                _ev = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_ev)
                _info = _ev.info_level
            except Exception:
                _info = lambda t: "mid"
            _pol = [e for e in _items if _info(e.get("scope") or "") == "high"]
            _show = (_pol or _items)[:3]
            tail = "；".join(f"{e['event_date']} {e.get('scope','')[:46]}" for e in _show)
            _rd_data["clue"] = {"count": clue["count"], "pol": len(_pol)}
            ev = (f"近 30 天对口部委**高信息量**事件 {clue['count']} 条（行程/活动类已滤除）；"
                  f"最近：{tail}" + (f"；另 {max(0, clue['count']-len(_show))} 条" if clue["count"] > len(_show) else ""))
        else:
            ev = ("该部委源不可抓（JS 渲染），无法自动取证" if clue.get("uncrawlable")
                  else "近 30 天该部委源无条目（源可抓但无发布）")
        rings[0].add("不可读（—）",
                     f"政策状态无源（需人工判定）；对口部委（{'、'.join(clue['depts'])}）{ev}",
                     "线索不等于政策方向，需人工判定")
    else:
        rings[0].add("不可读（—）", "行业政策状态需人工录入官方文件链接；该板块未配置对口部委", "该环无证据")
    # C2 供给份额：优先申万口径（有历史，可出前值与分位）；没有就退回同花顺快照
    sw_list = _sw_sectors_of(sector)
    sw = sw_list[0] if sw_list else None
    sw_share_done = False
    if sw_list:
        # 一级行业：把各二级板块同一天的成交额相加
        merged = {}
        for _x in sw_list:
            for d_, a_ in _sw_hist_amount(_x["code"]):
                merged[d_] = merged.get(d_, 0) + a_
        amt = sorted(merged.items())
        mkt = [(p_, v_) for p_, v_ in _hist("MKT_TURNOVER", 400)]
        mkt_d = dict(mkt)
        shares = [(d_, a_ / mkt_d[d_] * 100) for d_, a_ in amt if mkt_d.get(d_)]
        if len(shares) >= 3:
            cur_d, cur_s = shares[-1]
            prev_s = shares[-2][1]
            pos = _pos_of([x[1] for x in shares])
            word = "份额升" if cur_s > prev_s + 0.05 else ("份额降" if cur_s < prev_s - 0.05 else "不变")
            rings[1].add(f"{word}（{cur_d}）",
                         f"{sector}板块成交额占全市场 {cur_s:.2f}%，上一交易日 {prev_s:.2f}%"
                         + (f"（{len(shares)} 期 {pos:.0f}% 位）" if pos is not None else ""),
                         "只说明成交份额，不说明资金进出的方向",
                         "〔C 类·申万二级指数成交额 ÷ 全市场成交额，未对账…〕")
            _rd_data.update({"share": cur_s, "share_prev": prev_s, "share_pos": pos, "share_n": len(shares)})
            sw_share_done = True
    v = val("SECTOR_SHARE") if not sw_share_done else None
    p, prev_period = prev_value_from_revisions("SECTOR_SHARE", period("SECTOR_SHARE"))
    if (not sw_share_done) and v is not None and p is not None:
        word = "份额升" if v > p else ("份额降" if v < p else "不变")
        rings[1].add(f"{word}（{period('SECTOR_SHARE')}）",
                     f"{sector}板块成交额占比 {v:.2f}% 对比上一期 {p:.2f}%（{prev_period}）",
                     "只说明成交份额，不说明资金进出的方向", tag_of("SECTOR_SHARE"))
    elif (not sw_share_done) and v is not None:
        rings[1].add("不可读（—）", f"份额已有 {v:.2f}%，但修订链无更早数据期、无证据可作前值（首次落盘）",
                     "该环暂无法判方向")
    elif not sw_share_done:
        rings[1].add("不可读（—）", "板块成交额或全市场成交额缺失", "该环无证据")
    # C3 相对贵贱：板块 PE ÷ 沪深300 PE
    _idx_map = {}
    try:
        with io.open(os.path.join(ROOT, "data", "sector_index_map.json"), encoding="utf-8") as f:
            _idx_map = (json.load(f).get("map") or {})
    except Exception:
        _idx_map = {}
    _has_own_index = bool(_idx_map.get(sector))
    _sv = _sector_val_of(sector) if _has_own_index else None
    v3 = _sv["ratio"] if _sv else None
    if v3 is not None:
        word = "偏贵" if v3 > 1 else ("偏便宜" if v3 < 1 else "不变")
        _rd_data.update({"ratio": v3, "sec_pe": _sv["sec_pe"]})
        rings[2].add(f"{word}（{_sv.get('period')}）",
                     f"板块 PE {_sv['sec_pe']:.2f} ÷ 沪深300 PE {_sv['mkt_pe']:.2f} = {v3:.2f}×（基准：沪深300）",
                     "只说明相对倍数，不说明是否会回归；差值与分位归比价层", tag_of("SECTOR_VAL"))
    else:
        rings[2].add("不可读（—）",
                     f"无源：{sector} 未在 data/sector_index_map.json 映射到中证行业指数，板块 PE 无法计算"
                     + ("（一级行业需选具体二级板块）" if len(sw_list) > 1 else ""),
                     "该环无证据")
    # C4 杠杆与资金池：用深市个股两融 × 申万成分 汇总（仅深市部分）
    mbal, mn, mday = (None, 0, None)
    if sw_list:
        _tot_m, _tot_n, _d0 = 0.0, 0, None
        for _x in sw_list:
            _b, _n, _d = _sw_margin_of(_x["code"])
            if _b is not None:
                _tot_m += _b; _tot_n += _n; _d0 = _d0 or _d
        if _tot_n:
            mbal, mn, mday = _tot_m, _tot_n, _d0
    if mbal is not None:
        _rd_data.update({"margin": mbal, "margin_n": mn})
        rings[3].add("不可读（—）",
                     f"无前值（无证据可判方向）：板块内 {mn} 只深市标的融资余额合计 {mbal:,.2f} 亿元"
                     f"（深交所官方明细汇总，{mday}），仅单日数据",
                     "仅覆盖深市标的，沪市未纳入；次日累积后即可判方向",
                     "〔C 类·深交所两融明细 × 申万二级成分，自算汇总…〕")
    else:
        rings[3].add("不可读（—）", "板块层杠杆无可用口径（沪市两融无公开接口；深市明细未拉到）", "该环无证据")
    # C5 主体行为：按中证成分过滤的龙虎榜机构净买
    _lhb, _lhb_d, _lhb_n = _sector_lhb_sw(sector)
    v5 = _lhb     # 只用本板块（申万成分）口径；不得回退到配置里的目标板块数值
    if v5 is not None:
        _rd_data.update({"lhb": v5, "lhb_n": _lhb_n})
        word = "机构增" if v5 > 0 else ("机构减" if v5 < 0 else "机构不变")
        rings[4].add(f"{word}（{_lhb_d or period('SECTOR_INST_FLOW')}）",
                     f"板块内上榜个股龙虎榜净买额 {v5:+.2f} 亿（近 7 日累计，{_lhb_n} 只；申万成分口径）",
                     "仅覆盖上榜个股，不代表板块内全部机构行为", tag_of("SECTOR_INST_FLOW"))
    else:
        rings[4].add("不可读（—）",
                     "无证据：板块内近 7 日无个股上榜，或成分表缺失", "该环暂无可用证据")
    # C6 结果：涨跌幅（优先申万当日面板，与份额、广度和广度同日）+ 板块内广度
    sw_panel = _sw_panel()
    sw_pct_done = False
    if sw_list and sw_panel and len(sw_list) > 1:
        _rows = {x.get("code"): x for x in (sw_panel.get("sectors") or [])}
        _num = _den = 0.0
        for _x in sw_list:
            _r = _rows.get(_x["code"])
            if _r and _r.get("pct") is not None and _r.get("amount"):
                _num += _r["pct"] * _r["amount"]
                _den += _r["amount"]
        if _den:
            pct_agg = _num / _den
            _tot = sum((_rows.get(_x["code"]) or {}).get("amount") or 0 for _x in sw_list)
            word = "升" if pct_agg > 0 else ("降" if pct_agg < 0 else "不变")
            _rd_data.update({"pct": pct_agg, "amount": _tot})
            rings[5].add(f"{word}（{sw_panel.get('date')}）",
                         f"{sector}（{len(sw_list)} 个二级行业）成交额加权涨跌幅 {pct_agg:+.2f}%，合计成交 {_tot:.0f} 亿",
                         "一级行业无单一指数，此处为二级加权",
                         "〔C 类·申万二级实时行情加权，未对账…〕")
            sw_pct_done = True
    if sw and sw_panel and not sw_pct_done:
        row = next((x for x in (sw_panel.get("sectors") or []) if x.get("code") == sw["code"]), None)
        if row and row.get("pct") is not None:
            pct_sw = float(row["pct"])
            word = "升" if pct_sw > 0 else ("降" if pct_sw < 0 else "不变")
            _rd_data.update({"pct": pct_sw, "amount": row.get("amount")})
            rings[5].add(f"{word}（{sw_panel.get('date')}）",
                         f"{sector}板块指数涨跌幅 {pct_sw:+.2f}%（收 {row.get('close')}，成交 {row.get('amount')} 亿）",
                         "不说明板块内个股结构",
                         "〔C 类·申万二级指数实时行情，未对账…〕")
            sw_pct_done = True
    pct = None if sw_pct_done else val("SECTOR_PCT")
    if sw_pct_done:
        pass
    elif pct is not None:
        word = "升" if pct > 0 else ("降" if pct < 0 else "不变")
        rings[5].add(f"{word}（{period('SECTOR_PCT')}）", f"{sector}板块指数涨跌幅 {pct:+.2f}%", "不说明板块内个股结构", tag_of("SECTOR_PCT"))
    else:
        rings[5].add("不可读（—）", "板块指数日线缺失", "该环无证据")
    sw_b, sw_b_day = (_sw_breadth(sw["code"]) if sw else (None, None))
    b = sw_b if sw_b is not None else val("SECTOR_BREADTH")
    b_period = sw_b_day if sw_b is not None else period("SECTOR_BREADTH")
    if b is not None:
        _rd_data["breadth"] = b
        word = "强" if b > 50 else ("弱" if b < 50 else "不变")
        src_tag = ("〔C 类·申万二级成分 + 全市场个股涨跌幅，未对账…〕" if sw_b is not None
                   else tag_of("SECTOR_BREADTH"))
        rings[5].add(f"广度{word}（{b_period}）", f"{sector}板块上涨家数占比 {b:.1f}%（阈值 50%）",
                     "只说明广度，不说明幅度", src_tag)

    daily = [period(i) for i in ("SECTOR_PCT", "SECTOR_BREADTH", "SECTOR_AMT") if period(i)]
    if sw_panel and sw_panel.get("date"):
        daily.append(sw_panel["date"])
    as_of = max(daily) if daily else "不可用"
    normalize_dates(rings, as_of)
    body = "\n".join("\n".join(r_.lines) for r_ in rings)
    # 板块层也带链条完整性
    _cl, _broken = chain_summary([ln for ln in body.splitlines() if ln.startswith("C")])
    _ok = sum(1 for ln in body.splitlines() if ln.startswith("C") and "不可读" not in ln)
    _tot = sum(1 for ln in body.splitlines() if ln.startswith("C"))
    # 读法：直接用证据行里算出的数字（_rd_data）
    _rd = sector_readings(sector, _rd_data)
    if _rd:
        body += "\n\n**读法（资金视角）**\n\n" + "\n".join(f"- {k}：{v}" for k, v in sorted(_rd.items())) + "\n"

    _ev = sector_events_section(as_of, sector)
    if _ev:
        body += "\n" + "\n".join(_ev)
    body += f"\n\n链条完整性：{_cl}"
    body += f"\n本次 {_tot} 条证据，{_ok} 条有值，{len(_broken)} 处断点" + (
        f"：{'、'.join(_broken)}；断点处请勿跨环推断。" if _broken else "；六环齐全。")
    return as_of, body, sector

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", choices=["traceable", "strict", "demo"], default="traceable")
    ap.add_argument("--layer", choices=["market", "sector"], default="market")
    ap.add_argument("--sector", default="", help="板块名（板块层用）：半导体 / 医药 / 电力 / 基础化工")
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
        as_of, body, sector = build_sector(args.policy, args.sector or None)
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
    _b = [i for i in missing if tier_of(i) == "B"]
    _bnames = "、".join(id_label(i).split("（")[0] for i in _b) or "无"
    _policy_txt = {"strict": "只允许 B 类进入状态行",
                   "traceable": "B 类优先；没有 B 时才用 C 类，并逐行标出取数来源",
                   "demo": "演示模式：C 类也可用，逐行标注"}[args.policy]
    meta = (f"\n元信息：\n- 本次引用 {len(missing)} 条事实记录，压成 {n_ev} 条证据行\n"
            f"- 分级策略：{_policy_txt}\n"
            f"- 已与官方对账（B 类）：{_bnames}\n"
            f"- 时效：数据期落后超过 3 倍频率的指标不落盘，直接标不可读\n")
    lines = ["", "数据溯源（逐项核对；官方直连才可能升 B）：",
             "| 指标 | 官方源 | 请求域名 | 直连官方 | 档位 |", "|---|---|---|---|---|"]
    for iid in missing:
        pr = PROV.get(iid) or {}
        hosts = ",".join(pr.get("hosts") or []) or "—"
        lines.append(f"| {iid} | {pr.get('official_source') or '—'} | {hosts} | "
                     f"{'是' if pr.get('direct_official') else '否'} | {tier_of(iid)} |")
    out = text + meta + "\n".join(lines) + "\n"

    if args.json:
        _ok = sum(1 for ln in body.splitlines() if ln.startswith("C") and "不可读" not in ln)
        _tot = sum(1 for ln in body.splitlines() if ln.startswith("C"))
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
                   "chain_coverage": {"ok": _ok, "total": _tot, "text": f"{_ok}/{_tot}"},
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
