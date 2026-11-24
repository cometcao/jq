#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""歧义扫描：把"可能有两种读法"的表述拦在输出之前。

背景：2026-11-24 用户指出「10Y 上行压力」既能读成"有力量推高"、也能读成"上方遇阻"——
一句话两种相反含义，等于没写。此后把可枚举的歧义词做成清单，机械扫描。

扫描对象：
  reports/<最新>-market-state.md、reports/<最新>-sector-*-state.md
  reports/card-market.html、reports/card-events.html
  data/events/scenario-*.json（分支影响文案）

规则：
  A. 禁用词（任何位置出现即违规）
  B. "上一期 / 前值" 必须在同一行内带日期或具体数值（否则读者不知道跟哪天比）
  C. 方向词必须带机械映射（同向/上移/下移），不得用"压力/阻力/支撑"

用法：python scripts/ambiguity_scan.py [-v]
退出码：0 = 干净；1 = 有歧义。
"""
import io
import os
import re
import sys
import glob
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A. 禁用词 → 替代写法
BANNED = {
    "压力": "改为「同向上移/同向下移 + 不预测落点」",
    "阻力": "改为数值比较（x > 前值）或「区间高低」",
    "支撑": "改为数值比较或「区间高低」",
    "通常": "改为「按登记规则」（说明这是规则映射，不是常态判断）",
    "明显": "给不出阈值 → 写具体数值或删掉",
    "显著": "给不出阈值 → 写具体数值或删掉",
    "大致": "写确切数值",
    "大约": "写确切数值",
    "左右": "写确切数值",
    "预计": "不做预测",
    "有望": "不做预测",
    "应该": "不做预测/判断",
    "可能": "不猜概率；要写就写条件分支",
    "流入": "对手方叙事 → 写「净买额」「余额增减」",
    "流出": "对手方叙事 → 写「净卖额」「余额增减」",
    "主力": "无定义 → 写具体口径（大单/龙虎榜/两融）",
    "前者": "指代不明 → 重写指标全名",
    "后者": "指代不明 → 重写指标全名",
    "该指标": "指代不明 → 重写指标全名",
    "该口径": "指代不明 → 重写口径名",
    "近期": "写具体区间",
    "目前": "写具体数据期",
}

# B. 需要日期/数值伴随的关系词
NEED_DATE = ["上一期", "前值"]


def scan_text(name, text):
    bad = []
    clean = re.sub(r"<style.*?</style>", "", text, flags=re.S)
    clean = re.sub(r"<script.*?</script>", "", clean, flags=re.S)
    # 页面里的"禁用词说明"（自检清单、元信息）不算违规：只在证据行/卡片正文里查
    for w, why in BANNED.items():
        for m in re.finditer(w, clean):
            s = max(0, m.start() - 45)
            ctx = re.sub(r"\s+", " ", clean[s:m.start() + 45])
            # 白名单：出现在"不等于/不是/不说明"等否定句里，或本身就是规则文本
            if any(k in ctx for k in ("不等于", "不是", "不说明", "禁止", "改为", "不得")):
                continue
            # 固定声明段与机械比较式属合法用法
            if "no_prediction_statement" in ctx or "不预测哪个分支" in ctx or "不排序可能性" in ctx:
                continue
            bad.append((name, w, why, ctx))
    for w in NEED_DATE:
        for m in re.finditer(w, clean):
            line_start = clean.rfind("\n", 0, m.start()) + 1
            line_end = clean.find("\n", m.start())
            line = clean[line_start: line_end if line_end > 0 else len(clean)]
            seg = line[max(0, m.start() - line_start - 20): m.start() - line_start + 80]
            if "公布值" in seg or "高于前值" in seg or "没有变化" in seg or "前值不可得" in seg:
                continue          # 机械比较式（规则要求的写法）
            if not re.search(r"20\d{2}-\d{2}-\d{2}|\d", line[max(0, m.start() - line_start): m.start() - line_start + 60]):
                bad.append((name, w, "后面必须跟日期或数值", re.sub(r"\s+", " ", line[:110])))
    return bad


def latest(pattern):
    fs = sorted(glob.glob(os.path.join(ROOT, pattern)))
    return fs[-1] if fs else None


def main():
    verbose = "-v" in sys.argv
    targets = []
    # 只扫**最新**报告（历史归档不改，避免把旧输出当现存问题）
    for pat in ("reports/*-market-state.md", "reports/*-sector-*-state.md"):
        fs = sorted(glob.glob(os.path.join(ROOT, pat)))
        if fs:
            targets.append(fs[-1])
    for name in ("card-market.html", "card-events.html"):
        fp = os.path.join(ROOT, "reports", name)
        if os.path.exists(fp):
            targets.append(fp)
    for fp in glob.glob(os.path.join(ROOT, "data", "events", "scenario-*.json")):
        targets.append(fp)

    allbad = []
    for fp in targets:
        try:
            text = io.open(fp, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        allbad += scan_text(os.path.relpath(fp, ROOT), text)

    if not allbad:
        print(f"歧义扫描：{len(targets)} 个文件，0 处歧义")
        return 0
    print(f"歧义扫描：{len(targets)} 个文件，{len(allbad)} 处可疑表述")
    seen = set()
    for name, w, why, ctx in allbad:
        key = (name, w)
        if key in seen and not verbose:
            continue
        seen.add(key)
        print(f"  ✗ {w:<6} {why}")
        print(f"      {name}: …{ctx}…")
    print("\n处理：按提示改成机械表述；确属否定语境的，确认上下文含「不等于/不说明」即可放行。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
