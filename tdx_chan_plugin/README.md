# TDXChanPlugin — 通达信缠论插件

C++ 通达信 DLL 插件，实现缠论技术分析：分型 → 笔 → 线段。

## 快速开始

```bash
cd tdx_chan_plugin
.\build_with_cmake.bat
# 输出: build\Release\TDXChanPlugin.dll
```

部署到通达信: 将 `TDXChanPlugin.dll` 复制到通达信 `dlls\` 目录。

## 架构

```
原始K线 → standardize (包含处理) → markTopBot (分型) → defineBi (笔) → defineXD (线段)
```

### 数据流 (线段检测，Plan A 版)

```
marked_bi (笔序列)
    │
    ▼ Phase 1: 包含处理
buildFeatureSeq   → bi 端点 → FeatureSeqElement[]
processInclusions → 按方向合并 (price=判断用, orig_price=端点检测用)
applyCleanSequence → 写回 working_df
    │
    ▼ Phase 2: 端点检测
findXDOnFeatureSeq → 滑动窗口 orig_price 检测 XD 端点
                    (缺口 / K线缺口 / 标准XD / 前一覆盖 / popGap / 尾部推断)
    │
    ▼
marked_xd (线段端点)
```

### 核心改进 (Plan A, 2026-04-26)

从旧版的"删除被包含元素"重构为"按缠论原文规则合并"：

| | 旧版删除法 | 新版合并法 |
|--|-----------|----------|
| 包含处理 | 删除 (tb=NO_TOPBOT) | 合并 4→2 (price/orig_price 分离) |
| 极值保留 | chan_price 不变 (弱TOP可能存活) | orig_price 始终取市场最极端 |
| XD检测 | findXDFull 交错处理 | findXDOnFeatureSeq 纯滑动窗口 |
| 缠论一致性 | 删除 ≠ 原文合并要求 | 合并 = 原文规则 |

## 文件结构

```
tdx_chan_plugin/
├── ChanPlugin.h          # 头文件: 结构体 + 类声明
├── ChanAnalyzer.cpp      # 核心算法实现
├── Main.cpp              # 通达信插件入口
├── CMakeLists.txt
├── build_with_cmake.bat
│
├── README.md                              # 本文件(总体说明)
├── ChanTheory_Compliance_Analysis.md       # 专精: 缠论合规性分析
├── DEFINEBI_REWRITE_PLAN.md               # 专精: defineBi 重写方案(待实施)
└── TDXChanPlugin_BUGFIX_PLAN.md           # 专精: Bug修复历史
```

## 各模块状态

### 已实施 ✅

| 模块 | 函数 | 状态 |
|------|------|------|
| 包含处理 | `standardize()` | 合规 |
| 分型标记 | `markTopBot()` | 合规 |
| 笔定义 | `defineBi()` | 基本可用 (见 DEFINEBI_REWRITE_PLAN) |
| 线段检测 | `defineXD()` → `findXDOnFeatureSeq()` | Plan A 已实施, 合规 |
| 缺口线段 | `kbarGapAsXdFull()` | 保留, 合规 |

### 计划中

| 模块 | 说明 | 文档 |
|------|------|------|
| defineBi 完善 | 三段去除 / 回溯 / 缺口条件 / 方向一致性 | DEFINEBI_REWRITE_PLAN.md |

## 文档导航

| 你想了解... | 看这个文档 |
|------------|-----------|
| 实现与缠论原文的对应关系 | `ChanTheory_Compliance_Analysis.md` |
| 曾经修过哪些 Bug | `TDXChanPlugin_BUGFIX_PLAN.md` |
| defineBi 还有什么待完善 | `DEFINEBI_REWRITE_PLAN.md` |
