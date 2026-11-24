#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""板块对比面板：把 124 个申万二级板块的当日数据 + 广度 + 估值倍数 + 两融 → 可排序 HTML。

产物：reports/sector/dashboard-<date>.html（纯静态，双击即开，无外部依赖）

列：板块 / 一级行业 / 涨跌% / 成交额(亿) / 占全市场% / 上涨占比% / PE_TTM / 估值倍数 / 深度两融(亿)
功能：点表头排序、搜索框过滤、按列高亮极值。
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
SW = os.path.join(ROOT, "data", "sw")
OUT = os.path.join(ROOT, "reports", "sector")


def load(fp, default=None):
    try:
        with io.open(fp, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def latest(pattern):
    fs = sorted(glob.glob(os.path.join(ROOT, pattern)))
    return fs[-1] if fs else None


def build(date=None):
    daily_fp = os.path.join(SW, "daily", f"{date}.json") if date else latest(os.path.join("data", "sw", "daily", "*.json"))
    if not daily_fp or not os.path.exists(daily_fp):
        print("没有板块日线数据，先跑 python scripts/sw_sectors.py --meta --daily")
        return 1
    day = load(daily_fp, {}).get("date") or date
    daily = load(daily_fp, {}).get("sectors") or []

    br_fp = os.path.join(SW, "breadth", f"{day}.json")
    breadth = {x["code"]: x for x in (load(br_fp, {}).get("sectors") or [])}

    val = (load(os.path.join(ROOT, "data", "cache", "sector_val_by_sector.json"), {}) or {}).get("by_sector") or {}
    vmap = {}
    idx = (load(os.path.join(ROOT, "data", "sector_index_map.json"), {}) or {}).get("map") or {}
    for name, code in idx.items():
        if name in val:
            vmap[name] = val[name]

    # 板块两融：按成分聚合（明细口径，仅深市）
    mg = latest(os.path.join("data", "sw", "margin", "*.json"))
    margin, mday = {}, None
    if mg:
        m = load(mg, {}) or {}
        bal = m.get("fin_bal") or {}
        mday = m.get("date")
        cons = (load(os.path.join(SW, "constituents.json"), {}) or {}).get("sectors") or {}
        for cid, meta in cons.items():
            codes = meta.get("codes") or []
            hit = [bal[c] for c in codes if c in bal]
            if hit:
                margin[cid] = round(sum(hit), 2)
    cons = (load(os.path.join(SW, "constituents.json"), {}) or {}).get("sectors") or {}

    tot_amt = sum((x.get("amount") or 0) for x in daily) or 1
    # 一级行业名（用于估值/两融映射）
    rows = []
    for x in sorted(daily, key=lambda r: -(r.get("amount") or 0)):
        code, name = x.get("code"), x.get("name")
        parent = x.get("parent")
        b = breadth.get(code) or {}
        v = vmap.get(name) or vmap.get(parent) or {}
        mgv = margin.get(code)
        rows.append({
            "code": code, "name": name, "parent": parent,
            "pct": x.get("pct"), "amount": x.get("amount"),
            "share": round((x.get("amount") or 0) / tot_amt * 100, 2),
            "breadth": b.get("breadth"), "n": b.get("n"), "up": b.get("up"),
            "pe_ttm": x.get("pe_ttm"), "ratio": v.get("ratio"),
            "margin": mgv,
        })
    rows.sort(key=lambda r: -(r["amount"] or 0))

    html = render(day, rows, tot_amt, mday)
    os.makedirs(OUT, exist_ok=True)
    fp = os.path.join(OUT, f"dashboard-{day}.html")
    with io.open(fp, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"板块面板：{day} · {len(rows)} 个板块 → {os.path.relpath(fp, ROOT)}")
    return 0


def render(day, rows, tot_amt, mday):
    data = json.dumps(rows, ensure_ascii=False)
    n = len(rows)
    upd = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>板块对比面板 · {day}</title>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--tx:#1f2328;--dim:#6b7280;--line:#e3e6ea;--up:#d03050;--down:#1b7f4d}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--tx);font:13px/1.5 system-ui,-apple-system,'Segoe UI','Microsoft YaHei',sans-serif}}
.wrap{{max-width:1280px;margin:0 auto;padding:22px 18px 60px}}
h1{{font-size:19px;margin:0 0 4px}}
.sub{{color:var(--dim);font-size:12px;margin-bottom:16px}}
.bar{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:12px}}
input{{padding:7px 11px;border:1px solid var(--line);border-radius:7px;font-size:13px;width:220px;outline:none}}
input:focus{{border-color:#8fa9c4}}
button{{padding:6px 11px;border:1px solid var(--line);background:var(--card);border-radius:7px;cursor:pointer;font-size:12.5px}}
button:hover{{border-color:#8fa9c4}}
button.on{{background:#1f2328;color:#fff;border-color:#1f2328}}
table{{width:100%;border-collapse:collapse;background:var(--card);border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
th,td{{padding:7px 10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}}
th{{position:sticky;top:0;background:#eef1f4;font-weight:600;cursor:pointer;user-select:none;font-size:12px}}
th:hover{{background:#e3e8ee}}
th.asc::after{{content:' ▲';font-size:9px}}
th.desc::after{{content:' ▼';font-size:9px}}
td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){{text-align:left}}
tbody tr:hover{{background:#f3f7fb}}
.up{{color:var(--up)}} .down{{color:var(--down)}} .na{{color:#b6bcc5}}
.num{{font-variant-numeric:tabular-nums;font-family:ui-monospace,Consolas,monospace;font-size:12.5px}}
.foot{{margin-top:14px;color:var(--dim);font-size:11.5px;line-height:1.8}}
.tag{{display:inline-block;padding:1px 6px;border-radius:4px;background:#eef1f4;color:var(--dim);font-size:11px;margin-left:6px}}
</style></head><body><div class="wrap">
<h1>申万二级板块对比 · {day}</h1>
<div class="sub">{n} 个板块 · 合计成交 {tot_amt:,.0f} 亿 · 两融数据期 {mday or '—'}（仅深市明细口径） · 生成 {upd}</div>
<div class="bar">
  <input id="q" placeholder="搜索板块 / 一级行业…">
  <button data-sort="amount" class="on">按成交额</button>
  <button data-sort="pct">按涨跌</button>
  <button data-sort="breadth">按上涨占比</button>
  <button data-sort="ratio">按估值倍数</button>
  <button data-sort="margin">按两融余额</button>
</div>
<table id="t"><thead><tr>
<th data-k="name">板块</th><th data-k="parent">一级行业</th>
<th data-k="pct">涨跌%</th><th data-k="amount">成交额(亿)</th>
<th data-k="share">占全市场%</th><th data-k="breadth">上涨占比%</th>
<th data-k="n">成分数</th><th data-k="pe_ttm">PE_TTM</th>
<th data-k="ratio">估值倍数</th><th data-k="margin">两融(亿)</th>
</tr></thead><tbody></tbody></table>
<div class="foot">
涨跌红涨绿跌 · 「估值倍数」= 板块 PE ÷ 沪深300 PE（只映射了 45 个板块，其余 —）<br>
「两融」只含板块内深市标的融资余额，与市场层官方汇总口径不同，不可相加<br>
数据源：申万二级官网（行情/成分）+ 中证指数（估值）+ 深交所（两融明细）· 仅供客观核对，不构成判断
</div></div>
<script>
const DATA = {data};
const TB = document.querySelector('#t tbody');
let sortKey = 'amount', asc = false;
function fmt(v, d=2){{ return (v===null||v===undefined||isNaN(v)) ? '<span class="na">—</span>' : v.toFixed(d); }}
function paint(){{
  const q = document.querySelector('#q').value.trim();
  const rows = DATA.filter(r => !q || (r.name||'').includes(q) || (r.parent||'').includes(q))
    .slice().sort((a,b)=>{{
      let x=a[sortKey], y=b[sortKey];
      if (typeof x === 'string' || typeof y === 'string') {{ x=x||''; y=y||''; return asc ? x.localeCompare(y,'zh') : y.localeCompare(x,'zh'); }}
      const nx = (x===null||x===undefined)?-1e18:x, ny=(y===null||y===undefined)?-1e18:y;
      return asc ? nx-ny : ny-nx;
    }});
  TB.innerHTML = rows.map(r=>{{
    const pc = r.pct===null||r.pct===undefined?'na':(r.pct>0?'up':(r.pct<0?'down':''));
    const bc = r.breadth===null||r.breadth===undefined?'na':(r.breadth>=50?'up':'down');
    return `<tr><td>${{r.name}}<span class="tag">${{r.code}}</span></td><td>${{r.parent||''}}</td>
      <td class="num ${{pc}}">${{r.pct>0?'+':''}}${{fmt(r.pct)}}</td>
      <td class="num">${{fmt(r.amount,0)}}</td><td class="num">${{fmt(r.share)}}</td>
      <td class="num ${{bc}}">${{fmt(r.breadth,1)}}</td><td class="num">${{r.n||'<span class="na">—</span>'}}</td>
      <td class="num">${{fmt(r.pe_ttm,1)}}</td><td class="num">${{fmt(r.ratio)}}</td>
      <td class="num">${{fmt(r.margin,1)}}</td></tr>`;
  }}).join('');
}}
document.querySelectorAll('th').forEach(th=>th.onclick=()=>{{
  const k = th.dataset.k; if(!k) return;
  if (sortKey===k) asc=!asc; else {{ sortKey=k; asc = (k==='name'||k==='parent'); }}
  document.querySelectorAll('th').forEach(t=>t.classList.remove('asc','desc'));
  th.classList.add(asc?'asc':'desc'); paint();
}});
document.querySelectorAll('button[data-sort]').forEach(b=>b.onclick=()=>{{
  sortKey=b.dataset.sort; asc=false;
  document.querySelectorAll('button[data-sort]').forEach(x=>x.classList.remove('on'));
  b.classList.add('on'); paint();
}});
document.querySelector('#q').oninput = paint;
paint();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    a = ap.parse_args()
    return build(a.date or None)


if __name__ == "__main__":
    sys.exit(main())
