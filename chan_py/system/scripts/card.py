#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""六环状态卡生成器（唯一出口，禁止手写卡片）。

规则来源：
  R1.1 五段布局  R1.3 基准小字  R1.4 不写状态词  R1.5 字号
  R1.6 顶部=链条完整性  R1.7 小图规范  R1.8 关系量并入环  R1.9 单一网格

数据来源（全部读权威文件，不重算）：
  reports/state-market.json   ← relations_by_ring / chain_coverage（七锚输出）
  data/facts/<日期>/<id>.json ← 当期值、数据期、档位
  data/history/<id>.jsonl     ← 位置条与小图（形状）
  data/thresholds.json        ← 阈值

用法：
  python scripts/card.py --layer market --out reports/card-market.html
  python scripts/card.py --layer market --stdout
"""
import io
import os
import re
import sys
import json
import glob
import argparse
import datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

FACTS = os.path.join(ROOT, "data", "facts")
HIST = os.path.join(ROOT, "data", "history")

# ---------------------------------------------------------------- R1.5 字号（唯一常量表）
FS = {"ring": 13, "value": 12.5, "name": 12.5, "delta": 12,
      "sub": 10.5, "cap": 9, "bar_h": 6, "line_h": 18}
COLS = "64px 150px 78px 66px 108px"   # R1.7 列宽（末列=小图列，定宽，避免右侧空档）
MINI_W = int(re.match(r".*?(\d+)px$", COLS).group(1))   # 小图容器宽 = 末列宽

# 卡内禁止出现的状态词（R1.4）——只允许出现在证据行
STATE_WORDS = ["偏松", "偏紧", "扩", "缩", "变贵", "变便宜", "加杠杆", "去杠杆",
               "结构偏活", "结构偏死", "参与度", "广度强", "广度弱", "结构聚", "结构散",
               "份额升", "份额降", "偏贵", "偏便宜", "散户增", "机构减", "机构增",
               "不可读"]

# 每个判据在卡上的一行：(环, 指标名, 指标id, 值格式, 频率标签)
ROWS = []          # 由 reports/state-market.json 的 card_rows 提供（不再硬编码）
GROUP_NAME = {"C1": "基准利率", "C2": "货币与信贷", "C3": "资金价格",
              "C4": "杠杆与抵押", "C5": "市场参与者", "C6": "成交与结构"}
# 卡上要出现的"阈值类/区间类"判据（无序列，直接写比较式或区间）
EXTRA = []         # 同上：阈值/区间类也由 card_rows 提供
# 关系量的 id 组合 → 卡上名称与小数字（值取 relations_by_ring）
REL_META = {
    ("MKT_M2_YOY", "MKT_M1_YOY"): ("▪ 剪刀差 M2−M1", "pp"),
    ("MKT_M2_YOY", "MKT_RMB_LOAN_YOY"): ("▪ M2−贷款同比", "pp"),
    ("MKT_MARGIN_BAL", "MKT_MARGIN_COLLATERAL"): ("▪ 融资÷担保物", "%"),
    ("MKT_DR007", "MKT_CGB10Y"): ("▪ 期限差 DR007−10Y", "pp"),
}
ID_NAME = {"MKT_M2_YOY": "M2 同比", "MKT_M1_YOY": "M1 同比", "MKT_RMB_LOAN_YOY": "人民币贷款余额同比",
           "MKT_MARGIN_BAL": "融资余额", "MKT_MARGIN_COLLATERAL": "两融担保物", "MKT_DR007": "DR007",
           "MKT_CGB10Y": "中国 10Y"}


_SHAPES = {}


def shape_of(iid):
    global _SHAPES
    if not _SHAPES:
        try:
            with io.open(os.path.join(ROOT, "data", "series_shape.json"), encoding="utf-8") as f:
                _SHAPES = (json.load(f) or {}).get("shapes") or {}
        except Exception:
            _SHAPES = {}
    return (_SHAPES.get(iid) or {}).get("visual") or "位置条"


def _unused_shape_of(iid):
    """R9/ADR-041：波形决定画什么图。未登记默认按波动（最保守）。"""
    return (SHAPES.get(iid) or {}).get("visual") or "位置条"


def load(fp, default=None):
    try:
        with io.open(fp, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def fact(iid):
    fs = sorted(glob.glob(os.path.join(FACTS, "*", f"{iid}.json")))
    return load(fs[-1]) if fs else None


def num(t):
    m = re.search(r"-?[\d,]+(?:\.\d+)?", str(t or ""))
    return float(m.group(0).replace(",", "")) if m else None


def series(iid, n=60):
    fp = os.path.join(HIST, f"{iid}.jsonl")
    rows = []
    if os.path.exists(fp):
        rows = [json.loads(x) for x in io.open(fp, encoding="utf-8").read().splitlines() if x.strip()]
        rows = [r for r in rows if r.get("value") is not None]
        # 统一到基础单位：history 行有 base_value 就用它（否则同一序列会出现 15.19 与 158200 混排）
        for r in rows:
            if r.get("base_value") is not None:
                r["value"] = r["base_value"]
        rows.sort(key=lambda r: r["data_period"])
    f = fact(iid)
    if f:
        dp = f.get("data_period")
        # 优先用 facts 里已归一的基础值（units.py 写入）；老记录才退回量级启发式
        v = f.get("base_value")
        if v is None:
            v = num((f.get("current_state") or {}).get("数值"))
            if v is not None and rows:
                _ref = abs(rows[-1]["value"]) or 1e-9
                _r = v / _ref if _ref else 1
                if _r < 0.01:
                    v = v * 1e4
                elif _r > 100:
                    v = v / 1e4
        if v is not None and dp:
            if not rows or rows[-1]["data_period"] < dp:
                rows.append({"data_period": dp, "value": v})
            elif rows[-1]["data_period"] == dp:
                rows[-1]["value"] = v
    return rows[-n:]


def fmt(v, kind):
    if v is None:
        return "—"
    if kind == "pct1":
        return f"{v:.2f}%"
    if kind == "pct4":
        return f"{v:.4f}%"
    if kind == "yi":
        return f"{v:,.0f} 亿" if abs(v) >= 1000 else f"{v:,.2f} 亿"
    if kind == "yi2":
        return f"{v:,.2f} 亿"
    if kind == "wan":
        return f"{v:,.2f} 万户"
    if kind == "trillion":
        return f"{v:.2f} 万亿"
    if kind == "usd":
        return f"{v:.2f} 十亿美元"
    if kind == "cnt":
        return f"{v:+.0f} 条"
    if kind == "pp":
        return f"{v:+.2f}pp"
    return f"{v}"


def delta(cur, prev, kind):
    if prev is None:
        return "—", "grey", "无上期"
    d = cur - prev
    if abs(d) < 1e-12:
        return "0", "fl", ""
    arrow = "▲" if d > 0 else "▼"
    if kind == "yi":
        mag = f"{abs(d):,.0f} 亿" if abs(d) >= 1000 else f"{abs(d):,.2f} 亿"
    elif kind in ("yi2", "wan"):
        mag = f"{abs(d):,.2f} " + ("亿" if kind == "yi2" else "万户")
    elif kind == "trillion":
        mag = f"{abs(d):.2f} 万亿"
    elif kind == "usd":
        mag = f"{abs(d):.2f} 十亿美元"
    elif kind == "cnt":
        mag = f"{abs(d):.0f} 条"
    elif kind == "pct4":
        mag = f"{abs(d)*100:.1f}bp"
    else:
        mag = f"{abs(d):.2f}pp"
    return f"{arrow}{mag}", ("up" if d > 0 else "dn"), ""


def pos_pct(vals):
    if len(vals) < 2:
        return None
    v = vals[-1]
    return sum(1 for x in vals[:-1] if x < v) / (len(vals) - 1) * 100


def spark_svg(vals):
    if len(vals) < 2:
        return None
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    W, H = 100, FS["line_h"]
    pts = [(i / (len(vals) - 1) * W, 2 + (1 - (v - lo) / rng) * (H - 4)) for i, v in enumerate(vals)]
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    return d, pts[-1], lo, hi


def basis_of(iid, period):
    """R1.3：基准 = 该指标自己的上期日期（MM-DD）。"""
    s = series(iid, 60)
    if len(s) < 2:
        return "无上期"
    return f"vs {s[-2]['data_period'][5:10]}"


def cell_pos(pos, n):
    if pos is None:
        return '<div class="none">无序列</div>'
    lbl = "最低" if pos <= 2 else ("最高" if pos >= 98 else f"{pos:.0f}%")
    return (f'<div class="pbar"><span class="pf" style="left:{max(0,min(100,pos)):.0f}%"></span></div>'
            f'<div class="plbl">{n} 期 {lbl}</div>')


def cell_visual(vals, iid):
    """R9：累积→增速条；阶梯→档位；季节→较均值；区间汇总→不画；波动→位置条。"""
    vis = shape_of(iid)
    if vis == "不画":
        return '<div class="none">区间汇总</div>'
    if len(vals) < 2:
        return '<div class="none">无序列</div>'
    cur = vals[-1]
    if vis == "增速":
        # 近 20 期增幅，并给出该增幅在历史上的分位（R9：累积型用增速，位置恒 100% 无信息）
        win = 20
        if len(vals) <= win:
            win = max(1, len(vals) - 1)
        gs = [(vals[i] - vals[i - win]) / vals[i - win] * 100 for i in range(win, len(vals)) if vals[i - win]]
        if not gs:
            return '<div class="none">无序列</div>'
        g = gs[-1]
        pct = sum(1 for x in gs[:-1] if x < g) / max(len(gs) - 1, 1) * 100
        cls = "up" if g > 0 else ("dn" if g < 0 else "fl")
        return (f'<div class="pbar"><span class="pf" style="left:{pct:.0f}%"></span></div>'
                f'<div class="plbl"><span class="{cls}">{g:+.2f}%</span>（{win} 期 · {pct:.0f}% 位）</div>')
    if vis == "档位":
        uniq = sorted(set(vals))
        rank = uniq.index(cur) + 1
        lbl = "最低档" if rank == 1 else ("最高档" if rank == len(uniq) else f"第 {rank}/{len(uniq)} 档")
        return f'<div class="plbl">{lbl}</div>'
    if vis == "较均值":
        n = min(20, len(vals))
        ma = sum(vals[-n:]) / n
        d = (cur - ma) / ma * 100 if ma else None
        if d is None:
            return '<div class="none">无序列</div>'
        cls = "up" if d > 0 else ("dn" if d < 0 else "fl")
        return (f'<div class="pbar"><span class="pf" style="left:{min(abs(d)/60*100,100):.0f}%"></span></div>'
                f'<div class="plbl"><span class="{cls}">{d:+.1f}%</span> 较 {n} 日均值</div>')
    # 波动 → 位置条
    return cell_pos(pos_pct(vals), len(vals))


def cell_spark(vals, freq):
    sp = spark_svg(vals)
    if not sp:
        return '<div class="mini none">无序列</div>'
    d, (lx, ly), lo, hi = sp
    H = FS["line_h"]
    return (f'<div class="mini"><svg viewBox="0 0 100 {H}" preserveAspectRatio="none" width="100%" height="{H}">'
            f'<line x1="0" y1="{H/2}" x2="100" y2="{H/2}" stroke="#d5dae1" stroke-width="0.7" stroke-dasharray="2,3"/>'
            f'<path d="{d}" fill="none" stroke="#8497ab" stroke-width="1.1" vector-effect="non-scaling-stroke"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="1.4" fill="#1f2328"/></svg>'
            f'<div class="mcap"><span>{lo:.2f}–{hi:.2f}</span><span>{freq} {len(vals)}期</span></div></div>')


def build_market():
    st = load(os.path.join(ROOT, "reports", "state-market.json")) or {}
    rel_by_ring = st.get("relations_by_ring") or {}
    cov = st.get("chain_coverage") or {}

    # ---- 顶部条（R1.6）：按**证据行**统计每环 有值/总数（与 R1.6 示例口径一致）
    per_ring = {}
    for rec in (st.get("lines") or []):
        ring = rec.get("ring")
        if ring not in GROUP_NAME:
            continue
        per_ring.setdefault(ring, [0, 0])
        per_ring[ring][1] += 1
        if "不可读" not in (rec.get("raw") or rec.get("state") or ""):
            per_ring[ring][0] += 1
    for ring in GROUP_NAME:
        per_ring.setdefault(ring, [0, 0])

    html = [css(), '<div class="mk"><div class="top">']
    total_ok = total_n = 0
    broken = []
    for ring in ("C1", "C2", "C3", "C4", "C5", "C6"):
        ok, n = per_ring.get(ring, [0, 0])
        total_ok += ok
        total_n += n
        if ok < n:
            broken.append(ring)
        lite = " lite" if ok < n else ""
        html.append(f'<div><div class="cv"><b>{ring}</b> {ok}/{n}</div>'
                    f'<div class="tbar"><div class="tfill{lite}" style="width:{(ok/n*100 if n else 0):.0f}%"></div></div></div>')
    html.append("</div>")
    btxt = "、".join(broken) if broken else "无"
    html.append(f'<div class="sum">共 <b>{total_ok}/{total_n}</b> 条有值 · 断点：{btxt}'
                f' · 断点处不可跨环推断</div><div class="g">')

    def gh(ring):
        ok, n = per_ring.get(ring, [0, 0])
        html.append(f'<div class="gh"><b>{ring}</b>{GROUP_NAME[ring]}'
                    f'<span style="float:right">{ok}/{n}</span></div>')

    def metric_row(ring, label, iid, kind, freq):
        s = series(iid, 60)
        if not s:
            html.append(f'<div class="rn">{ring}</div><div class="nm">{label}</div>'
                        '<div class="dcol grey">—<div class="bs">无上期</div></div>'
                        '<div class="none">无序列</div><div class="mini none">无序列</div>')
            return
        vals = [x["value"] for x in s]
        cur, prev = vals[-1], (vals[-2] if len(vals) > 1 else None)
        dtxt, dcls, _ = delta(cur, prev, kind)
        html.append(
            f'<div class="rn">{ring}</div><div class="nm">{label} <b>{fmt(cur, kind)}</b></div>'
            f'<div class="dcol"><span class="{dcls}">{dtxt}</span><div class="bs">{basis_of(iid, s[-1]["data_period"])}</div></div>'
            f'<div class="pos">{cell_visual(vals, iid)}</div>{cell_spark(vals, freq)}')

    def rel_rows(ring):
        for r in rel_by_ring.get(ring, []):
            order = r.get("operand_order") or ""
            parts = re.split(r"[÷−]", order)
            key = (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else None
            if key and key in REL_META:
                name, unit = REL_META[key]
            elif key:
                name = "▪ " + " ÷ ".join(ID_NAME.get(x, x) for x in key)
                unit = "%" if "÷" in order else "pp"
            else:
                name, unit = "▪ 关系量", "pp"
            periods = [x["data_period"] for x in series(parts[0].strip(), 60)] if key else []
            if key and unit == "pp":
                A = dict((x["data_period"], x["value"]) for x in series(parts[0].strip(), 60))
                B = dict((x["data_period"], x["value"]) for x in series(parts[1].strip(), 60))
                s = [(d, A[d] - B[d]) for d in sorted(set(A) & set(B))]
            elif key:
                A = dict((x["data_period"], x["value"]) for x in series(parts[0].strip(), 60))
                B = dict((x["data_period"], x["value"]) for x in series(parts[1].strip(), 60))
                s = [(d, A[d] / B[d] * 100) for d in sorted(set(A) & set(B))]
            else:
                s = []
            vals = [v for _, v in s]
            auth = r.get("value") or "—"
            if len(vals) >= 2:
                d = vals[-1] - vals[-2]
                arrow = "▲" if d > 0 else ("▼" if d < 0 else "—")
                dcls = "up" if d > 0 else ("dn" if d < 0 else "fl")
                dtxt = f'{arrow}{abs(d):.2f}{unit}'
                basis = f"vs {s[-2][0][5:10]}"
                posc = cell_pos(pos_pct(vals), len(vals))
                spk = cell_spark(vals, "月频" if len(vals) <= 24 else "日频")
            else:
                dtxt, dcls, basis, posc, spk = "—", "grey", "无序列", '<div class="none">无序列</div>', '<div class="mini none">无序列</div>'
            html.append(f'<div class="rn"></div><div class="nm rel">{name} <b>{auth}</b></div>'
                        f'<div class="dcol"><span class="{dcls}">{dtxt}</span><div class="bs">{basis}</div></div>'
                        f'<div class="pos">{posc}</div>{spk}')

    # 逐环输出：完全由 state 的 card_rows 驱动（不再硬编码任何数值/名称）
    rows = st.get("card_rows") or []
    by_ring = {}
    for r in rows:
        by_ring.setdefault(r["ring"], []).append(r)

    def render_metric(ring, r):
        iid, kind, freq = r.get("indicator_id"), r.get("value_kind"), r.get("freq", "日频")
        label = r["label"]
        if not r.get("has_series"):
            # 无序列（区间汇总/阈值类）：只给现值与基准，不画位置条
            _b = ("阈值 50%" if ("占比" in label) else (r.get("freq") or "无上期"))
            html.append(f'<div class="rn">{ring}</div><div class="nm">{label} <b>{fmt(r["value"], kind)}</b></div>'
                        f'<div class="dcol grey">—<div class="bs">{_b}</div></div>'
                        '<div class="none">无序列</div><div class="mini none">区间/阈值</div>')
            return
        ser = [x["value"] for x in series(iid, 60)]
        cur = r["value"]
        prev = r.get("prev")
        dtxt, dcls, _ = delta(cur, prev, kind)
        basis = f"vs {r['prev_period'][5:10]}" if r.get("prev_period") else "无上期"
        html.append(
            f'<div class="rn">{ring}</div><div class="nm">{label} <b>{fmt(cur, kind)}</b></div>'
            f'<div class="dcol"><span class="{dcls}">{dtxt}</span><div class="bs">{basis}</div></div>'
            f'<div class="pos">{cell_visual(ser, iid)}</div>{cell_spark(ser, freq)}')

    for ring in ("C1", "C2", "C3", "C4", "C5", "C6"):
        gh(ring)
        for r in by_ring.get(ring, []):
            if r.get("kind") == "unreadable":
                html.append(f'<div class="rn">{ring}</div><div class="nm grey">{r["label"]}</div>'
                            '<div class="dcol grey">—<div class="bs">无上期</div></div>'
                            '<div class="none">不可读</div><div class="mini none">无源/无前值</div>')
            else:
                render_metric(ring if r is by_ring[ring][0] else "", r)
        if ring in ("C2", "C3", "C4"):
            rel_rows(ring)

    html.append("</div>")
    html.append('<div class="ft">关系量取七锚输出（reports/state-market.json · relations_by_ring）：现值按七锚口径；'
                '位置条与小图取精确序列 · 各指标上期日期不同，<b>不可横向比较新旧</b> · 灰底块 = 关系量，不计入覆盖率分母</div></div>')
    return "".join(html)


def css():
    return f"""<style>
.mk{{font:{FS['name']}px/1.4 system-ui,-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;color:var(--dsw-alias-label-primary)}}
.top{{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin:0 0 4px}}
.cv{{font-size:{FS['sub']}px;color:var(--dsw-alias-label-secondary)}}.cv b{{color:var(--dsw-alias-label-primary);font-size:11px}}
.tbar{{height:{FS['bar_h']}px;border-radius:3px;background:var(--dsw-alias-border-l2);overflow:hidden;margin-top:2px}}
.tfill{{height:{FS['bar_h']}px;background:#5b6672;border-radius:3px}}.tfill.lite{{background:#aab3bd}}
.sum{{font-size:{FS['sub']}px;color:var(--dsw-alias-label-secondary);margin-bottom:6px}}
.g{{display:grid;grid-template-columns:{COLS};column-gap:12px;row-gap:4px;align-items:start}}
.gh{{grid-column:1/-1;font-size:{FS['sub']}px;color:var(--dsw-alias-label-secondary);border-bottom:1px solid var(--dsw-alias-border-l2);padding:7px 0 2px;margin-top:4px}}
.gh b{{font-size:{FS['ring']}px;color:var(--dsw-alias-label-primary);font-weight:600;margin-right:5px}}
.rn{{font-size:{FS['ring']}px;font-weight:600}}.nm{{font-size:{FS['name']}px}}.nm b{{font-family:ui-monospace,Consolas,monospace}}
.nm.rel{{color:#5b6672}}.nm.rel b{{color:#3d4550}}
.dcol{{font-size:{FS['delta']}px;font-family:ui-monospace,Consolas,monospace}}
.bs{{font-size:{FS['sub']}px;color:var(--dsw-alias-label-secondary);font-family:system-ui,sans-serif}}
.up{{color:#d03050}}.dn{{color:#2477b3}}.fl{{color:var(--dsw-alias-label-secondary)}}.grey{{color:#a8aeb6}}
.pos{{font-size:{FS['sub']}px}}
.pbar{{position:relative;height:{FS['bar_h']}px;border-radius:3px;background:linear-gradient(90deg,#e8ecf1,#d5dce4)}}
.pf{{position:absolute;top:-2px;width:2.5px;height:{FS['bar_h']+4}px;border-radius:1.2px;background:#2477b3;transform:translateX(-1.2px)}}
.plbl{{font-size:{FS['sub']}px;color:var(--dsw-alias-label-secondary);margin-top:1px;white-space:nowrap}}
.none{{font-size:{FS['sub']}px;color:#b6bcc5}}
.mini{{border:1px solid rgba(31,35,40,.07);border-radius:3px;background:transparent;padding:1px 3px;width:{MINI_W}px;box-sizing:border-box}}
.mini.none{{border-color:rgba(31,35,40,.05);color:#b6bcc5;text-align:center}}
.mcap{{display:flex;justify-content:space-between;font-size:{FS['cap']}px;color:#8a8f99;margin-top:-2px}}
.ft{{margin-top:9px;font-size:{FS['sub']}px;color:var(--dsw-alias-label-secondary);border-top:1px solid var(--dsw-alias-border-l2);padding-top:6px;line-height:1.7}}
</style>"""


# ---------------------------------------------------------------- 事件日历卡（脚本生成，禁止手写）
def _short_label(e):
    """格子里的短标签（按事件类型）。"""
    t = e.get("scope") or ""
    cat = e.get("category") or ""
    ev = e.get("event_type") or ""
    if "限售解禁" in t:
        m = re.search(r"限售解禁：([\d]+) 家(?:，解禁市值 ([\d.]+) 亿)?", t)
        if m:
            return f"解禁 {m.group(1)} 家" + (f" {float(m.group(2)):.0f}亿" if m.group(2) else "")
    if "逆回购到期" in t:
        m = re.search(r"([\d,]+) 亿元", t)
        return (f"到期 {m.group(1)} 亿" if m else "逆回购到期")[:16]
    if "新股申购" in t:
        m = re.search(r"新股申购：([^（(]+)", t)
        return ("新股 " + (m.group(1).strip() if m else ""))[:14]
    if ev == "数据发布":
        tm = e.get("event_time") or ""
        nm = re.sub(r"月度报告|报告$", "", t)[:8]
        return (f"{tm[:5]} {nm}").strip()
    return t[:12]


def _tip_html(e, scen):
    """悬停窗：标题 + 发行人 + 状态 + （数据发布）受影响指标与分支。"""
    out = [f'<div class="tip"><b>{e.get("event_date")} {e.get("event_time") or ""} {e.get("scope","")}</b>',
           f'<span class="u">{e.get("issuer","")} · {e.get("event_status","")}</span>']
    if scen:
        reg = load(os.path.join(ROOT, "dist", "market-state", "references", "registry.json")) or {}
        ids_list = []
        for o in (scen.get("possible_outcomes") or []):
            for i in (o.get("affected_indicators") or []):
                nm = (reg.get(i) or {}).get("name") or i
                ch = {"C1": "C1", "C2": "C2", "C3": "C3", "C4": "C4", "C5": "C5", "C6": "C6"}.get((reg.get(i) or {}).get("channel"), "")
                lab = f"{nm}（{ch}）" if ch else nm
                if lab not in ids_list:
                    ids_list.append(lab)
        ids = "、".join(ids_list) or "（未登记受影响指标）"
        out.append(f'<span class="u">受影响：{ids}</span>')
        for o in scen.get("possible_outcomes") or []:
            note = o.get("impact_note") or o.get("observable_flag") or ""
            lab = o.get("observable_flag") or o.get("outcome_label") or ""
            # 卡片只放要点（完整分支在状态页"事件段"与 data/events/*.json）
            note = note.replace("按登记的传导规则，", "").replace("（收益率上行 = 债券价格下行；不预测实际落点）", "")
            note = (note[:52] + "…") if len(note) > 52 else note
            out.append(f'<div class="o"><em>{lab}</em>{note}</div>')
    else:
        out.append(f'<div class="o">{e.get("scope","")}</div>')
    out.append("</div>")
    return "".join(out)


def build_events():
    """事件日历卡：未来窗口按月网格；**每一个** event chip 都带悬停窗（不留裸 chip）。"""
    import calendar as _cal
    cals = sorted(glob.glob(os.path.join(ROOT, "data", "events", "calendar-*.json")))
    cal = load(cals[-1]) if cals else {}
    evs = cal.get("events") or []
    if not evs:
        return '<div class="mk">无事件数据</div>'
    as_of = cal.get("as_of") or ""
    # 分支模板（按日期 + 标题前 8 字匹配）
    # 分支模板按**事件日期**索引（event_summary 前 10 位是 YYYY-MM-DD），
    # 不能用 observation_time（那是生成时间，与事件日期不同）
    scen = {}
    for fp in glob.glob(os.path.join(ROOT, "data", "events", "scenario-*.json")):
        r = load(fp) or {}
        summary = r.get("event_summary") or ""
        m = re.match(r"(\d{4}-\d{2}-\d{2})", summary)
        if m:
            scen.setdefault(m.group(1), []).append(r)
    rows = [e for e in evs if e.get("event_status") == "未来预定"]
    rows.sort(key=lambda e: (e.get("event_date"), e.get("event_time") or ""))
    if not rows:
        return '<div class="mk">窗口内无未来事件</div>'
    months = sorted({e["event_date"][:7] for e in rows})
    by_day = {}
    for e in rows:
        by_day.setdefault(e["event_date"], []).append(e)
    html = [EVENT_CSS, '<div class="ec">']
    for ym in months[:2]:
        y, m = int(ym[:4]), int(ym[5:7])
        html.append(f'<table><caption>{y} 年 {m} 月</caption>'
                    '<tr><th>一</th><th>二</th><th>三</th><th>四</th><th>五</th><th>六</th><th>日</th></tr>')
        first_wd = dt.date(y, m, 1).weekday()
        ndays = _cal.monthrange(y, m)[1]
        cells = [None] * first_wd + [dt.date(y, m, d).isoformat() for d in range(1, ndays + 1)]
        while len(cells) % 7:
            cells.append(None)
        for i in range(0, len(cells), 7):
            html.append("<tr>")
            for c in cells[i:i + 7]:
                if not c:
                    html.append("<td class='e'></td>")
                    continue
                cls = "td today" if c == as_of else "td"
                day = int(c[-2:])
                cell = [f"<td class='{cls}'><s>{day}</s>"]
                for e in by_day.get(c, []):
                    # 分支只挂给「数据发布」且标题完整命中的事件；
                    # 解禁/新股/央行操作没有三分支，硬套会张冠李戴（2026-11-24 教训）
                    sc = None
                    if e.get("event_type") == "数据发布":
                        _sc0 = (e.get("scope") or "").strip()
                        for r in scen.get(c, []):
                            if _sc0 and _sc0 in (r.get("event_summary") or ""):
                                sc = r
                                break
                    cell.append(f"<div class='ev'><span class='chip'>{_short_label(e)}</span>{_tip_html(e, sc)}</div>")
                cell.append("</td>")
                html.append("".join(cell))
            html.append("</tr>")
        html.append("</table>")
    html.append("</div>")
    return "".join(html)


EVENT_CSS = """<style>
.ec{font:12.5px/1.4 system-ui,'Segoe UI',sans-serif;display:flex;gap:14px;color:var(--dsw-alias-label-primary);padding:10px 8px;position:relative}
.ec table{border-collapse:collapse;flex:1}
.ec caption{text-align:left;font-weight:600;font-size:13px;padding:2px 0 6px}
.ec th{font-size:10.5px;color:var(--dsw-alias-label-secondary);font-weight:400;padding:2px;text-align:center}
.ec td.td{border:1px solid var(--dsw-alias-border-l2);height:58px;width:14.2%;vertical-align:top;padding:2px 3px}
.ec td.e{border:none}
.ec td.today{outline:2px solid #d03050;outline-offset:-2px}
.ec s{font-size:10.5px;color:var(--dsw-alias-label-secondary);text-decoration:none;display:block}
.ec .ev{position:relative;margin-top:2px}
.ec .chip{display:block;font-size:9.5px;background:var(--dsw-alias-border-l2);border-radius:3px;padding:1px 4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ec .ev:hover .chip{background:#d8e3ee}
.ec .tip{display:none;position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);z-index:90;width:470px;max-width:86vw;max-height:74vh;overflow:auto;background:#fff;color:#1f2328;border:1px solid #b9c0ca;border-radius:8px;padding:13px 15px;font:11.5px/1.8 system-ui,'Segoe UI',sans-serif;box-shadow:0 12px 36px rgba(0,0,0,.25);white-space:normal;text-align:left}
.ec .ev:hover .tip{display:block}
.ec .tip b{font-size:12px;display:block;margin:0 0 6px}
.ec .tip .u{color:#6b7280;display:block;margin-bottom:6px}
.ec .tip .o{margin:7px 0;padding-left:9px;border-left:3px solid #2477b3}
.ec .tip .o em{font-style:normal;font-weight:600;display:block;color:#2477b3;margin-bottom:1px}
</style>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layer", default="market", choices=["market", "events"])
    ap.add_argument("--out", default="")
    ap.add_argument("--stdout", action="store_true")
    a = ap.parse_args()
    html = build_events() if a.layer == "events" else build_market()
    if a.out:
        os.makedirs(os.path.dirname(os.path.join(ROOT, a.out)) or ROOT, exist_ok=True)
        with io.open(os.path.join(ROOT, a.out), "w", encoding="utf-8") as f:
            f.write(html)
        print(f"{'事件卡' if a.layer == 'events' else '状态卡'}已生成：{a.out}（{len(html)} 字符）")
    if a.stdout or not a.out:
        print(html)
    return 0


if __name__ == "__main__":
    sys.exit(main())
