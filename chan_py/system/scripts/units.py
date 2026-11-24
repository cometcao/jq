#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单位归一：facts 存"展示值"（人读），同时存"基础值"（机器算）。

背景（2026-11-24 教训）：融资余额存「亿元」、担保物存「万亿」，两者一比，
正确结果 33.63%，但任何下游拿展示值直接复算会得到 336251.65% —— 差了 1 万倍。
`compare.py` 内部有换算所以显示对，**但 facts 层没归一**，下游全靠各自记得换算。

本模块定义：每个指标的展示单位 → 基础单位（该维度唯一口径）的换算。
    DIM_CNY   金额（中国）→ 基础单位 亿元
    DIM_USD   金额（美国）→ 基础单位 十亿美元
    DIM_CNT   户数/条数 → 原样
    DIM_PCT   百分比 → 原样
    DIM_IDX   指数点/比值 → 原样

facts 记录新增字段：
    base_value  数值换算到基础单位后的值
    base_unit   基础单位名（亿元 / 十亿美元 / 万户 / % / 条 / —）
    unit_scale  展示值 × unit_scale = base_value

用法（Python）：
    from units import to_base
    base, base_unit, scale = to_base(100.0, "万亿")   # → (1000000.0, "亿元", 10000)
"""
import re

# 展示单位 → (维度, 换算到该维度基础单位的倍数)
UNIT_RULES = {
    # ---- 人民币金额（基础：亿元）
    "亿元": ("cny", 1),
    "亿": ("cny", 1),
    "万元": ("cny", 1 / 1e4),
    "万亿元": ("cny", 1e4),
    "万亿": ("cny", 1e4),
    "元": ("cny", 1 / 1e8),
    # ---- 美元金额（基础：十亿美元）
    "十亿美元": ("usd", 1),
    "亿美元": ("usd", 0.1),
    "亿美元(USD)": ("usd", 0.1),
    # ---- 计数（基础：原样）
    "万户": ("cnt", 1),
    "户": ("cnt", 1 / 1e4),
    "条": ("cnt", 1),
    "家": ("cnt", 1),
    "只": ("cnt", 1),
    "个": ("cnt", 1),
    "只个股": ("cnt", 1),
    # ---- 百分比（基础：%）
    "%": ("pct", 1),
    "pp": ("pct", 1),
    "个百分点": ("pct", 1),
    # ---- 指数/比值（原样）
    "点": ("idx", 1),
    "倍": ("idx", 1),
    "×": ("idx", 1),
    "倍（PE）": ("idx", 1),
    "倍PE": ("idx", 1),
    "": ("idx", 1),
}

BASE_NAME = {"cny": "亿元", "usd": "十亿美元", "cnt": "（原单位）",
             "pct": "%", "idx": "（原单位）"}

_UNIT_RE = re.compile(r"(万亿元|万亿|十亿美元|亿美元|亿元|万元|万户|亿|%|pp|个百分点|元|户|条|家|只个股|只|个|点|倍|×)$")


def split_unit(text):
    """把 '3.00 万亿' / '7.10%' / '-233 条' 拆成 (数值, 单位)。"""
    s = str(text or "").strip().replace("−", "-")
    m = re.search(r"[-+]?[\d,]+(?:\.\d+)?", s)
    if not m:
        return None, None
    try:
        val = float(m.group(0).replace(",", ""))
    except Exception:
        return None, None
    tail = s[m.end():].strip()
    tail = tail.split("（")[0].strip()
    return val, tail


def to_base(value, unit):
    """展示值 → (基础值, 基础单位名, 倍数)。未知单位按原样返回并标注。"""
    u = (unit or "").strip()
    rule = UNIT_RULES.get(u)
    if rule is None:
        # 尝试去尾部空白/括号后再查
        u2 = re.sub(r"[\s（）()]", "", u)
        rule = UNIT_RULES.get(u2)
        if rule is None:
            return value, u or "（原单位）", 1
        u = u2
    dim, scale = rule
    return value * scale, BASE_NAME[dim], scale


def norm(display_text):
    """直接从 facts 的「数值」文本一次算出三个字段。"""
    v, u = split_unit(display_text)
    if v is None:
        return None, None, None
    base, base_unit, scale = to_base(v, u)
    return base, base_unit, scale


def main():
    """自检：常见写法的换算是否正确。"""
    cases = [
        ("21,419.23 亿元", 21419.23, "亿元", 1),
        ("6.37 万亿", 63700.0, "亿元", 10000),
        ("15.82 万亿元", 158200.0, "亿元", 10000),
        ("7.10%", 7.10, "%", 1),
        ("848.16 万户", 848.16, "（原单位）", 1),
        ("4.41 十亿美元", 4.41, "十亿美元", 1),
        ("−233 条", -233.0, "（原单位）", 1),
        ("2.70pp", 2.70, "%", 1),
    ]
    bad = 0
    for text, ev, eu, es in cases:
        b, u, s = norm(text)
        ok = b is not None and abs(b - ev) < 1e-6 and u == eu and abs(s - es) < 1e-9
        print(("  ✓ " if ok else "  ✗ ") + f"{text:<16} → {b} {u} (×{s})")
        bad += 0 if ok else 1
    print(f"\n单位归自检：{len(cases) - bad}/{len(cases)} 通过")
    return 0 if not bad else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
