#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单元测试 + 数值金标（golden fixture）。

与 `test_regression.py` 的分工：
  test_regression.py —— 端到端契约与历史坑（页面/卡片/三方一致/歧义）
  本文件            —— ① 纯函数单测；② **数值金标**：关键读数必须等于已核对过的值

金标文件：`tests/golden/market-<as_of>.json`
  每条记录含 `value` 与 `derivation`（怎么核对出来的），任何静默漂移都会让它失败。

用法：python -B scripts/test_units.py [-v]
退出码：0 全过 / 1 有失败。
"""
import io
import os
import sys
sys.dont_write_bytecode = True   # 自检自身不许生成 __pycache__
import json
import glob
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

PASS, FAIL = [], []


def ck(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))


def load(fp, default=None):
    try:
        with io.open(fp, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


# ---------------------------------------------------------------- 1. 纯函数
def unit_card_fmt():
    import card as C
    ck("card.fmt 百分比", C.fmt(7.1, "pct1") == "7.10%", C.fmt(7.1, "pct1"))
    ck("card.fmt 亿", C.fmt(16678.03, "yi") == "16,678 亿", C.fmt(16678.03, "yi"))
    ck("card.fmt 万亿→亿 不混", C.fmt(15.82, "wan") == "15.82 万户", C.fmt(15.82, "wan"))


def unit_card_delta():
    import card as C
    t, cls, _ = C.delta(1.40, 1.37, "pct4")
    ck("card.delta 利率用 bp", t == "▲3.0bp" and cls == "up", t)
    t2, cls2, _ = C.delta(21419.23, 21508.48, "yi")
    ck("card.delta 亿用亿元", t2.startswith("▼") and "亿" in t2 and cls2 == "dn", t2)
    t3, cls3, _ = C.delta(3.0, 3.0, "pct1")
    ck("card.delta 相等标 0", t3 == "0", t3)


def unit_card_pos_spark():
    import card as C
    ck("card.pos 升序末位=最高", C.pos_pct([1, 2, 3, 4]) == 100.0, C.pos_pct([1, 2, 3, 4]))
    ck("card.pos 降序末位=最低", C.pos_pct([4, 3, 2, 1]) == 0.0, C.pos_pct([4, 3, 2, 1]))
    ck("card.pos 单点无分位", C.pos_pct([1]) is None)
    sp = C.spark_svg([1, 2, 3])
    ck("card.spark 返回路径", isinstance(sp, tuple) and sp[0].startswith("M"), str(sp)[:40])


def unit_events_info_level():
    import events as E
    ck("events 行程类=low", E.info_level("雷平会见俄罗斯联邦卫生监督局副局长") == "low")
    ck("events 印发=high", E.info_level("工业和信息化部办公厅关于印发2026年第五批行业标准制修订项目计划的通知") == "high")
    ck("events 征求意见=high", E.info_level("关于公开征求《半导体集成电路 融合视觉传感器测试方法》意见的公示") == "high")


def unit_scenarios_wording():
    import scenarios as SC
    t = SC.impact_of("采购经理指数月度报告", "高于前值", 49.30)
    ck("scenarios 无「压力」", "压力" not in t, t[:40])
    ck("scenarios 用机械映射", "同向" in t or "同向上移" in t, t[:60])
    ck("scenarios 带不预测声明", "不预测" in t)


def unit_pdf_and_amac():
    import fetch as F
    # 两种排版都要能parse（千分位+小数点 / 小数点被吞）
    a = "货币市场基金358158,229.068158,232.061358163,168.026163,288.036"
    b = "货币市场基金358158,229068158,232061358163,168026163,288036"
    va, vb = F.amac_mmf_net(a), F.amac_mmf_net(b)
    ck("货基解析 带小数点", va and abs(va - 158232.06) < 1, str(va))
    ck("货基解析 小数点粘连", vb and abs(vb - 158232.06) < 1, str(vb))


def unit_dp_of():
    import history as H
    cases = [("2026.4", "2026-04-01"), ("2026.10", "2026-10-01"), ("2026年4月", "2026-04-01"),
             ("202604", "2026-04-01"), ("2026-04", "2026-04-01"), ("2026.12", "2026-12-01")]
    bad = []
    for raw, exp in cases:
        try:
            got = H._dp_of(raw)
        except Exception as e:
            got = f"{type(e).__name__}"
        if got != exp:
            bad.append(f"{raw}→{got}")
    ck("history._dp_of 单数字月份不丢", not bad, ";".join(bad))


def unit_norm_period():
    import fetch as F
    ck("norm_period 去时间", F.norm_period("2026-11-24 15:00:00") == "2026-11-24", F.norm_period("2026-11-24 15:00:00"))
    ck("norm_period 斜杠", F.norm_period("2026/11/24") == "2026-11-24", F.norm_period("2026/11/24"))


def unit_state_helpers():
    import state as S
    ck("_sw_sectors_of 医药=6 个二级", len(S._sw_sectors_of("医药")) == 6, len(S._sw_sectors_of("医药")))
    ck("_sw_sectors_of 半导体=1", len(S._sw_sectors_of("半导体")) == 1, len(S._sw_sectors_of("半导体")))
    ck("_prev_period 有值且早于当期", (S._prev_period("MKT_TURNOVER") or "") < (S.period("MKT_TURNOVER") or "9"), S._prev_period("MKT_TURNOVER"))


# ---------------------------------------------------------------- 2. 数值金标
def golden_checks():
    files = sorted(glob.glob(os.path.join(ROOT, "tests", "golden", "market-*.json")))
    if not files:
        return ck("金标文件存在", False, "tests/golden/market-*.json 缺失")
    g = load(files[-1], {}) or {}
    as_of = g.get("as_of")
    ck("金标 as_of 与最新状态页一致", as_of and os.path.exists(os.path.join(ROOT, "reports", f"{as_of}-market-state.md")), str(as_of))
    import state as S
    for iid, rec in (g.get("values") or {}).items():
        cur = S.val(iid)
        exp = rec.get("value")
        ok = cur is not None and exp is not None and abs(cur - exp) <= max(abs(exp) * 1e-4, 1e-6)
        ck(f"金标 {iid} = {exp}", ok, f"实际 {cur}（{rec.get('derivation','')[:28]}）")
    # 派生关系必须能由原始值复算
    for name, rec in (g.get("derived") or {}).items():
        lhs, rhs, tol = rec.get("lhs"), rec.get("rhs"), rec.get("tol", 0.02)
        got = round(lhs - rhs, 2) if rec.get("op") == "diff" else round(lhs / rhs * 100, 2)
        ck(f"金标派生 {name} = {rec.get('value')}", abs(got - rec.get("value")) <= tol, f"复算 {got}")


# ---------------------------------------------------------------- 3. facts 卫生
def facts_hygiene():
    FACTS = os.path.join(ROOT, "data", "facts")
    bad = []
    for d in glob.glob(os.path.join(FACTS, "*")):
        if not os.path.isdir(d):
            continue
        name = os.path.basename(d)
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", name):
            bad.append(f"目录名不规范 {name}")
        if not glob.glob(os.path.join(d, "*.json")):
            bad.append(f"空目录 {name}")
    ck("facts 目录规范且非空", not bad, "; ".join(bad[:3]))


# ---------------------------------------------------------------- 板块金标（独立复算）
def golden_sector_checks():
    files = sorted(glob.glob(os.path.join(ROOT, "tests", "golden", "sector-*.json")))
    if not files:
        return ck("板块金标存在", False, "tests/golden/sector-*.json 缺失")
    g = load(files[-1], {}) or {}
    total = g.get("turnover_total")
    import state as S
    for name, rec in (g.get("sectors") or {}).items():
        tot = 0
        for c in rec.get("codes") or []:
            fp_ = os.path.join(ROOT, "data", "sw", "history", f"{c}.jsonl")
            if not os.path.exists(fp_):
                continue
            rows = [json.loads(x) for x in io.open(fp_, encoding="utf-8").read().splitlines() if x.strip()]
            rows = [r for r in rows if r.get("date")]
            rows.sort(key=lambda r: r["date"])
            if rows:
                tot += rows[-1].get("amount") or 0
        ck(f"板块金标 {name} 历史成交额可复算", tot > 0, f"{tot:,.2f} 亿")
        if total:
            share = round(tot / total * 100, 2)
            ck(f"板块金标 {name} 份额 = {rec.get('share_pct_history')}%",
               abs(share - (rec.get("share_pct_history") or 0)) <= 0.02, f"复算 {share}%")
        # 面板金额与历史金额不应大幅偏离（>3% 说明两源不同步）
        pan, his = rec.get("amount") or 0, rec.get("amount_history") or 0
        if pan and his:
            ck(f"板块金标 {name} 面板/历史成交额差 ≤3%", abs(pan - his) / his <= 0.03,
               f"{abs(pan-his)/his*100:.2f}%")


# ---------------------------------------------------------------- 守卫与口径（每个 bug 一条）
def unit_breadth_denominator():
    import fetch as F
    import pandas as pd
    df = pd.DataFrame({"item": ["上涨", "下跌", "平盘", "停牌", "统计日期"],
                       "value": [1838, 3267, 114, 5, "2026-11-24 15:00:00"]})
    d, meta = F.p_breadth(df)
    ck("广度分母=涨+跌+平（剔除停牌）", d["值"] == "35.2%", d["值"])
    ck("广度对比写明三类家数", "平盘" in d["对比"] and "停牌" in d["对比"], d["对比"])


def unit_snapshot_guard():
    import fetch as F
    skip, why = F.should_skip_snapshot(15639.61, 15639.61, "akshare/ths", 16, "日")
    ck("快照同值 → 跳过（回放旧值）", skip and "回放" in why, why)
    skip2, why2 = F.should_skip_snapshot(1234.0, 1000.0, "akshare/legu", 9, "日")
    ck("盘前日频 → 跳过（盘中值）", skip2 and "盘中" in why2, why2)
    skip3, _ = F.should_skip_snapshot(1234.0, 1000.0, "akshare/ths", 16, "日")
    ck("正常快照 → 不跳过", not skip3)
    skip4, _ = F.should_skip_snapshot(3.0, 3.0, "calc", 9, "月")
    ck("非快照源不受同值限制", not skip4)


def unit_stale_monthly():
    import fetch as F
    import datetime as dt
    st, lag = F.is_stale_monthly("2025-12-01", dt.date(2026, 11, 24))
    ck("停更判定 2025-12 → 落后 11 个月", st and lag == 11, f"{st},{lag}")
    st2, _ = F.is_stale_monthly("2026-10-01", dt.date(2026, 11, 24))
    ck("当月数据不算停更", not st2)


def unit_turnover_provider():
    import fetch as F
    spec = [x for x in F.SPECS if x["id"] == "MKT_TURNOVER"][0]
    first = spec["providers"][0]
    ck("成交额主源=交易所官方", first[2] is F.p_turnover_official, str(first[0]))
    ck("成交额 official_hosts 含两所", any("sse.com.cn" in h for h in spec.get("official_hosts") or []))


def unit_tsf_caliber():
    import fetch as F
    import pandas as pd
    df = pd.DataFrame({"月份": ["202602", "202604", "202601"],
                       "社会融资规模增量": [1.0, 6245.0, 2.0]})
    d, meta = F.p_tsf(df)
    ck("社融取最新期（不是最旧）", meta["data_period"] == "2026-04-01", meta["data_period"])
    ck("社融值是增量（亿元）而非同比", "亿元" in d["值"] and "%" not in d["值"], d["值"])
    reg = load(os.path.join(ROOT, "dist", "market-state", "references", "registry.json"), {}) or {}
    ck("社融注册为 level（与源一致）", (reg.get("MKT_TSF_YOY") or {}).get("value_kind") == "level",
       str((reg.get("MKT_TSF_YOY") or {}).get("value_kind")))


def unit_event_links():
    import glob as _g
    cals = sorted(_g.glob(os.path.join(ROOT, "data", "events", "calendar-*.json")))
    if not cals:
        return ck("事件日历存在", False)
    cal = load(cals[-1], {}) or {}
    miss = [e for e in (cal.get("events") or []) if not e.get("source_link")]
    ck("每个事件都有官方链接", not miss, str([e.get("scope", "")[:16] for e in miss][:3]))


def unit_sector_c2_fresh():
    """板块 C2 份额的数据期不得落后 as-of 3 天以上（曾停在 11-13）。"""
    import glob as _g, re as _re, datetime as _dt
    fps = sorted(_g.glob(os.path.join(ROOT, "reports", "*-sector-*-state.md")))
    if not fps:
        return ck("板块页存在", False)
    t = io.open(fps[-1], encoding="utf-8").read()
    body = t.split("```")[1]
    asof = _re.search(r"as-of (\d{4}-\d{2}-\d{2})", t)
    c2 = [l for l in body.splitlines() if l.startswith("C2 ") and "份额" in l]
    if c2 and asof:
        ds = _re.findall(r"（(\d{4}-\d{2}-\d{2})", c2[0])
        if ds:
            gap = (_dt.date.fromisoformat(asof.group(1)) - _dt.date.fromisoformat(ds[0])).days
            ck("板块 C2 份额不落后 >3 天", gap <= 3, f"{ds[0]} vs as-of {asof.group(1)}")


def unit_prev_period_correct():
    """证据行的"上一期日期"必须等于 history 倒数第二期。"""
    import state as S
    for iid in ("MKT_TURNOVER", "MKT_DR007", "MKT_CGB10Y"):
        h = [x for x in S._hist(iid, 400) if x[1] is not None]
        if len(h) < 2:
            continue
        ck(f"{iid} 前值日期与 history 一致", S._prev_period(iid) == h[-2][0],
           f"{S._prev_period(iid)} vs {h[-2][0]}")


def unit_card_series_units():
    """卡片小图/位置条用的序列不得混用单位（曾出现 15.19 与 158200 混排）。"""
    import card as C
    st = C.load(os.path.join(ROOT, "reports", "state-market.json")) or {}
    bad = []
    for row in (st.get("card_rows") or []):
        iid = row.get("indicator_id")
        if not iid or not row.get("has_series"):
            continue
        vals = [x["value"] for x in C.series(iid, 60) if x.get("value") is not None]
        if len(vals) < 2:
            continue
        lo, hi = min(abs(v) for v in vals if v), max(abs(v) for v in vals if v)
        if lo and hi / lo > 50:
            bad.append(f"{iid}({lo:.4g}~{hi:.4g})")
    ck("卡片序列单位一致（量级跨度 ≤50 倍）", not bad, ";".join(bad[:3]))


def unit_no_old_turnover_name():
    h = io.open(os.path.join(ROOT, "reports", "card-market.html"), encoding="utf-8").read()
    fp = os.path.join(ROOT, "reports", "2026-11-24-market-state.md")
    t = io.open(fp, encoding="utf-8").read() if os.path.exists(fp) else ""
    ck("卡片不再叫「全市场成交额」", "全市场成交额" not in h)
    ck("证据行不再叫「行业板块成交额合计」", "行业板块成交额合计" not in t)


# ---------------------------------------------------------------- 补覆盖：降级 / 时间边界 / 事件规则 / 布局 / 指纹
def unit_network_fallback():
    """网络降级：主源抛错必须切备源，并标 fallback_flag/path（此前完全没测）。"""
    import fetch as F
    spec = {"id": "TEST_FB", "channel": "C6", "subject": "公共池", "freq": "日", "value_kind": "level",
            "layer": "市场", "tier_default": "C", "proves": "x", "does_not_prove": "y",
            "providers": [("calc", ["__boom__"], None), ("calc", ["__ok__"], None)]}

    def boom(df=None):
        raise RuntimeError("主源挂了")

    def ok(df=None):
        return ({"指标": "测试", "值": "1.00 亿元", "对比": ""}, {"data_period": "2026-11-24"})

    spec["providers"] = [("calc", ["__boom__"], boom), ("calc", ["__ok__"], ok)]

    class A:
        no_cache = True
        as_of = None
    old = dict(F.SPEC_MAP)
    try:
        F.SPEC_MAP["TEST_FB"] = spec
        res = F.fetch_one(spec, A(), None)
        ck("降级：主源失败会切备源", bool(res.get("fallback_flag")), str(res.get("fallback_path")))
        ck("降级：仍能产出当期值", "current_state" in res)
    except Exception as e:
        ck("降级：主源失败会切备源", False, f"{type(e).__name__}: {e}")
    finally:
        F.SPEC_MAP.clear(); F.SPEC_MAP.update(old)
        # 测试用的假指标会写 cache，必须清掉（否则污染 T18/deep_audit）
        cf = os.path.join(ROOT, "data", "cache", "TEST_FB.json")
        if os.path.exists(cf):
            os.remove(cf)


def unit_time_edges():
    """时间边界：盘中/收盘、周末、停更阈值、跨月。"""
    import fetch as F
    import datetime as dt
    sk14, _ = F.should_skip_snapshot(1.0, 2.0, "akshare/legu", 14, "日")
    sk15, _ = F.should_skip_snapshot(1.0, 2.0, "akshare/legu", 15, "日")
    ck("盘中边界：14:59 跳过 / 15:00 不跳过", sk14 and not sk15, f"{sk14},{sk15}")
    st3, lag3 = F.is_stale_monthly("2026-08-01", dt.date(2026, 11, 24))
    st4, lag4 = F.is_stale_monthly("2026-07-01", dt.date(2026, 11, 24))
    ck("停更阈值：3 个月不判停更、4 个月判", (not st3) and st4 and lag3 == 3 and lag4 == 4, f"{lag3},{lag4}")
    ck("月末跨月解析", F.norm_period("2026-12-31") == "2026-12-31", F.norm_period("2026-12-31"))


def unit_event_rules():
    """事件规则：信息含量分级、窗口过滤、同日去重。"""
    import events as E
    ck("信息含量：行程类=low", E.info_level("雷平会见俄罗斯联邦卫生监督局副局长") == "low")
    ck("信息含量：印发类=high", E.info_level("工业和信息化部办公厅关于印发2026年第五批行业标准制修订项目计划的通知") == "high")
    cals = sorted(glob.glob(os.path.join(ROOT, "data", "events", "calendar-*.json")))
    if cals:
        cal = load(cals[-1], {}) or {}
        as_of = cal.get("as_of") or ""
        horizon = cal.get("horizon_days") or 40
        import datetime as dt
        end = (dt.date.fromisoformat(as_of) + dt.timedelta(days=horizon)).isoformat()
        fut = [e for e in (cal.get("events") or []) if e.get("event_status") == "未来预定"]
        out_win = [e for e in fut if not (as_of <= (e.get("event_date") or "") <= end)]
        ck("事件窗口内（as_of ~ horizon）", not out_win, str([e.get("event_date") for e in out_win][:3]))
        keys = [(e.get("event_date"), (e.get("scope") or "")) for e in (cal.get("events") or [])]
        dup = [k for k in set(keys) if keys.count(k) > 1]
        ck("事件已去重（日期+标题唯一）", not dup, str(dup[:2]))


def unit_layout_fill():
    """布局：网格必须弹性填满，小图必须 100%（曾经定宽 96px 导致右侧空档）。"""
    h = io.open(os.path.join(ROOT, "reports", "card-market.html"), encoding="utf-8").read()
    import re as _re
    g = _re.search(r"\.g\{[^}]*grid-template-columns:([^;}]+)", h)
    m = _re.search(r"\.mini\{[^}]*width:([^;}]+)", h)
    ck("网格列宽含 fr（随卡片缩放）", bool(g) and "fr" in g.group(1), g.group(1)[:40] if g else "无")
    ck("小图容器 width:100%", bool(m) and m.group(1).strip() == "100%", m.group(1).strip() if m else "无")


def unit_shape_fingerprint():
    """快照型源的 facts 必须有 shape 指纹（源改版靠它发现）。"""
    import glob as _g, json as _j
    snap = {"akshare/ths", "akshare/legu"}
    miss = []
    for fp in _g.glob(os.path.join(ROOT, "data", "facts", "*", "*.json")):
        r = _j.load(io.open(fp, encoding="utf-8"))
        if r.get("source") in snap and not r.get("shape"):
            miss.append(r.get("indicator_id"))
    ck("快照源 facts 带 shape 指纹", not miss, str(sorted(set(miss))[:3]))


def unit_cli_variants():
    """CLI 组合：--no-events / --show-history / --policy strict 都必须能跑。"""
    import subprocess as _sp
    for args, expect in (
        (["--layer", "market", "--no-events", "--json"], '"lines"'),
        (["--show-history"], "已归档快照"),
        (["--layer", "market", "--policy", "strict", "--json"], '"lines"'),
    ):
        r = _sp.run([sys.executable, "-B", os.path.join(ROOT, "scripts", "state.py")] + args,
                    capture_output=True, text=True, encoding="utf-8", cwd=ROOT, timeout=180)
        ck(f"CLI {' '.join(args[:2])} 可运行", expect in (r.stdout or ""), (r.stderr or "")[-50:])


# ---------------------------------------------------------------- R8 事件分支↔六环
def unit_event_ring_attribution():
    """每个事件类型必须能给出环归属（或显式"不映射"），不许静默消失。"""
    import card as C
    rules = C.EVENT_RINGS
    for et in ("政策会议", "逆回购到期", "公开市场操作", "解禁", "新股发行", "财报披露", "数据发布"):
        ck(f"环归属规则已登记：{et}", et in rules, str(list(rules)[:3]))
    ck("逆回购 → C3", "C3" in (rules.get("逆回购到期") or {}).get("rings", []))
    ck("政策会议 → C1", "C1" in (rules.get("政策会议") or {}).get("rings", []))
    ck("解禁 → 不映射（显式空）", (rules.get("解禁") or {}).get("rings") == [])
    # 数据发布按 affected_indicators 的 channel
    import glob as _g, json as _j
    fs = _g.glob(os.path.join(ROOT, "data", "events", "scenario-*.json"))
    if fs:
        scen = _j.load(io.open(fs[0], encoding="utf-8"))
        ev = {"event_type": "数据发布", "scope": scen.get("event_summary", "")}
        hit, rule = C.rings_of_event(ev, scen)
        ck("数据发布的环由指标通道决定", bool(hit), f"{sorted(hit)} / {rule}")


def unit_event_ring_strip():
    """R8 环条：6 环 + 背景齐全、命中环加粗、圆点只标分支不标方向色。"""
    import card as C
    import glob as _g, json as _j
    h = io.open(os.path.join(ROOT, "reports", "card-events.html"), encoding="utf-8").read()
    chips = len(__import__("re").findall(r"class='chip'", h))
    rrs = len(__import__("re").findall(r'class="rr"', h))
    ck("每个事件格都有环条", chips == rrs and chips > 0, f"chip={chips} rr={rrs}")
    blk = __import__("re").findall(r'<div class="rr">(.*?)</div>', h)
    if blk:
        ck("环条含 C1–C6 与背景", all(x in blk[0] for x in ("C1", "C2", "C3", "C4", "C5", "C6", "背景")), blk[0][:40])
    bad = [b for b in blk if ("#d03050" in b or "#2477b3" in b)]
    ck("环条无红蓝（R8 硬规则）", not bad, str(bad[:1])[:60])
    # 有分支的事件应出现圆点（● ○ ◌）
    dotted = [b for b in blk if any(ch in b for ch in "●○◌")]
    ck("数据发布事件环条带分支圆点", bool(dotted), f"{len(dotted)} 个")


# ---------------------------------------------------------------- 市场卡格式定死
def unit_market_card_format_frozen():
    """格式指纹必须等于 tests/golden/card-format.json。

    想改格式：改 data/card_spec.json → 重生成卡 → 更新 golden → 升版本（三处一起，缺一即失败）。
    """
    import re as _re, json as _j
    h = io.open(os.path.join(ROOT, "reports", "card-market.html"), encoding="utf-8").read()
    g = load(os.path.join(ROOT, "tests", "golden", "card-format.json"), {}) or {}
    spec = load(os.path.join(ROOT, "data", "card_spec.json"), {}) or {}
    ck("格式定稿版本存在", bool(spec.get("version")), str(spec.get("version")))
    ck("卡与定稿版本一致", g.get("spec_version") == spec.get("version"),
       f"golden={g.get('spec_version')} spec={spec.get('version')}")
    rings = [list(x) for x in _re.findall(r'<div class="gh"><b>(C\d)</b>([^<]+)<', h)]
    ck("环顺序与定稿一致", rings == [list(x) for x in (g.get("ring_order") or [])], str([r[0] for r in rings]))
    labels = [_l.strip() for _l in _re.findall(r'<div class="nm(?: rel)?">([^<]+?)(?: <b>|</div>)', h) if _l.strip()]
    ck("行顺序与定稿一致", labels == (g.get("row_labels") or []), f"{len(labels)} 行")
    grid = _re.search(r"\.g\{[^}]*grid-template-columns:([^;}]+)", h)
    ck("网格列宽与定稿一致", bool(grid) and grid.group(1).strip() == g.get("grid"),
       (grid.group(1)[:50] if grid else "无"))
    mini = _re.search(r"\.mini\{[^}]*width:([^;}]+)", h)
    ck("小图宽度与定稿一致", bool(mini) and mini.group(1).strip() == g.get("mini_width"),
       mini.group(1).strip() if mini else "无")
    fonts = sorted({float(x) for x in _re.findall(r"font(?:-size)?:\s*([\d.]+)px", h)})
    ck("字号集合与定稿一致", fonts == (g.get("fonts") or []), str(fonts))
    ck("行数=定稿行数", len(labels) == len(g.get("row_labels") or []), f"{len(labels)}")
    # 小图高度 / 进度条高度（曾只改常量没改 golden）
    vb = _re.search(r'viewBox="0 0 100 (\d+)"', h)
    ck("小图高度与定稿一致", bool(vb) and int(vb.group(1)) == int(g.get("line_h") or 0),
       vb.group(1) if vb else "无")
    bar = _re.search(r"\.pbar\{[^}]*height:(\d+)px", h)
    ck("位置条高度与定稿一致", bool(bar) and int(bar.group(1)) == int(g.get("bar_h") or 0),
       bar.group(1) if bar else "无")


# ---------------------------------------------------------------- 解禁显示阈值（V2.137.0）
def unit_unlock_threshold():
    import event_rules as R
    th = R.thresholds()
    ck("解禁阈值已登记（绝对值）", th.get("unlock_abs_yi") == 200.0, str(th))
    ck("解禁阈值已登记（相对成交额）", th.get("unlock_pct_of_turnover") == 1.0, str(th))
    tx = 16585.24
    ok1, mv1, r1 = R.unlock_passes("限售解禁：1 家，解禁市值 298.7 亿", tx)
    ok2, mv2, r2 = R.unlock_passes("限售解禁：5 家，解禁市值 7.2 亿", tx)
    ck("298.7 亿 → 显示", ok1 and mv1 == 298.7)
    ck("7.2 亿 → 折叠", not ok2 and mv2 == 7.2)
    ok3, _, _ = R.unlock_passes("限售解禁：1 家，解禁市值 200.0 亿", tx)
    ck("边界 200 亿 → 显示", ok3)
    ok4, _, _ = R.unlock_passes("限售解禁：9 家，解禁市值 150.0 亿", tx)
    ck("150 亿（0.9% 成交）→ 折叠", not ok4)
    # 无市值的事件不做过滤（宁可显示，不静默）
    ok5, mv5, _ = R.unlock_passes("限售解禁：3 家", tx)
    ck("取不到市值 → 不折叠", ok5 and mv5 is None)


def unit_unlock_card_folded():
    """卡上不得出现低于阈值的解禁；且必须写出折叠条数。"""
    import re as _re, event_rules as R
    h = io.open(os.path.join(ROOT, "reports", "card-events.html"), encoding="utf-8").read()
    lim = R.thresholds()["unlock_abs_yi"]
    low = []
    for m in _re.finditer(r"解禁[^<]*?(\d+(?:\.\d+)?)\s*亿", h):
        try:
            v = float(m.group(1))
        except Exception:
            continue
        if v < lim:
            low.append(v)
    ck(f"卡片无 <{lim:.0f} 亿解禁", not low, str(low[:3]))
    ck("卡片写出折叠条数", "折叠" in h and "解禁" in h)


def unit_event_tips_nonempty():
    """每个事件格的悬停窗必须有内容（防"格子有、悬浮空白"）。"""
    import re as _re
    h = io.open(os.path.join(ROOT, "reports", "card-events.html"), encoding="utf-8").read()
    blocks = _re.findall(r"<div class='ev'>(.*?)</div></div>", h, _re.S)
    ck("事件格数量 > 0", len(blocks) > 0, str(len(blocks)))
    no_tip = [b for b in blocks if 'class="tip"' not in b]
    ck("每格都有悬停窗", not no_tip, f"{len(no_tip)} 个缺失")
    short = []
    for b in blocks:
        if 'class="tip"' not in b:
            continue
        txt = _re.sub(r"<[^>]+>", "", b.split('class="tip"', 1)[1]).strip()
        if len(txt) < 10:
            short.append(txt[:12])
    ck("悬停窗都有实际内容（≥10 字）", not short, str(short[:3]))
    # 悬停窗里必须带日期与来源，便于核对
    ck("悬停窗含日期", all(_re.search(r"20\d{2}-\d{2}-\d{2}", b) for b in blocks if 'class="tip"' in b))


def main():
    verbose = "-v" in sys.argv
    for fn in (unit_card_fmt, unit_card_delta, unit_card_pos_spark, unit_events_info_level,
               unit_scenarios_wording, unit_pdf_and_amac, unit_dp_of, unit_norm_period, unit_state_helpers,
               golden_checks, golden_sector_checks, facts_hygiene,
               unit_breadth_denominator, unit_snapshot_guard, unit_stale_monthly,
               unit_turnover_provider, unit_tsf_caliber, unit_event_links,
               unit_sector_c2_fresh, unit_prev_period_correct, unit_no_old_turnover_name, unit_card_series_units,
               unit_network_fallback, unit_time_edges, unit_event_rules,
               unit_layout_fill, unit_shape_fingerprint, unit_cli_variants, unit_event_ring_attribution, unit_event_ring_strip, unit_market_card_format_frozen, unit_unlock_threshold, unit_unlock_card_folded, unit_event_tips_nonempty):
        try:
            fn()
        except Exception as e:
            ck(fn.__name__, False, f"{type(e).__name__}: {e}")
    if verbose:
        for n, d in PASS:
            print(f"  ✓ {n}" + (f"  [{d}]" if d else ""))
    for n, d in FAIL:
        print(f"  ✗ {n}" + (f"  [{d}]" if d else ""))
    print(f"\n单元测试：{len(PASS)} 通过 / {len(FAIL)} 失败（共 {len(PASS) + len(FAIL)} 条）")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
