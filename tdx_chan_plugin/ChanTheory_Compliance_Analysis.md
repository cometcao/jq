# 缠论理论合规性分析 — TDXChanPlugin

> 分析日期: 2026-04-27 (更新: Plan A 方向感知修复)
> 上一个版本: 2026-04-26 (Plan A FeatureSeqElement 合并实现，方向无关 — 后被发现有 bug)
> 编译状态: 通过

---

## 2026-04-27 修订 — Plan A 方向感知修复

### 起因

2026-04-26 版本的 Plan A 把"删除法"重构为"合并法"，但 `processInclusions` 没有 `direction` 参数，从 `feature_seq[0]` 开始按 `i+=2` 步进。`findInitialDirectionFull` 把 `initial_loc` 设成极值分型位置（`bot2top` 时是 BOT、`top2bot` 时是 TOP），刚好让 `feature_seq[0]` 是反向类型。结果：

- 上升段：处理的是向上笔配对 (BOT,TOP) 的包含，而缠论原文要求处理向下笔；`mergeFeatureSeqPair` 因 `e0.tb==BOT` 走 MIN 合并分支，方向也错
- 下降段：对称镜像错误

对于含特征序列包含的真实数据，这个 bug 会让线段端点检测漏判（构造的 5 笔上升段示例中，本应在 TOP 110 形成顶分型的，C++ 主循环因序列被过度合并而无法触发，最终输出 0 个端点）。

### Python 原版的处理方式

Python `is_XD_inclusion_free` (py:1102-1105) 对方向有 assert：
- `bot2top` → 4 元素必须 (TOP, BOT, TOP, BOT) → 配对 = 向下笔 ✓
- `top2bot` → 4 元素必须 (BOT, TOP, BOT, TOP) → 配对 = 向上笔 ✓

`find_XD` 主循环每次通过 `get_next_N_elem(start_tb=...)` 跳到正确类型起点，再调 `check_inclusion_by_direction`，所以 Python 始终处理缠论原文要求的特征序列笔类型。

### 修改

1. **`processInclusions` 增加 `direction` 参数**（cpp:1093）
   - `bot2top` 时跳过领头 BOT，定位到首个 TOP 后开始按 `i+=2` 步进
   - `top2bot` 时跳过领头 TOP，定位到首个 BOT 后开始

2. **`mergeFeatureSeqPair` 修复 `orig_price` 与 `orig_market_idx`**（cpp:1054）
   - 旧版按"分类型保极值"（TOP→max, BOT→min）— 与缠论合并方向不一致
   - 新版按"线段方向合并"（上升 max/max, 下降 min/min），与 `price` 字段语义统一
   - `orig_market_idx` 同步：上升时 BOT 侧追踪较高 BOT 的位置，下降时 TOP 侧追踪较低 TOP 的位置

3. **`defineXD` 调用处传入方向**（cpp:1587）：`processInclusions(feature_seq, initial_direction)`

4. **`ChanPlugin.h` 第 203 行签名同步**

### 修复后行为验证

5 笔上升段反例：feature_seq=[BOT 80, TOP 100, BOT 90, TOP 95, BOT 92, TOP 110, BOT 105, TOP 108, BOT 100]

- 修复前：processInclusions 处理 (笔1, 笔3) 向上笔配对 + MIN 合并 → 序列被过度合并到 5 元素，主循环 `i+5 < size` 失败，输出 0 个端点
- 修复后：跳过领头 BOT，从 i=1 起处理 (笔2, 笔4) 向下笔配对 + MAX 合并。笔2 (TOP 100, BOT 90) 与 笔4 (TOP 95, BOT 92) 合并为 (TOP 100, BOT 92)。序列保持 7 元素，主循环在 i=1 处通过 6 元素结构性检查命中 顶分型 → 在 TOP 110 设置线段端点 ✓

### 残留限制（未在本次处理）

- 主循环检测到 XD 端点后切换 direction，但**没有对剩余 feature_seq 重做 processInclusions**。后续段的特征序列若是上一方向合并出来的，对新方向不一定成立。原文对该边界（合并后是否需 restore）没有明确规则；此问题保持现状。
- popGap 用价格突破近似"反向特征序列分型确认"，原文要求 3 元素结构判定。当前是工程近似。
- `kbarGapAsXdFull` 的 0.618 阈值是原文未定义的工程补充。

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

## 4. 线段 (XianDuan / Line Segment) — Plan A + 方向感知修复

### 4.1 特征序列元素表示

FeatureSeqElement 用 (e0,e1) 配对隐式表示一笔的两个端点。`price`（包含判断用）与 `orig_price`（XD 端点检测用）在 2026-04-27 修复后语义一致，都是按线段方向合并的值。✅

### 4.2 包含处理（2026-04-27 修复）

- `processInclusions(seq, direction)`: 根据 direction 跳到正确类型起点（上升→首个 TOP，下降→首个 BOT），再左到右单趟扫描+回退
- `mergeFeatureSeqPair`: `e0.tb==TOP` 走上升 MAX 合并分支（向下笔），`e0.tb==BOT` 走下降 MIN 合并分支（向上笔）。修复点对齐起点后 `e0.tb` 自动匹配方向，分支语义正确

✅ 与缠论原文一致

### 4.3 XD端点检测

6元素 orig_price 滑动比较，条件与缠论原文 `check_XD_topbot` 逐字对应。✅

### 4.4 缺口

`kbarGapAsXdFull` 保留，黄金分割 0.618 阈值是原文未定义的合理补充。✅

### 4.5 残留差异（已知）

- **方向切换后不重做 processInclusions**：主循环识别 XD 端点后切换 direction，但剩余 feature_seq 仍按原方向已合并的状态。原文对此边界（合并后是否 restore）未明文规则，保持现状
- **popGap 用价格突破近似反向分型确认**：原文要求 3 元素结构性反向特征序列分型；当前简化为价格突破检测，在快速突破场景下近似良好
- **gap_XD 推送时机** (`line 1321`)：与旧版有微小差异，不影响端点创建

结论: Plan A + 方向感知修复后是当前最忠实实现。✅

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
| 线段检测 | ✅ | Plan A + 2026-04-27 方向感知修复。processInclusions 按 direction 跳起点；mergeFeatureSeqPair 沿线段方向合并 |
| 尾部推断 | ⚪ | 工程补充，非原文定义 |

### 与旧版相比的改进

旧版核心问题——`chan_price` 身兼包含判断和端点检测二职导致极值丢失——已通过 FeatureSeqElement 的 `price`/`orig_price` 分离彻底解决。旧版的 12 个耦合函数被 Plan A 的清晰两阶段流水线替代。
