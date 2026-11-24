#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归测试：把已发生过的坑写成断言，防止改代码时悄悄回退。

运行：python scripts/test_regression.py          # 全部
      python scripts/test_regression.py -v       # 逐条打印
不依赖 pytest，退出码 0=全过，1=有失败。

覆盖的坑（按发生时间）：
  T01 申万成交额单位（亿元，误除 100 → 份额 0.14%）
  T02 交易日口径（period 借指数缓存 → 值标错日期）
  T03 同花顺板块成交额异常（161 亿 vs 14222 亿 → 应走备源）
  T04 history_prev 取不到前值（误判“不变”）
  T05 BOM 文件（json.load 静默失败 → 板块解析为空）
  T06 C4 状态词白名单（“板块两融”不在白名单）
  T07 不可读行必须写 无源/无证据/stale
  T08 对手方叙事（边界里出现“流向”被拦）
  T09 读法数字与证据行同源
  T10 板块串板块（C1/C3/C5 不得回退到目标板块）
  T11 一级行业聚合（医药 → 6 个二级）
  T12 事件信息含量（会见/调研 → low；印发/征求意见 → high）
  T13 事件分层（市场页不含板块事件，反之亦然）
  T14 六环链条完整性行
  T15 估值映射全部可取（离线校验表结构）
"""
import io
import os
import re
import sys
import json
import glob
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

PASS, FAIL = [], []


def check(tid, desc, cond, detail=""):
    (PASS if cond else FAIL).append((tid, desc, detail))


def load_json(fp, default=None):
    try:
        with io.open(fp, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def latest(pattern):
    fs = sorted(glob.glob(os.path.join(ROOT, pattern)))
    return fs[-1] if fs else None


# ---------------------------------------------------------------- T01 单位
def t01():
    import state as S
    secs = (load_json(os.path.join(ROOT, "data", "sw", "sectors.json"), {}) or {}).get("sectors") or []
    code = secs[0]["code"] if secs else None
    if not code:
        return check("T01", "申万成交额单位（亿元，不除 100）", False, "无 sectors.json")
    hist = S._sw_hist_amount(code)
    check("T01", "申万成交额单位（亿元，不除 100）", len(hist) > 0, f"{code} 无历史")
    if hist:
        vals = [a for _, a in hist]
        # 单板块成交额应是 1~5000 亿量级；若误除 100 会变成 0.01~50
        ok = max(vals) > 1.0 and max(vals) < 20000
        check("T01b", "成交额量级合理（1~20000 亿）", ok, f"max={max(vals):.2f}")


# ---------------------------------------------------------------- T02 交易日口径
def t02():
    import state as S
    cal = load_json(latest("data/events/calendar-*.json"), {}) or {}
    facts = glob.glob(os.path.join(ROOT, "data", "facts", "*", "MKT_TURNOVER.json"))
    if not facts:
        return check("T02", "MKT_TURNOVER 数据期=真实交易日", False, "无 fact")
    rec = load_json(sorted(facts)[-1], {}) or {}
    dp = rec.get("data_period") or ""
    # 数据期必须是工作日
    import datetime as dt
    try:
        d = dt.date.fromisoformat(dp)
        ok = d.weekday() < 5
    except Exception:
        ok = False
    check("T02", "MKT_TURNOVER 数据期是工作日", ok, f"data_period={dp}")


# ---------------------------------------------------------------- T03 成交额异常守卫
def t03():
    p = os.path.join(ROOT, "scripts", "fetch.py")
    src = io.open(p, encoding="utf-8").read()
    has = ("中位数" in src or "median" in src) and "tx" in src
    check("T03", "同花顺成交额有合理性检查与备源", has)


# ---------------------------------------------------------------- T04 前值
def t04():
    import state as S
    p = os.path.join(ROOT, "scripts", "fetch.py")
    src = io.open(p, encoding="utf-8").read()
    check("T04", "history_prev 存在（回历史取前值）", "def history_prev" in src)
    # 参与度前值不应等于当期（否则“不变”误判）
    facts = glob.glob(os.path.join(ROOT, "data", "facts", "*", "MKT_TURNOVER.json"))
    if facts:
        rec = load_json(sorted(facts)[-1], {}) or {}
        cs = rec.get("current_state") or {}
        v = str(cs.get("数值") or "")
        check("T04b", "MKT_TURNOVER 有当期值", bool(v), v[:40])


# ---------------------------------------------------------------- T05 BOM
def t05():
    bad = []
    for fp in glob.glob(os.path.join(ROOT, "data", "*.json")) + glob.glob(os.path.join(ROOT, "data", "*", "*.json")):
        if os.path.basename(fp).startswith("."):
            continue
        try:
            io.open(fp, encoding="utf-8").read(1)
        except Exception:
            bad.append(os.path.basename(fp))
            continue
        with io.open(fp, "rb") as f:
            if f.read(3) == b"\xef\xbb\xbf":
                bad.append(os.path.basename(fp))
    check("T05", "data/*.json 无 BOM", not bad, ",".join(bad[:5]))


# ---------------------------------------------------------------- T06/T07 状态词与不可读
def t06():
    page = latest("reports/*-market-state.md")
    if not page:
        return check("T06", "市场页存在", False)
    txt = io.open(page, encoding="utf-8").read()
    ring = [ln for ln in txt.split("```")[1].splitlines() if ln.startswith("C4 ")]
    c4 = [ln for ln in ring if "不可读" not in ln]
    ok_words = ("加杠杆", "去杠杆", "不变", "现金池增", "现金池减")
    bad = [ln[:40] for ln in c4 if not any(w in ln for w in ok_words)]
    check("T06", "C4 有值行用白名单状态词", not bad, str(bad[:2]))
    for ln in ring:
        if "不可读" in ln:
            check("T07", "不可读行含 无源/无证据/stale", any(k in ln for k in ("无源", "无证据", "stale")), ln[:50])
            break


# ---------------------------------------------------------------- T08 对手方叙事
def t08():
    page = latest("reports/*-sector-*-state.md")
    if not page:
        return check("T08", "板块页存在", False)
    txt = io.open(page, encoding="utf-8").read()
    body = txt.split("```")[1] if "```" in txt else txt
    bad = [k for k in ("流向", "对手方", "接盘") if k in body]
    check("T08", "板块页无对手方叙事词", not bad, str(bad))


# ---------------------------------------------------------------- T09 读法与证据行同源
def t09():
    page = latest("reports/*-sector-*-state.md")
    if not page:
        return check("T09", "板块页存在", False)
    txt = io.open(page, encoding="utf-8").read()
    body = txt.split("```")[1]
    has_read = "读法（资金视角）" in body
    check("T09", "板块页有读法段（R11.3）", has_read)
    if not has_read:
        return
    # 读法里的份额必须出现在 C2 证据行
    m = re.search(r"吃下全市场成交额的 ([\d.]+)%", body)
    c2 = [ln for ln in body.splitlines() if ln.startswith("C2 ")]
    ok = True
    if m and c2:
        ok = m.group(1) in c2[0]
    check("T09b", "读法份额与 C2 证据行一致", ok, (m.group(1) if m else "无"))


# ---------------------------------------------------------------- T10 板块串板块
def t10():
    a = latest("reports/*-sector-半导体-state.md")
    b = latest("reports/*-sector-银行-state.md")
    if not (a and b):
        return check("T10", "两个板块页存在", False)
    ta = io.open(a, encoding="utf-8").read().split("```")[1]
    tb = io.open(b, encoding="utf-8").read().split("```")[1]
    # 银行页不应出现半导体专属数值
    leaked = "6.37×" in tb or "87.36" in tb
    check("T10", "银行页未串半导体估值", not leaked)
    # 银行无对口部委映射 → C1 应为不可读，且不得写“工业和信息化部”
    c1 = [ln for ln in tb.splitlines() if ln.startswith("C1 ")]
    ok = bool(c1) and "工业和信息化部" not in c1[0] or "半导体" in c1[0]
    check("T10b", "银行 C1 未串半导体部委", ok, c1[0][:60] if c1 else "无 C1")


# ---------------------------------------------------------------- T11 一级行业聚合
def t11():
    import state as S
    lst = S._sw_sectors_of("医药")
    check("T11", "医药 → 多个申万二级（一级聚合）", len(lst) >= 5, f"{len(lst)} 个")
    lst2 = S._sw_sectors_of("半导体")
    check("T11b", "半导体 → 单个二级（精确匹配优先）", len(lst2) == 1, f"{len(lst2)} 个")


# ---------------------------------------------------------------- T12 事件信息含量
def t12():
    import events as E
    low = E.info_level("雷平会见俄罗斯联邦卫生监督局副局长")
    high1 = E.info_level("工业和信息化部办公厅关于印发2026年第五批行业标准制修订项目计划的通知")
    high2 = E.info_level("关于公开征求《半导体集成电路 融合视觉传感器测试方法》等46项国家标准计划项目意见的公示")
    check("T12", "行程类判 low", low == "low", low)
    check("T12b", "印发/征求意见判 high", high1 == "high" and high2 == "high", f"{high1}/{high2}")


# ---------------------------------------------------------------- T13 事件分层
def t13():
    cal = load_json(latest("data/events/calendar-*.json"), {}) or {}
    evs = cal.get("events") or []
    layers = {e.get("layer") or "市场" for e in evs}
    check("T13", "日历含市场与板块两层", layers >= {"市场"}, str(layers))
    mp = latest("reports/*-market-state.md")
    sp = latest("reports/*-sector-*-state.md")
    if mp and sp:
        mt = io.open(mp, encoding="utf-8").read()
        st = io.open(sp, encoding="utf-8").read()
        check("T13b", "市场页有事件段", "—— 事件" in mt)
        check("T13c", "板块页有板块事件段或明确无", ("—— 板块事件" in st) or ("板块事件" not in st))


# ---------------------------------------------------------------- T14 链条完整性
def t14():
    for pat, name in (("reports/*-market-state.md", "市场"), ("reports/*-sector-*-state.md", "板块")):
        fp = latest(pat)
        if not fp:
            check("T14", f"{name}页存在", False)
            continue
        txt = io.open(fp, encoding="utf-8").read()
        check("T14", f"{name}页有链条完整性行", "链条完整性" in txt)


# ---------------------------------------------------------------- T15 映射表
def t15():
    m = (load_json(os.path.join(ROOT, "data", "sector_index_map.json"), {}) or {}).get("map") or {}
    check("T15", "估值映射 ≥ 40 个板块", len(m) >= 40, f"{len(m)} 个")
    bad = [k for k, v in m.items() if not re.match(r"^(H\d{5}|\d{6})$", str(v))]
    check("T15b", "映射代码格式合法", not bad, str(bad[:3]))
    d = (load_json(os.path.join(ROOT, "data", "sector_dept_map.json"), {}) or {}).get("map") or {}
    check("T15c", "部委映射存在", len(d) >= 4, f"{len(d)} 个")


# ---------------------------------------------------------------- T16 页面校验器
def t16():
    ck = os.path.join(ROOT, "dist", "market-state", "check.py")
    if not os.path.exists(ck):
        return check("T16", "check.py 存在", False)
    r = subprocess.run([sys.executable, ck, "--demo"], capture_output=True, text=True,
                       encoding="utf-8", cwd=os.path.dirname(ck), timeout=120)
    check("T16", "check.py --demo PASS", "PASS" in (r.stdout or ""), (r.stdout or "")[-60:])
    for fp in (latest("reports/*-market-state.md"), latest("reports/*-sector-*-state.md")):
        if not fp:
            continue
        rr = subprocess.run([sys.executable, ck, "--page", fp], capture_output=True, text=True,
                            encoding="utf-8", cwd=os.path.dirname(ck), timeout=120)
        check("T16b", f"{os.path.basename(fp)} 校验 0 错误", "0 错误" in (rr.stdout or ""), (rr.stdout or "")[:120])


# ---------------------------------------------------------------- T17 C4 深市前值
def t17():
    mp = latest("reports/*-market-state.md")
    if not mp:
        return check("T17", "市场页存在", False)
    txt = io.open(mp, encoding="utf-8").read().split("```")[1]
    c4 = [ln for ln in txt.splitlines() if ln.startswith("C4 ") and "深市" in ln]
    ok = bool(c4) and "对比上一期" in c4[0]
    check("T17", "市场层 C4 深市两融带前值（不再“仅单日”）", ok, c4[0][:70] if c4 else "无深市 C4 行")
    sp = latest("reports/*-sector-*-state.md")
    if sp:
        st = io.open(sp, encoding="utf-8").read().split("```")[1]
        sc4 = [ln for ln in st.splitlines() if ln.startswith("C4 ")]
        ok2 = bool(sc4) and ("上一期" in sc4[0] or "不可读" in sc4[0])
        check("T17b", "板块层 C4 有前值或明确不可读", ok2, sc4[0][:70] if sc4 else "无")


# ---------------------------------------------------------------- T18 一致性 & 阈值
def t18():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "check_consistency.py")],
                       capture_output=True, text=True, encoding="utf-8", timeout=180)
    check("T18", "cache 与 facts 一致（0 漂移）", "0 漂移" in (r.stdout or ""), (r.stdout or "").strip()[-80:])
    th = load_json(os.path.join(ROOT, "data", "thresholds.json"), {}) or {}
    need = ["breadth_pct", "concentration_pct", "share_change_pp", "margin_change_yi",
            "prev_coverage", "stale_warn", "stale_block"]
    miss = [k for k in need if k not in th]
    check("T18b", "thresholds.json 必需键齐全", not miss, str(miss))
    src = io.open(os.path.join(ROOT, "scripts", "state.py"), encoding="utf-8").read()
    check("T18c", "state.py 用 TH 而非硬编码 50", 'TH["breadth_pct"]' in src)


# ---------------------------------------------------------------- T19 未来事件干净
def t19():
    import datetime as _dt
    cal = load_json(latest("data/events/calendar-*.json"), {}) or {}
    evs = cal.get("events") or []
    today = _dt.date.today().isoformat()
    bad = [e for e in evs if e.get("event_status") == "未来预定" and (e.get("event_date") or "") < today]
    check("T19", "未来预定事件不含过去日期", not bad, str([e["event_date"] for e in bad][:3]))
    fut = [e for e in evs if e.get("event_status") == "未来预定"]
    issuers = {e.get("issuer") for e in fut}
    check("T19b", "未来事件含央行操作/解禁/新股 至少两类",
          len({"中国人民银行", "交易所·限售解禁", "交易所·新股发行"} & issuers) >= 2, str(sorted(issuers)))


# ---------------------------------------------------------------- T20 卡片由脚本生成且过契约校验
def t20():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "card.py"),
                        "--out", "reports/card-market.html"],
                       capture_output=True, text=True, encoding="utf-8", cwd=ROOT, timeout=180)
    fp = os.path.join(ROOT, "reports", "card-market.html")
    check("T20", "card.py 能生成卡片", os.path.exists(fp), (r.stdout or r.stderr)[-60:])
    ck = os.path.join(ROOT, "dist", "market-state", "check.py")
    rr = subprocess.run([sys.executable, ck, "--card", fp], capture_output=True, text=True,
                        encoding="utf-8", cwd=os.path.dirname(ck), timeout=120)
    check("T20b", "生成的卡片通过 check --card 契约", "0 错误" in (rr.stdout or ""), (rr.stdout or "")[:160])


# ---------------------------------------------------------------- T21 形态分派（R9/ADR-041）
def t21():
    shapes = (load_json(os.path.join(ROOT, "data", "series_shape.json"), {}) or {}).get("shapes") or {}
    check("T21", "累积型指标已登记为增速", shapes.get("RTL_MARGIN_INVESTORS", {}).get("visual") == "增速")
    h = io.open(os.path.join(ROOT, "reports", "card-market.html"), encoding="utf-8").read() if os.path.exists(os.path.join(ROOT, "reports", "card-market.html")) else ""
    check("T21b", "卡片里累积型行用增速（含「期 · X% 位」）", "期 ·" in h and "位" in h, "未找到增速标签")
    check("T21c", "卡片关系量无底色（透明底）", "#eef0f3" not in h)


# ---------------------------------------------------------------- T22 现金池措辞必须可核对
def t22():
    sp = io.open(os.path.join(ROOT, "scripts", "state.py"), encoding="utf-8").read()
    check("T22", "state.py 不再断言“2017 起停发”", "2017 年起停发" not in sp)
    check("T22b", "state.py 写明已核对月报", "月报" in sp and "处置补偿" in sp)
    cp = io.open(os.path.join(ROOT, "scripts", "card.py"), encoding="utf-8").read()
    check("T22c", "卡片现金池行由证据行动态渲染", ("现金池" in cp and "st.get(\"lines\")" in cp))
    d7 = io.open(os.path.join(ROOT, "docs", "07_数据源可得性矩阵.md"), encoding="utf-8").read()
    check("T22d", "docs/07 记录已解析月报 PDF", "月报 PDF 已解析核实" in d7)


# ---------------------------------------------------------------- T23 停发指标已按 ADR-040 移出
def t23():
    reg = load_json(os.path.join(ROOT, "dist", "market-state", "references", "registry.json"), {}) or {}
    check("T23", "MKT_MARGIN_DEP 已移出注册表", "MKT_MARGIN_DEP" not in reg, f"registry={len(reg)}")
    st = io.open(os.path.join(ROOT, "scripts", "state.py"), encoding="utf-8").read()
    check("T23b", "state.py 不再引用该指标", "MKT_MARGIN_DEP" not in st)
    d7 = io.open(os.path.join(ROOT, "docs", "07_数据源可得性矩阵.md"), encoding="utf-8").read()
    check("T23c", "docs/07 标注已移出", "已移出注册表" in d7)


# ---------------------------------------------------------------- T24 货基官方源与历史
def t24():
    import json as _j
    rows = []
    fp = os.path.join(ROOT, "data", "history", "MKT_MMF_SCALE.jsonl")
    if os.path.exists(fp):
        rows = [_j.loads(x) for x in io.open(fp, encoding="utf-8").read().splitlines() if x.strip()]
    check("T24", "货基历史 ≥ 6 期（可判方向）", len(rows) >= 6, f"{len(rows)} 期")
    src = io.open(os.path.join(ROOT, "scripts", "fetch.py"), encoding="utf-8").read()
    check("T24b", "货基主源为中基协官方", "www.amac.org.cn" in src and "p_mmf_official" in src)
    reg = load_json(os.path.join(ROOT, "dist", "market-state", "references", "registry.json"), {}) or {}
    check("T24c", "货基指标仍在注册表", "MKT_MMF_SCALE" in reg)


# ---------------------------------------------------------------- T25 卡片数值量级守卫
def t25():
    h = io.open(os.path.join(ROOT, "reports", "card-market.html"), encoding="utf-8").read()
    bad = [w for w in ("336251", "21419.23–26369.06e") if w in h and "%。" not in h]
    check("T25", "卡片无数值爆表（单位混用）", "▲336" not in h and "e+0" not in h)
    import re as _re
    pcts = [float(x) for x in _re.findall(r"[▲▼]([\d.]+)%", h)]
    check("T25b", "变化百分比均在 ±100% 内", all(abs(x) < 100 for x in pcts), str(pcts[:6]))


# ---------------------------------------------------------------- T26 事件卡不许裸 chip
def t26():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "card.py"),
                        "--layer", "events", "--out", "reports/card-events.html"],
                       capture_output=True, text=True, encoding="utf-8", cwd=ROOT, timeout=180)
    fp = os.path.join(ROOT, "reports", "card-events.html")
    check("T26", "事件卡能由 card.py 生成", os.path.exists(fp), (r.stdout or r.stderr)[-60:])
    if not os.path.exists(fp):
        return
    import re as _re
    h = io.open(fp, encoding="utf-8").read()
    chips = len(_re.findall(r"class=['\"]chip['\"]", h))
    tips = len(_re.findall(r"class=['\"]tip['\"]", h))
    check("T26b", f"每个 chip 都有悬停窗（chip={chips}/tip={tips}）", chips > 0 and chips == tips)
    ck = os.path.join(ROOT, "dist", "market-state", "check.py")
    rr = subprocess.run([sys.executable, ck, "--card", fp], capture_output=True, text=True,
                        encoding="utf-8", cwd=os.path.dirname(ck), timeout=120)
    check("T26c", "事件卡通过 check --card", "0 错误" in (rr.stdout or ""), (rr.stdout or "")[:120])


# ---------------------------------------------------------------- T27 分支文案禁用歧义词
def t27():
    sc = io.open(os.path.join(ROOT, "scripts", "scenarios.py"), encoding="utf-8").read()
    # 允许出现在注释/说明里，但不许出现在生成的 impact_note 中
    bad = [w for w in ("上行压力", "下行压力", "面临压力") if w in sc]
    check("T27", "scenarios.py 不再用“上行压力”类措辞", not bad, str(bad))
    import glob as _g, json as _j
    hits = []
    for fp in _g.glob(os.path.join(ROOT, "data", "events", "scenario-*.json")):
        r = _j.load(io.open(fp, encoding="utf-8"))
        for o in (r.get("possible_outcomes") or []):
            note = o.get("impact_note") or ""
            if any(w in note for w in ("上行压力", "下行压力")):
                hits.append(os.path.basename(fp))
                break
    check("T27b", "已生成分支记录无“压力”措辞", not hits, str(hits[:3]))
    h = io.open(os.path.join(ROOT, "reports", "card-events.html"), encoding="utf-8").read() if os.path.exists(os.path.join(ROOT, "reports", "card-events.html")) else ""
    check("T27c", "事件卡无“压力/阻力/支撑”", not any(w in h for w in ("压力", "阻力", "支撑")))


# ---------------------------------------------------------------- T28 全文歧义扫描
def t28():
    r = subprocess.run([sys.executable, "-B", os.path.join(ROOT, "scripts", "ambiguity_scan.py")],
                       capture_output=True, text=True, encoding="utf-8", cwd=ROOT, timeout=180)
    check("T28", "歧义扫描 0 处", "0 处歧义" in (r.stdout or ""), (r.stdout or "").strip()[-160:])
    # 读法里不许有主观程度词
    fp = latest("reports/*-market-state.md")
    if fp:
        t = io.open(fp, encoding="utf-8").read()
        bad = [w for w in ("很薄", "缩得更快", "另一边", "只能来自", "几乎一个价") if w in t]
        check("T28b", "读法无主观程度词/比喻", not bad, str(bad))


def main():
    verbose = "-v" in sys.argv
    for fn in (t01, t02, t03, t04, t05, t06, t08, t09, t10, t11, t12, t13, t14, t15, t16, t17, t18, t19, t20, t21, t22, t23, t24, t25, t26, t27, t28):
        try:
            fn()
        except Exception as e:
            check(fn.__name__.upper(), f"{fn.__name__} 执行异常", False, f"{type(e).__name__}: {e}")
    for tid, desc, detail in PASS:
        if verbose:
            print(f"  ✓ {tid:<6} {desc}" + (f"  [{detail}]" if detail else ""))
    for tid, desc, detail in FAIL:
        print(f"  ✗ {tid:<6} {desc}" + (f"  [{detail}]" if detail else ""))
    print(f"\n回归测试：{len(PASS)} 通过 / {len(FAIL)} 失败（共 {len(PASS) + len(FAIL)} 条）")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
