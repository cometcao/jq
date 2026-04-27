# 缠论理论合规性分析 — TDXChanPlugin

> 分析日期: 2026-04-26 (更新: Plan A FeatureSeqElement 合并实现)
> 上一个版本: 2026-04-25 (旧版删除法)
> 编译状态: 通过

---

## 概要变更 (Plan A)

2026-04-26 实施了 FeatureSeqElement 合并方案（Plan A），将线段检测的核心从"删除法"重构为"合并法"：

| 维度 | 旧版 (删除法) | 新版 (合并法) |
|------|-------------|-------------|
| 包含处理 | 删除被包含元素 (tb=NO_TOPBOT) | 按方向合并 4→2 (price/orig_price 分离) |
| 价格来源 | chan_price 身兼二职 | price=包含判断, orig_price=端点检测 |
| XD 检测 | findXDFull 交错处理 | findXDOnFeatureSeq 纯滑动窗口 |
| 与原文一致性 | 删除 ≠ 原文"合并" | 合并 = 原文规则 |

---

## 背景: 为何需要 FeatureSeqElement

### merge_price 方案为何失败

最初尝试在 `StandardKLine` 上新增 `merge_price` 字段做包含判断，保留 `chan_price` 做端点检测。方案在理论上正确但实践上失败，根本原因：

```
E0=TOP 100, E1=BOT 90, E2=TOP 105, E3=BOT 88, E4=TOP 103, E5=BOT 91
```

1. 第一轮包含 E1,E2 被删，E0 存活，`E0.merge_price = max(100,105) = 105`
2. 下一轮: `105>103 且 90<91 → 包含` → E4,E5 被吞
3. 层层叠加后，留给端点检测的 6 个元素凑不齐，端点无法形成

更致命的是：端点检测用 `chan_price`，被删的 E2 的 `chan_price=105` 永久丢失，存活的 E0 的 `chan_price` 只有 100。**patch 方案无法解决——需要在数据结构层面重新设计特征序列元素的表示方式。**

### FeatureSeqElement 如何解决

引入独立对象，不复用 `StandardKLine`：

```cpp
struct FeatureSeqElement {
    TopBotType tb;              // TOP or BOT
    double price;               // 包含判断用: 方向合并值 (向上max, 向下min)
    double orig_price;          // XD端点检测用: 原始市场极端价格
    int orig_market_idx;        // 指向 working_df 中原始 K 线索引
    bool is_merged;
};
```

核心：`price` 和 `orig_price` 属于**同一个合并实体**，不分散在两个跨位置的 StandardKLine 上。

- `price` = 方向合并值，用于包含判断。向上全 max，向下全 min (与 K 线包含规则一致)
- `orig_price` = 所有参与合并的原始元素中，最极端的市场价。TOP 取最高原始 high，BOT 取最低原始 low。永远不丢失市场极值

> 旧版用 StandardKLine 跨位置删除表示合并——E0(TOP 100) 和 E3(BOT 88) 分别代理合并后的 TOP 和 BOT。E0 的 chan_price=100 是弱的 TOP，真正的高点 E2(105) 已被删除。
> FeatureSeqElement 用一个对象持有完整信息：`merged_top.orig_price = max(100,105) = 105`。

| 矛盾点 | merge_price patch | FeatureSeqElement |
|--------|-------------------|-------------------|
| 合并后 TOP 价格低于被删元素 | chan_price 仍是弱值 → 极值丢失 | orig_price = 最高/最低 → 不丢失 |
| 多轮合并叠加 | price 增强 → 吞噬 → 雪崩 | price 用于包含；每一轮正确 |
| 数据结构分散 | TOP/BOT 代理在不同对象 | 一个实体持完整信息 |
| 包含+端点分离 | 耦合在 findXDFull 循环 | processInclusions / findXDOnFeatureSeq 两阶段 |

---

## 1. 包含处理 (K-line Inclusion Processing)

### 缠论规则
相邻两根K线包含 → 按趋势方向合并：向上 max(high,low)、向下 min(high,low)。方向由前两根非包含K线决定。

### 实现: `standardize()`

| 方面 | 状态 |
|------|------|
| 合并方向判断 | ✅ `isBullType` 确定 BOT2TOP/TOP2BOT |
| 合并操作符 | ✅ BOT2TOP→max, TOP2BOT→min |
| 链式合并 | ✅ 合并后继续与下一根比较 |
| 被合并元素清除 | ✅ high=low=0 |
| 趋势方向复用 | ✅ 存储在 K 线的 `tb`/`original_tb`，后续迭代复用 |

### 差异

1. **`isBullType` 仅比较 high** (`ChanAnalyzer.cpp:56-58`): 缠论原文要求同时比较两根K线的 high 和 low 来确定方向。`isBullType` 仅用 `first.high < second.high → BOT2TOP` 做判断。由于调用时 `past` 和 `first` 已被确认无包含关系，high 和 low 应同向变动，实践中不会出错，但与原文规则略有简化。

2. **初始状态包含处理** (`line 150-168`): 当 `initial_state` 指定时合并非标准（只推一侧）。仅影响前两根K线，无实际影响。

**结论**: 合规。✅

---

## 2. 分型 (FenXing / Top-Bottom Pattern)

### 缠论规则
每3根非包含K线，中间 highest 为顶分型、中间 lowest 为底分型。分型之间不共用K线。同类型连续分型取极值（顶取最高，底取最低）。

### 实现: `markTopBot()` + `cleanFirstTwoTB()`

| 方面 | 状态 |
|------|------|
| 顶分型 | ✅ `float_more(first.high, current.high) && float_more(first.high, second.high)` |
| 底分型 | ✅ `float_less(first.low, current.low) && float_less(first.low, second.low)` |
| 首尾标记 | ✅ 首分型反推、尾分型取反 |
| 同类型清理 | ✅ `cleanFirstTwoTB` 保留极值 |

### 差异

**分型检测阶段允许K线共用** (`line 280-290`): `markTopBot` 循环 `for (i = 0; i < size-2; i++)` 每次 `i++`，两轮相邻迭代检测的分型可以共用 K 线：

```
i=0: current=std[0], first=std[1], second=std[2] → std[1].tb = TOP
i=1: current=std[1], first=std[2], second=std[3] → std[2].tb = BOT

TOP 分型 = {std[0], std[1], std[2]}
BOT 分型 = {std[1], std[2], std[3]}
           ^^^^^^ ^^^^^^ 两个分型共用这两根K线
```

缠论原文要求分型之间K线不可重叠。但此处在 markTopBot 阶段不阻止重叠，而将此问题推迟到 `defineBi` 阶段统一清理——`cleanFirstTwoTB` 处理同类型重叠，Case C（line 616-807）处理跨类型重叠。

**结论**: markTopBot 阶段允许重叠，但 defineBi 通过清理逻辑消除了后果。最终 `marked_bi` 输出的笔序列合规。✅

---

## 3. 笔 (Bi / Pen)

### 缠论规则
顶底交替。至少1根独立K线 (`new_index >= 4`)。顶high > 底low。同向取极值。

### 实现: `defineBi()`

| 方面 | 状态 |
|------|------|
| 同类型合并 (Case A/B) | ✅ 保留极值 |
| 距离检查 (`new_index >= 4`) | ✅ |
| 价格有效性 | ✅ Case C 检查 |
| 末端处理 | ✅ `work_on_end` |
| 回溯机制 | ✅ `trace_back_index` |

### 差异

**Case C 逻辑过度复杂** (`line 616-807`): 约200行代码处理「前一笔距离不足、但下一笔可能有效」的各种子情况。此复杂度源于 `markTopBot` 阶段 K 线共用在 defineBi 中引发的拓扑异常——若分型检测阶段强制不重叠，Case C 的大多数子条件将不再触发。当前通过清理逻辑消除后果，最终笔序列合规。

**结论**: 功能合规。复杂性来自上游问题。✅

---

## 4. 线段 (XianDuan / Line Segment) — Plan A 重写

### 4.1 特征序列元素表示

旧版用跨位置的 StandardKLine 代理合并对→新版用独立的 FeatureSeqElement (price+orig_price 同体)。✅

### 4.2 包含处理

`mergeFeatureSeqPair`: e0.tb 定方向 (TOP→TOP2BOT, BOT→BOT2TOP), 操作符与K线包含一致。`processInclusions`: 左到右单趟+回退。✅

### 4.3 XD端点检测

6元素 orig_price 滑动比较，条件与缠论原文逐字对应。✅

### 4.4 缺口

`kbarGapAsXdFull` 保留，黄金分割 0.618 阈值是原文未定义的合理补充。✅

### 差异

**kline gap XD 的 gap_XD 推送** (`line 1321`): 当 kline gap 直接构成 XD 端点时，新版始终推入 `gap_XD`，旧版不推入 (旧版 `wcg = !with_kline_gap`)。差异仅影响后续 popGap 回退的触发时机，不影响端点创建。属于工程差异。

结论: Plan A 是缠论最忠实实现。✅

---

## 5. 尾部推断

### 缠论规则
缠论原文没有对数据末尾的未完成线段给出明确的推断规则。

### 实现: `findXDOnFeatureSeq` 尾部 (line 1430-1528)

使用启发式规则: 收集剩余元素的 price 信息，按方向判断最后端点。逻辑与旧版 `findXDFull` 尾部等价。

### 差异
此为工程补充，非缠论原文定义。对实时行情尾部处理有实际价值，但不存在"合规/不合规"的判定基础。

结论: 合理工程补充。⚪

---

## 6. 汇总

| 模块 | 状态 | 说明 |
|------|------|------|
| K线包含 | ✅ | `isBullType` 仅比较 high（非 high+low），实践中无影响 |
| 分型标记 | ✅ | markTopBot 允许K线共用但 defineBi 后续清理，最终笔输出合规 |
| 笔定义 | ✅ | 合规。Case C 复杂性来自上游分型阶段 |
| 线段检测 | ✅ | Plan A — 缠论最忠实实现。price/orig_price 分离 |
| 尾部推断 | ⚪ | 工程补充，非原文定义 |

### 与旧版相比的改进

旧版核心问题——`chan_price` 身兼包含判断和端点检测二职导致极值丢失——已通过 FeatureSeqElement 的 `price`/`orig_price` 分离彻底解决。旧版的 12 个耦合函数被 Plan A 的清晰两阶段流水线替代。
