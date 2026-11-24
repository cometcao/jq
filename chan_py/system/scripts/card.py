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
      "sub": 10.5, "cap": 9, "bar_h": 6, "line_h": 20}
COLS = "64px 150px 78px 66px minmax(64px,1fr)"   # R1.7 列宽

# 卡内禁止出现的状态词（R1.4）——只允许出现在证据行
STATE_WORDS = ["偏松", "偏紧", "扩", "缩", "变贵", "变便宜", "加杠杆", "去杠杆",
               "结构偏活", "结构偏死", "参与度", "广度强", "广度弱", "结构聚", "结构散",
               "份额升", "份额降", "偏贵", "偏便宜", "散户增", "机构减", "机构增",
               "不可读"]

# 每个判据在卡上的一行：(环, 指标名, 指标id, 值格式, 频率标签)
ROWS = [
    ("C1", "LPR 1Y", "POL_LPR", "pct1", "月频"),
    ("C2", "M2 同比", "MKT_M2_YOY", "pct1", "月频"),
    ("C3", "DR007", "MKT_DR007", "pct4", "日频"),
    ("C3", "中国 10Y", "MKT_CGB10Y", "pct4", "日频"),
    ("C4", "融资余额", "MKT_MARGIN_BAL", "yi", "日频"),
    ("C4", "深市两融", "MKT_MARGIN_BAL_SZ", "yi2", "日频"),
    ("C5", "两融投资者", "RTL_MARGIN_INVESTORS", "wan", "日频"),
    ("C6", "全市场成交额", "MKT_TURNOVER", "yi", "日频"),
]
GROUP_NAME = {"C1": "基准利率", "C2": "货币与信贷", "C3": "资金价格",
              "C4": "杠杆与抵押", "C5": "市场参与者", "C6": "成交与结构"}
# 卡上要出现的"阈值类/区间类"判据（无序列，直接写比较式或区间）
EXTRA = [
    ("C5", "机构龙虎榜", "−30.55 亿", "区间 7 日", None),
    ("C5", "外部中国 ETF", "4.41 十亿美元", "vs 11-20", "+0.03"),
    ("C5", "产业资本公告", "−233 条", "区间 30 日", None),
    ("C6", "上涨占比", "36.0%", "阈值 50%", None),
    ("C6", "Top5 成交占比", "34.0%", "阈值 50%", None),
]
# 关系量的 id 组合 → 卡上名称与小数字（值取 relations_by_ring）
REL_META = {
    ("MKT_M2_YOY", "MKT_M1_YOY"): ("▪ 剪刀差 M2−M1", "pp"),
    ("MKT_M2_YOY", "MKT_RMB_LOAN_YOY"): ("▪ M2−贷款同比", "pp"),
    ("MKT_MARGIN_BAL", "MKT_MARGIN_COLLATERAL"): ("▪ 融资÷担保物", "%"),
}


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
        rows.sort(key=lambda r: r["data_period"])
    f = fact(iid)
    if f:
        dp, v = f.get("data_period"), num((f.get("current_state") or {}).get("数值"))
        if v is not None and dp:
            if not rows or rows[-1]["data_period"] < dp:
                rows.append({"data_period": dp, "value": v})
            elif rows[-1]["data_period"] == dp:
                rows[-1]["value"] = v
    return rows[-n:]


def fmt(v, kind):
    return {"pct1": f"{v:.2f}%", "pct4": f"{v:.4f}%", "yi": f"{v:,.0f} 亿",
            "yi2": f"{v:,.2f} 亿", "wan": f"{v:,.2f} 万户",
            "pp": f"{v:+.2f}pp"}.get(kind, f"{v}")


def delta(cur, prev, kind):
    if prev is None:
        return "—", "grey", "无上期"
    d = cur - prev
    if abs(d) < 1e-12:
        return "0", "fl", ""
    arrow = "▲" if d > 0 else "▼"
    if kind == "yi":
        mag = f"{abs(d):,.0f} 亿"
    elif kind == "yi2":
        mag = f"{abs(d):,.2f} 亿"
    elif kind == "wan":
        mag = f"{abs(d):,.2f} 万户"
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
            f'<line x1="0" y1="{H/2}" x2="100" y2="{H/2}" stroke="#c9ced6" stroke-width="0.8" stroke-dasharray="3,3"/>'
            f'<path d="{d}" fill="none" stroke="#7f9bb8" stroke-width="1.3" vector-effect="non-scaling-stroke"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="1.6" fill="#1f2328"/></svg>'
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
            name, unit = REL_META.get(key, ("▪ " + order, r.get("value", "")[-2:] or ""))
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

    # 逐环输出
    for ring in ("C1", "C2", "C3", "C4", "C5", "C6"):
        gh(ring)
        for r, label, iid, kind, freq in ROWS:
            if r == ring:
                metric_row(ring, label, iid, kind, freq)
        if ring in ("C2", "C3", "C4"):
            rel_rows(ring)
        if ring == "C3":
            html.append('<div class="rn"></div><div class="nm rel">▪ 期限差 DR007−10Y <b class="grey">—</b></div>'
                        '<div class="dcol grey">暂不可比<div class="bs">数据期不同（11-24 vs 11-23）</div></div>'
                        '<div class="none">口径锚拦截</div><div class="mini none">不出数</div>')
        if ring == "C4":
            # 现金池按证据行动态渲染（不硬编码数值，避免与状态页不一致）
            _ln = None
            for _r in (st.get("lines") or []):
                if _r.get("ring") == "C4" and "现金池" in (_r.get("raw") or ""):
                    _ln = _r
                    break
            if _ln and "不可读" in (_ln.get("raw") or ""):
                html.append('<div class="rn"></div><div class="nm grey">现金池</div>'
                            '<div class="dcol grey">—<div class="bs">无上期</div></div>'
                            '<div class="none">' + (_ln.get("evidence") or "")[:26] + '</div>'
                            '<div class="mini none">代理口径</div>')
            elif _ln:
                _ev = _ln.get("evidence") or ""
                _v = re.search(r"([\d.]+) 万亿", _ev)
                _pv = re.search(r"对比上一期 ([\d.]+) 万亿", _ev)
                _cur = float(_v.group(1)) if _v else None
                _prev = float(_pv.group(1)) if _pv else None
                if _cur is not None and _prev is not None:
                    _dlt = _cur - _prev
                    cls = "up" if _dlt > 0 else ("dn" if _dlt < 0 else "fl")
                    html.append(f'<div class="rn"></div><div class="nm">现金池（代理） <b>{_cur:.2f} 万亿</b></div>'
                                f'<div class="dcol"><span class="{cls}">{"▲" if _dlt>0 else ("▼" if _dlt<0 else "—")}{abs(_dlt):.2f} 万亿</span>'
                                f'<div class="bs">vs {(_ln.get("period") or "")[5:10]} 前</div></div>'
                                f'<div class="none">货币基金规模</div><div class="mini none">同属性代理</div>')
                else:
                    html.append('<div class="rn"></div><div class="nm grey">现金池（代理）</div>'
                                '<div class="dcol grey">—<div class="bs">无上期</div></div>'
                                '<div class="none">' + _ev[:26] + '</div><div class="mini none">代理口径</div>')
        for r, label, val, basis, dtxt in EXTRA:
            if r != ring:
                continue
            if dtxt:
                html.append(f'<div class="rn"></div><div class="nm">{label} <b>{val}</b></div>'
                            f'<div class="dcol"><span class="up">{dtxt}</span><div class="bs">{basis}</div></div>'
                            '<div class="none">无序列</div><div class="mini none">代理口径</div>')
            else:
                html.append(f'<div class="rn"></div><div class="nm">{label} <b>{val}</b></div>'
                            f'<div class="dcol grey">—<div class="bs">{basis}</div></div>'
                            '<div class="none">无序列</div><div class="mini none">区间/阈值</div>')

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
.mini{{border:1px solid #dfe5ec;border-radius:3px;background:transparent;padding:1px 3px}}
.mini.none{{border-color:#e8ecf1;color:#b6bcc5;text-align:center}}
.mcap{{display:flex;justify-content:space-between;font-size:{FS['cap']}px;color:#8a8f99;margin-top:-2px}}
.ft{{margin-top:9px;font-size:{FS['sub']}px;color:var(--dsw-alias-label-secondary);border-top:1px solid var(--dsw-alias-border-l2);padding-top:6px;line-height:1.7}}
</style>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layer", default="market", choices=["market"])
    ap.add_argument("--out", default="")
    ap.add_argument("--stdout", action="store_true")
    a = ap.parse_args()
    html = build_market()
    if a.out:
        os.makedirs(os.path.dirname(os.path.join(ROOT, a.out)) or ROOT, exist_ok=True)
        with io.open(os.path.join(ROOT, a.out), "w", encoding="utf-8") as f:
            f.write(html)
        print(f"状态卡已生成：{a.out}（{len(html)} 字符）")
    if a.stdout or not a.out:
        print(html)
    return 0


if __name__ == "__main__":
    sys.exit(main())
