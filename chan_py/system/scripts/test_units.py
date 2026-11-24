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


def main():
    verbose = "-v" in sys.argv
    for fn in (unit_card_fmt, unit_card_delta, unit_card_pos_spark, unit_events_info_level,
               unit_scenarios_wording, unit_pdf_and_amac, unit_dp_of, unit_norm_period, unit_state_helpers,
               golden_checks, golden_sector_checks, facts_hygiene,
               unit_breadth_denominator, unit_snapshot_guard, unit_stale_monthly,
               unit_turnover_provider, unit_tsf_caliber, unit_event_links,
               unit_sector_c2_fresh, unit_prev_period_correct, unit_no_old_turnover_name, unit_card_series_units):
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
