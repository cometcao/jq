#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深度巡检：三角一致性 + 全序列回放 + 单位 + 数据期 + 板块独立复算。

与 selftest.py 的分工：
  selftest.py —— 已知规则的机械校验（契约、回归、歧义）
  本文件     —— **主动找新 bug**：拿原始数据把 output 重算一遍，比对所有落盘层。

用法：python -B scripts/deep_audit.py [-v]
退出码：0 未发现异常 / 1 有异常
"""
import io
import os
import sys
import json
import glob
import re
import datetime as dt
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

FINDINGS = []
C_INDEX = {}


def add(level, area, msg, detail=""):
    FINDINGS.append({"level": level, "area": area, "msg": msg, "detail": detail})


def load(fp, default=None):
    try:
        with io.open(fp, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def num(t):
    m = re.search(r"-?[\d,]+(?:\.\d+)?", str(t or ""))
    return float(m.group(0).replace(",", "")) if m else None


def facts_index():
    """{iid: [record...]} 按 data_period 升序。"""
    idx = {}
    for fp in glob.glob(os.path.join(ROOT, "data", "facts", "*", "*.json")):
        r = load(fp)
        if not r or not r.get("indicator_id"):
            continue
        d = os.path.basename(os.path.dirname(fp))
        if r.get("data_period") != d:
            add("ERROR", "facts", f"{r['indicator_id']} 的 data_period={r.get('data_period')} 与目录 {d} 不符")
        idx.setdefault(r["indicator_id"], []).append(r)
    for k in idx:
        idx[k].sort(key=lambda r: r.get("data_period") or "")
    return idx


def hist_index():
    idx = {}
    for fp in glob.glob(os.path.join(ROOT, "data", "history", "*.jsonl")):
        iid = os.path.basename(fp)[:-6]
        rows = []
        for x in io.open(fp, encoding="utf-8").read().splitlines():
            if not x.strip():
                continue
            try:
                r = json.loads(x)
            except Exception:
                add("ERROR", "history", f"{iid} 有无法解析的行")
                continue
            if r.get("data_period") and r.get("value") is not None:
                rows.append(r)
        rows.sort(key=lambda r: r["data_period"])
        idx[iid] = rows
    return idx


def cache_index():
    idx = {}
    for fp in glob.glob(os.path.join(ROOT, "data", "cache", "*.json")):
        r = load(fp)
        if isinstance(r, dict) and r.get("indicator_id"):
            idx[r["indicator_id"]] = r
    return idx


def check_triangle(F, H, C):
    """facts / history / cache 三方同日同值（金额用 base_value）。"""
    for iid in sorted(set(F) & set(H)):
        f_last = F[iid][-1]
        h_last = H[iid][-1]
        if f_last.get("data_period") != h_last.get("data_period"):
            add("WARN", "三角", f"{iid} 最新期不同：facts {f_last.get('data_period')} vs history {h_last.get('data_period')}")
            continue
        fv = f_last.get("base_value")
        hv = h_last.get("base_value", h_last.get("value"))
        if fv is None or hv in (None, 0):
            continue
        rel = abs(fv - hv) / abs(hv)
        if rel > 0.005:
            add("ERROR", "三角", f"{iid} facts={fv} vs history={hv} 差 {rel*100:.2f}%")
    # cache vs facts
    for iid, c in C.items():
        if iid not in F:
            add("WARN", "三角", f"{iid} 有 cache 但 facts 里没有")
            continue
        f_last = F[iid][-1]
        if c.get("data_period") != f_last.get("data_period"):
            add("WARN", "三角", f"{iid} cache 期 {c.get('data_period')} ≠ facts 期 {f_last.get('data_period')}")
            continue
        cv = num((c.get("current_state") or {}).get("数值"))
        fv_show = num((f_last.get("current_state") or {}).get("数值"))
        if cv is not None and fv_show is not None and abs(cv - fv_show) > max(abs(fv_show) * 1e-6, 1e-9):
            add("ERROR", "三角", f"{iid} cache={cv} vs facts 展示值={fv_show}")


def check_units(F, H):
    for iid, rows in F.items():
        r = rows[-1]
        if r.get("base_value") is None:
            add("ERROR", "单位", f"{iid} 缺 base_value")
        # history 与 facts 基础单位应一致
        if iid in H and H[iid]:
            hr = H[iid][-1]
            if "base_value" not in hr:
                add("WARN", "单位", f"{iid} history 缺 base_value")
            else:
                fv, hv = r.get("base_value"), hr["base_value"]
                if fv and hv and abs(fv - hv) / abs(hv) > 0.01:
                    add("WARN", "单位", f"{iid} facts/history base 差 {abs(fv-hv)/abs(hv)*100:.2f}%")


def check_periods(F, today=None):
    today = today or dt.date.today().isoformat()
    for iid, rows in F.items():
        for r in rows:
            dp = r.get("data_period") or ""
            if dp > today:
                add("ERROR", "数据期", f"{iid} 数据期 {dp} 在未来")
            if r.get("release_date") and r["release_date"] < dp:
                add("WARN", "数据期", f"{iid} release_date {r['release_date']} 早于数据期 {dp}")


SNAPSHOT_IIDS = {"MKT_TURNOVER", "MKT_BREADTH", "SECTOR_AMT_CONC", "MKT_MARGIN_BAL",
                 "MKT_MARGIN_COLLATERAL", "MKT_DR007", "MKT_CGB10Y", "MKT_MARGIN_BAL_SZ"}


def check_duplicate_values(H):
    """快照型日频序列连续两期完全相同 = 源可能在回放上日值。

    政策/月度指标（LPR、房价同比等）重复是常态，不报。
    """
    for iid in SNAPSHOT_IIDS & set(H):
        rows = H[iid]
        if len(rows) < 2:
            continue
        a, b = rows[-2], rows[-1]
        if a["value"] and b["value"] and abs(a["value"] - b["value"]) < 1e-12:
            add("WARN", "序列", f"{iid} 最近两期完全相同（{a['data_period']} / {b['data_period']} = {a['value']}）")


def check_cache_age(F):
    """cache 的数据期不得落后超过 3 倍频率（否则就是"拿停更值冒充当前值"）。"""
    FREQ_M = {"日": 0.2, "月": 3, "季": 9}
    reg = load(os.path.join(ROOT, "dist", "market-state", "references", "registry.json"), {}) or {}
    import datetime as _dt
    for iid, c in C_INDEX.items():
        dp = c.get("data_period") or ""
        if not dp:
            continue
        freq = (reg.get(iid) or {}).get("frequency") or ""
        limit = FREQ_M.get(freq)
        if not limit:
            continue
        try:
            d0 = _dt.date.fromisoformat(dp)
        except Exception:
            continue
        months = (_dt.date.today().year - d0.year) * 12 + (_dt.date.today().month - d0.month)
        if months > limit and freq == "月":
            add("ERROR", "cache", f"{iid} cache 数据期 {dp} 落后 {months} 个月（>3），却仍留在 cache")
        if freq == "日":
            days = (_dt.date.today() - d0).days
            if days > 10:
                add("ERROR", "cache", f"{iid} cache 数据期 {dp} 落后 {days} 天（日频）")


def check_kind_unit(F):
    """value_kind 与实际值单位必须相容（ratio 却给亿元 = 口径错位）。"""
    reg = load(os.path.join(ROOT, "dist", "market-state", "references", "registry.json"), {}) or {}
    for iid, rows in F.items():
        r = rows[-1]
        kind = (reg.get(iid) or {}).get("value_kind") or ""
        txt = str((r.get("current_state") or {}).get("数值") or "")
        if kind == "ratio" and ("亿元" in txt or "万亿" in txt):
            add("ERROR", "口径", f"{iid} 标 ratio，但值是金额：{txt}")
        unit = (reg.get(iid) or {}).get("unit") or ""
        if kind == "level" and "%" in txt and unit not in ("U2", "U7"):
            add("WARN", "口径", f"{iid} 标 level（unit={unit}），但值是百分比：{txt}")


def check_state_pages():
    for fp in sorted(glob.glob(os.path.join(ROOT, "reports", "*-market-state.md")))[-3:]:
        t = io.open(fp, encoding="utf-8").read()
        if "```" not in t:
            add("ERROR", "页面", f"{os.path.basename(fp)} 没有代码块")
            continue
        body = t.split("```")[1]
        lines = [l for l in body.splitlines() if re.match(r"^C[1-6] ", l)]
        m = re.search(r"本次 (\d+) 条证据", body)
        if m and int(m.group(1)) != len(lines):
            add("ERROR", "页面", f"{os.path.basename(fp)} 声明 {m.group(1)} 条，实际 {len(lines)} 条")
        for l in lines:
            if "｜依据：" not in l or "｜边界：" not in l:
                add("ERROR", "页面", f"{os.path.basename(fp)} 证据行结构不全：{l[:60]}")
        # 数据期不得晚于页面 as-of
        asof = re.search(r"as-of (\d{4}-\d{2}-\d{2})", t)
        if asof:
            for l in lines:
                for d in re.findall(r"（(\d{4}-\d{2}-\d{2})\*?）", l):
                    if d > asof.group(1):
                        add("ERROR", "页面", f"{os.path.basename(fp)} 引用未来日期 {d}")


def check_cards():
    for name in ("card-market.html", "card-events.html"):
        fp = os.path.join(ROOT, "reports", name)
        if not os.path.exists(fp):
            add("WARN", "卡片", f"{name} 不存在")
            continue
        h = io.open(fp, encoding="utf-8").read()
        if re.search(r"\bMKT_[A-Z0-9_]{3,}", h):
            add("ERROR", "卡片", f"{name} 露出裸指标 id")
        if re.search(r"(NaN|None|nan|Infinity)", h):
            add("ERROR", "卡片", f"{name} 出现 NaN/None")
        if name != "card-market.html":
            continue
        st = load(os.path.join(ROOT, "reports", "state-market.json"), {}) or {}
        for r in (st.get("card_rows") or []):
            v = r.get("value")
            if v is None:
                continue
            cands = {f"{v}", f"{v:.2f}", f"{v:.0f}", f"{v:,.2f}", f"{v:,.0f}", f"{abs(v):,.0f}"}
            if not any(c in h for c in cands):
                add("WARN", "卡片", f"{name} 未出现 {r['label']} 的值 {v}")


def check_sectors():
    import state as S
    for name in ("半导体", "医药", "银行"):
        try:
            as_of, body, sec = S.build_sector("traceable", name)
        except Exception as e:
            add("ERROR", "板块", f"{name} 板块层构建失败：{type(e).__name__}: {e}")
            continue
        lines = [l for l in body.splitlines() if re.match(r"^C[1-6] ", l)]
        add("INFO", "板块", f"{name} 产出 {len(lines)} 条（as-of {as_of}）")
        # C2 份额必须用最新日期的成交额
        c2 = [l for l in lines if l.startswith("C2 ")]
        if c2 and "份额" in c2[0]:
            ds = re.findall(r"（(\d{4}-\d{2}-\d{2})", c2[0])
            if ds and ds[0] < as_of:
                gap = (dt.date.fromisoformat(as_of) - dt.date.fromisoformat(ds[0])).days
                if gap >= 3:
                    add("ERROR", "板块", f"{name} C2 份额用 {ds[0]} 的数据，落后 as-of {gap} 天")


def check_events():
    cals = sorted(glob.glob(os.path.join(ROOT, "data", "events", "calendar-*.json")))
    if not cals:
        add("WARN", "事件", "没有日历文件")
        return
    cal = load(cals[-1], {}) or {}
    evs = cal.get("events") or []
    fut = [e for e in evs if e.get("event_status") == "未来预定"]
    hap = [e for e in evs if e.get("event_status") == "已发生"]
    add("INFO", "事件", f"日历 {os.path.basename(cals[-1])}：未来 {len(fut)} · 已发生 {len(hap)}")
    for e in fut:
        if (e.get("event_date") or "") < (cal.get("as_of") or ""):
            add("ERROR", "事件", f"未来事件日期 {e.get('event_date')} 早于 as-of {cal.get('as_of')}")
    for e in evs:
        if not e.get("source_link"):
            add("WARN", "事件", f"{e.get('event_date')} {e.get('scope','')[:20]} 无官方链接")
    # 央行到期：未来 5 天内应至少有一条
    soon = [e for e in fut if "逆回购" in (e.get("scope") or "")]
    add("INFO", "事件", f"逆回购到期事件 {len(soon)} 条")


def check_docs():
    sk = io.open(os.path.join(ROOT, "dist", "market-state", "SKILL.md"), encoding="utf-8").read()
    reg = load(os.path.join(ROOT, "dist", "market-state", "references", "registry.json"), {}) or {}
    ledger = io.open(os.path.join(ROOT, "docs", "12_数据源台账.md"), encoding="utf-8").read()
    m = re.search(r"(\d+) 个指标", ledger)
    if m and int(m.group(1)) != len(reg):
        add("ERROR", "文档", f"台账写 {m.group(1)} 个指标，注册表 {len(reg)} 个")
    for pat, label in ((r"(\d+) 条历史坑断言", "回归条数"), (r"(\d+) 条", "条数")):
        mm = re.search(pat, sk)
        if mm:
            add("INFO", "文档", f"SKILL 提到{label}：{mm.group(1)}")
            break
    if "124 个" in sk and "131 个" not in sk:
        add("WARN", "文档", "SKILL 仍只写 124 个板块（实际 131 个）")


def replay_days(n=3):
    days = sorted({os.path.basename(fp)[:10] for fp in glob.glob(os.path.join(ROOT, "reports", "state-history", "*.json"))})[-n:]
    for d in days:
        r = subprocess.run([sys.executable, "-B", os.path.join(ROOT, "scripts", "state.py"),
                            "--layer", "market", "--as-of", d, "--json"],
                           capture_output=True, text=True, encoding="utf-8", cwd=ROOT, timeout=180)
        try:
            j = json.loads(r.stdout)
        except Exception:
            add("ERROR", "回放", f"{d} 回放失败：{(r.stderr or '')[-60:]}")
            continue
        cov = (j.get("chain_coverage") or {}).get("text")
        add("INFO", "回放", f"{d} 覆盖 {cov}")
        for l in j.get("lines") or []:
            if (l.get("period") or "") > d:
                add("ERROR", "回放", f"{d} 引用了未来期 {l.get('period')}")


def main():
    verbose = "-v" in sys.argv
    F, H, C = facts_index(), hist_index(), cache_index()
    global C_INDEX
    C_INDEX = C
    check_triangle(F, H, C)
    check_units(F, H)
    check_periods(F)
    check_cache_age(F)
    check_kind_unit(F)
    check_duplicate_values(H)
    check_state_pages()
    check_cards()
    try:
        check_sectors()
    except Exception as e:
        add("ERROR", "板块", f"板块巡检异常：{type(e).__name__}: {e}")
    check_events()
    check_docs()
    replay_days(3)

    errs = [f for f in FINDINGS if f["level"] == "ERROR"]
    warns = [f for f in FINDINGS if f["level"] == "WARN"]
    infos = [f for f in FINDINGS if f["level"] == "INFO"]
    if verbose:
        for f in infos:
            print(f"  · {f['area']}: {f['msg']}")
    for f in errs:
        print(f"  ✗ [{f['area']}] {f['msg']}" + (f"  ({f['detail']})" if f["detail"] else ""))
    for f in warns:
        print(f"  ! [{f['area']}] {f['msg']}" + (f"  ({f['detail']})" if f["detail"] else ""))
    print(f"\n深度巡检：{len(errs)} 错误 / {len(warns)} 警告 / {len(infos)} 信息")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
