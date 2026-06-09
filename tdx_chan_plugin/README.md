# TDXChanPlugin — 通达信缠论插件

C++ 通达信 DLL 插件，实现缠论技术分析：分型 → 笔 → 线段。

## 状态

所有核心模块已实施完成，编译通过，64-bit 版本稳定运行。

## 快速开始

```bash
cd tdx_chan_plugin
.\build_with_cmake.bat       # 32-bit
.\build_with_cmake64.bat     # 64-bit
# 输出: build\Release\TDXChanPlugin.dll
```

部署到通达信: 将 `TDXChanPlugin.dll` 复制到通达信 `dlls\` 目录。

在通达信公式中使用:
```
TDXDLL1(1, H, L, 0)   # 笔端点 (顶=+1, 底=-1)
TDXDLL1(2, H, L, 0)   # 线段端点 (顶=+1, 底=-1)
```

## 架构

```
原始K线 → detectGaps (缺口检测)
        → standardize (包含处理)
        → markTopBot (分型标记)
        → defineBi (笔定义)
        → defineXD → findXDOnFeatureSeq (线段检测, Plan A 合并法)
```

### 线段检测 (Plan A)

```
marked_bi (笔序列)
    │
    ▼ Phase 1: 包含处理
buildFeatureSeq   → 笔端点 → FeatureSeqElement[]
processInclusions → 按线段方向合并 (price=判断用, orig_price=端点检测用)
applyCleanSequence → 写回 working_df
    │
    ▼ Phase 2: 端点检测
findXDOnFeatureSeq → 滑动窗口 orig_price 检测线段端点
                    (缺口/K线缺口/标准XD/极值优先/前一覆盖/popGap/尾部推断)
    │
    ▼
marked_xd (线段端点)
```

### Plan A vs 旧版删除法

| | 旧版删除法 | Plan A 合并法 |
|--|-----------|----------|
| 包含处理 | 删除 (tb=NO_TOPBOT) | 合并 4→2 (price/orig_price 分离) |
| 极值保留 | chan_price 不变 | orig_price 取市场最极端 |
| XD检测 | findXDFull 交错处理 | findXDOnFeatureSeq 纯滑动窗口 |

## 文件结构

```
tdx_chan_plugin/
├── ChanPlugin.h                   # 头文件: 结构体 + 类声明
├── ChanAnalyzer.cpp               # 核心算法实现 (2049行)
├── Main.cpp                       # 通达信插件入口
├── CMakeLists.txt
├── build_with_cmake.bat
├── build_with_cmake64.bat
│
├── README.md                      # 本文件
├── ChanTheory_Compliance_Analysis.md  # 缠论合规性分析
└── TDXChanPlugin_BUGFIX_PLAN.md   # 修复记录
```

## 各模块状态

| 模块 | 核心函数 | 状态 |
|------|---------|------|
| 包含处理 | `standardize()` | 合规 |
| 分型标记 | `markTopBot()` | 合规 |
| 笔定义 | `defineBi()` | 完整算法，匹配缠论规则 |
| 线段检测 | `defineXD()` → `findXDOnFeatureSeq()` | Plan A 合并法，合规 |
| 缺口线段 | `kbarGapAsXdFull()` | 合规 |
| CRT 链接 | CMakeLists.txt `/MT` 静态链接 | 64-bit 退出正常 |
| 调用约定 | Func1/Func2 `__stdcall` | Win32 栈匹配 |

## 已知限制

| 问题 | 平台 | 状态 |
|------|------|------|
| 退出通达信时 `0xC0000005` 崩溃 | 32-bit | 未解决（不影响实际功能） |

> 日常使用推荐 64 位版本。32 位退出崩溃根因分析见 `TDXChanPlugin_BUGFIX_PLAN.md` Phase 10。
