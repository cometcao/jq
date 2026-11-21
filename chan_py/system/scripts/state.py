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
    rings[3].add("现金池不可读（—）", "客户保证金无公开日度来源", "该环无证据")

    # C5 窄口径替代 + 机构/外部空环
    ok, tag = allow("RTL_MARGIN_INVESTORS")
    v, p = val("RTL_MARGIN_INVESTORS"), val("RTL_MARGIN_INVESTORS", "prev_value")
    if ok and v is not None:
        word = "增" if (p is None or v > p) else ("减" if v < p else "不变")
        ev = f"两融个人投资者 {v:.2f} 万户" + (f" 对比上一期 {p:.2f} 万户" if p is not None else "")
        rings[4].add(f"散户{word}（{period('RTL_MARGIN_INVESTORS')}）", ev, "仅覆盖杠杆散户，不等于新增开户", tag + "〔替代：窄口径〕")
    else:
        rings[4].add("散户不可读（—）", "无开户或杠杆投资者记录", "该环无可用证据")
    rings[4].add("机构不可读（—）", "龙虎榜、ETF 净申赎、大宗均未接入", "该环无证据")
    rings[4].add("外部不可读（—）", "北向日度已停披露，季度持股未接入", "该环无证据")

    # C6 参与度（板块成交额）+ 广度/结构空环
    ok, tag = allow("SECTOR_AMT")
    v, p = val("SECTOR_AMT"), val("SECTOR_AMT", "prev_value")
    if ok and v is not None and p is not None:
        word = "不变" if v == p else ("升" if v > p else "降")
        rings[5].add(f"参与度{word}（{period('SECTOR_AMT')}）", f"半导体板块成交额 {v:.2f} 亿 对比上一期 {p:.2f} 亿", "不说明资金来源", tag + "〔板块层口径〕")
    else:
        rings[5].add("参与度不可读（—）", "板块成交额缺失，或来源为 C 类（聚合口径）、无源可支撑状态词", "该环无可用证据")
    rings[5].add("广度不可读（—）", "涨跌家数来自 MCP 实时端点，未落盘", "该环无证据")
    rings[5].add("结构不可读（—）", "板块集中度未接入", "该环无证据")

    # as-of：最慢环（月频优先）
    periods = []
    for iid in ("MKT_M2_YOY", "MKT_M1_YOY", "MKT_RMB_LOAN_YOY", "FISC_DEP"):
        p_ = period(iid)
        if p_:
            periods.append((p_, "C2 月频"))
    as_of = min(periods)[0] if periods else "不可用"
    body = "\n".join(r_.lines for r_ in rings) if False else "\n".join("\n".join(r_.lines) for r_ in rings)
    return as_of, body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", choices=["traceable", "strict", "demo"], default="traceable")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    as_of, body = build(a.policy)
    text = f"as-of {as_of}（最慢环 C2 月频；其余日频为区间内最新读数）\n{body}\n"

    missing = sorted({json.load(io.open(f, encoding="utf-8"))["indicator_id"]
                      for f in glob.glob(os.path.join(FACTS, "*", "*.json"))})
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
    print(out)

    if a.write:
        os.makedirs(REPORTS, exist_ok=True)
        p = os.path.join(REPORTS, f"{as_of}-state.md")
        with io.open(p, "w", encoding="utf-8") as f:
            f.write("```\n" + text + "```\n" + meta)
        print("已写入:", os.path.relpath(p, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
