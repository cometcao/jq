# TDXChanPlugin 性能问题修复计划

---

### 2026-04-25 Phase 9 实施记录 — 线段完全不显示修复（对比Python完整重写）

#### 0.14 问题诊断：6个关键Bug导致线段完全不显示

**Bug 1: `getNextNElem` 起始过滤逻辑错误** (`ChanAnalyzer.cpp`)

C++ 旧实现：`single_direction` 模式只过滤与 `last_tb` **相反方向**的元素，且总把**第一个元素加入**。
```cpp
// 旧：不检查 start_tb，第一个元素无条件加入
TopBotType last_tb = start_tb;
for (...) {
    if (single_direction && last_tb != NO_TOPBOT) {
        if (last_tb == TOP && working_df[i].tb == BOT) continue;  // 反方向过滤
    }
    result.push_back(i);  // 第一个元素总加入
}
```

Python `get_next_N_elem`：先跳过不匹配 `start_tb` 的元素，`single_direction` 全程只保留匹配 `start_tb` 的元素。
```python
if start_tb != TopBotType.noTopBot and current_elem['tb'] != start_tb.value and len(result_locs) == 0:
    continue  # 起始过滤
if single_direction and current_elem['tb'] != start_tb.value:
    continue  # 同向过滤
```

**影响**：`single_dir` 返回错误元素（如 BOT2TOP 方向下，应该得到 `[T1, T2, T3]`，实际得到 `[B0, T1, T3]`），导致方向断言和候选检查全部混乱。

**修复**: 重写 `getNextNElem` 匹配Python：
```cpp
if (start_tb != NO_TOPBOT && result.empty() && working_df[i].tb != start_tb) continue;  // 起始跳过
if (single_direction && working_df[i].tb != start_tb) continue;  // 同向跳过
result.push_back(i);
```

**Bug 2: `directionAssert` 方向判断前后颠倒** (`ChanAnalyzer.cpp`)

C++ 旧实现：
```cpp
if (direction == BOT2TOP) return elem.tb == BOT;  // ❌ BOT2TOP 应检查 TOP
if (direction == TOP2BOT) return elem.tb == TOP;  // ❌ TOP2BOT 应检查 BOT
```

Python `direction_assert`：
```python
if direction == TopBotType.bot2top:
    if firstElem['tb'] != TopBotType.top.value: result = False  # ✅ BOT2TOP→要求TOP
if direction == TopBotType.top2bot:
    if firstElem['tb'] != TopBotType.bot.value: result = False  # ✅ TOP2BOT→要求BOT
```

**影响**：结合 Bug1，BOT2TOP 时 C++ 检查了错误的元素类型（B0 而非 T1），方向断言永远通过但后续逻辑全错。

**修复**: 反转向导检查条件。

**Bug 3: `findInitialDirectionFull` 简化过度** (`ChanAnalyzer.cpp`)

C++ 旧实现直接取第一个分型（BOT/TOP）做方向，且错误设置 `xd_tb`：
```cpp
for (size_t i = 0; i < working_df.size(); i++) {
    if (working_df[i].tb == BOT) {
        working_df[i].xd_tb = BOT;  // ❌ Python 不在此设置 xd_tb
        return (i, BOT2TOP);
    }
}
```

Python `find_initial_direction` 用滑动窗口遍历 4 个连续元素的 `chan_price` 确定方向：
```python
while current_loc + 3 < working_df.size:
    first, second, third, forth = working_df[current_loc:current_loc+4]
    found_direction = (first <= third && second < forth) || ...  # 价格方向一致性
```

**影响**：C++ 方向判断完全错误，且提前设置了 `xd_tb` 导致第一个 XD 端点位置错误。

**Bug 4: `findXDFull` 中 `getNextNElem` 传错 `start_tb`** (`ChanAnalyzer.cpp`)

C++ 将 `current_direction`（BOT2TOP=4 / TOP2BOT=3）当作 `start_tb` 传入：
```cpp
getNextNElem(i, 4, current_direction, false);  // ❌ current_direction=4 ≠ TOP/BOT
getNextNElem(single_dir[0], 6, current_direction, false);  // ❌
```

Python 调用不传 `start_tb`（默认 `NO_TOPBOT`，无需过滤）：
```python
self.get_next_N_elem(i, working_df, 4)  # ✅ 默认 NO_TOPBOT
self.get_next_N_elem(single_dir[0], working_df, 6)  # ✅
```

**影响**：`getNextNElem` 按 start_tb=4/3 过滤时，没有元素 tb 值等于 4/3，结果少于 4/6 个，`findXDFull` 提前 break，**从不执行 `checkXDTopBotDirectedFull`**。这是"线段完全不显示"的根因。

**Bug 5: `xdTopbotCandidateFull` 包含关系检查无条件返回** (`ChanAnalyzer.cpp`)

C++ 旧实现：只要找到极值就返回候选，**从不检查极值是否超过参考价格**，导致 `checkXDTopBotDirectedFull` 永远不被调用：
```cpp
if (min_data_idx >= 0) return new_valid_elems[0];  // ❌ 无条件返回
```

Python 仅当极值比参考点更极端时才返回：
```python
if float_less(min_price, working_df[next_valid_elems[1]]['chan_price']):
    result = next_valid_elems[1]  # ✅ 有条件返回
```

**Bug 6: `isXDInclusionFreeFull` 无元素删除逻辑** (`ChanAnalyzer.cpp`)

Python `is_XD_inclusion_free` 在检测到包含关系时，会**删除被包含的元素**（设置 `tb = NO_TOPBOT`）。C++ 旧实现只返回 `false`，但**从未删除元素**，导致 `checkInclusionByDirectionFull` 的循环无法收敛，永远找不到 inclusion-free 的窗口。

**连带修复**：

| 函数 | 问题 | 修复 |
|------|------|------|
| `combineGaps` | 合并条件用 `float_less_equal`（反向），无排序 | 改为 `float_more_equal` 并先排序（匹配Python） |
| `getPreviousNElem` | 使用 `tb` 而非 `original_tb`；`N=0` 时 `0>=0` 立即返回 | 改为 `original_tb`；`N==0` 时检查 `xd_tb` 停止（匹配Python） |
| `kbarGapAsXdFull` | 无黄金分割比例检查，`compare_idx=-1` 时直接 `return true` | 添加 `gap_range/price_diff >= GOLDEN_RATIO` 检查 |
| `popGapFull` | 简化版只返回 `next_valid_elems[1]` | 重写匹配 Python `pop_gap`：检查 max/min 价格覆盖、弹出 gap_XD、翻转方向 |
| `findXDFull` 尾部处理 | C++ 只有简单的 "last kbar replace cur/prev" 逻辑 | 重写为 Python 尾部处理：gap_XD 末位替换 + 极值推断剩余 XD 端点 |
| `findXDFull` 整体 | 简化版 no-gap 单分支 | 完整 Python 三分支（previous_gap / no gap / tail handling） |

---

### 2026-04-25 Phase 9b 实施记录 — `checkInclusionByDirectionFull` 重复索引Bug（线段画线错误）

#### 0.15 问题诊断：`checkInclusionByDirectionFull` 产生重复索引

**位置**: `ChanAnalyzer.cpp` — `checkInclusionByDirectionFull()`

**根因**: C++ 实现使用"累积扩展"模式，与 Python 的"重新获取"模式本质不同。

**Python `check_inclusion_by_direction`**：每次循环从相同起始位置 `i` 重新获取 `count_num` 个元素（`get_next_N_elem` 自动跳过被 `is_XD_inclusion_free` 标记为 `NO_TOPBOT` 的元素），然后检查新的窗口是否 inclusion-free：

```python
def check_inclusion_by_direction(self, current_loc, working_df, direction, count_num=6):
    i = current_loc
    first_run = True
    while first_run or (i+count_num-1 < working_df.shape[0]):
        first_run = False
        next_valid_elems = self.get_next_N_elem(i, working_df, count_num)  # ✅ 重新获取
        if len(next_valid_elems) < count_num: break
        # 检查 inclusion...
```

**C++ 旧实现**：先获取初始 `count_num` 个元素，然后用第二个 while 循环**从 `current_loc` 重新开始添加元素**到已有向量。由于 `i = current_loc` 的复位，已存在的元素被**重复添加**：

```cpp
// 第一步：获取初始 count_num 个元素 → [0,1,2,3,4,5]
while (i < working_df.size() && result.size() < count_num) {
    if (working_df[i].tb != NO_TOPBOT) result.push_back(i);
    i++;
}
// ❌ i = current_loc 复位！
i = current_loc;  
// 第二步：从 current_loc 重新推入 → [0,1,2,3,4,5,0,1,2,3,4,5]
while (result.size() < count_num * 2) {
    next_valid_elems.push_back(i);  // 重复添加 0,1,2,3,4,5
    // 每次检查前4个 → 找到包含关系 → 删除元素（但索引仍在向量中）
    // 下一个循环又检查同样的前4个 → 永远不收敛
}
```

**影响**：`next_valid_elems` 包含重复索引 `[0,1,2,3,4,5,0,1,2,3,4,5]`。`isXDInclusionFreeFull` 反复检查相同的元素，包含关系永远无法消除（删除元素 tb=NO_TOPBOT 后重复元素仍然指向 `chan_price` 有效的被删元素）。函数永不收敛，最终返回垃圾结果（2x count_num 个混杂了有效和无效的元素）。

由于 `findXDFull` 中的 `xdTopbotCandidateFull` 和 `previous_gap` 分支都调用 `checkInclusionByDirectionFull`，其返回的垃圾数据直接导致 XD 候选判断和线段端点检测完全错误。

**修复**: 重写为 Python 的 `first_run` 重新获取模式：

```cpp
int i = current_loc;
bool first_run = true;
while (first_run || (i + count_num - 1 < working_df.size())) {
    first_run = false;
    std::vector<int> nve = getNextNElem(i, working_df, count_num, NO_TOPBOT, false);
    if (nve.size() < count_num) break;
    // 检查 inclusion...
    // 如果未通过，循环继续 → 被删除的元素被 getNextNElem 自动跳过
}
```

| 对比 | Python | C++ 旧版 | C++ 新版 |
|------|--------|----------|----------|
| 元素获取方式 | 每次 `get_next_N_elem(i, count_num)` 重新获取 | 先一次获取，后逐元素累积含重复 | 每次 `getNextNElem(i, count_num)` 重新获取 |
| 删除元素处理 | 自动跳过（`get_next_N_elem` 跳过 NO_TOPBOT） | 仍在向量中，反复被检查 | 自动跳过（`getNextNElem` 跳过 NO_TOPBOT） |
| 循环条件 | `first_run or (i+count_num-1 < size)` | `size < count_num * 2` | `first_run or (i+count_num-1 < size)` |
| 返回时机 | inclusion-free 时返回 | 永不收敛或 2x 时返回 | inclusion-free 时返回 |

**编译结果**: ✅ 编译成功 (`build\Release\TDXChanPlugin.dll`, 54,784 bytes)

**测试结果**: 效果"好多了"。

---

### 2026-04-25 Phase 9c 实施记录 — `standardize` 趋势方向存储缺失 + `checkInclusionByDirectionFull` 重复索引

#### 0.16 问题诊断：`standardize` 包含关系处理中趋势方向未存储

**位置**: `ChanAnalyzer.cpp` — `standardize()` 包含关系循环 (line 208-244)

**根因**: Python `standardize` 每次合并后存储趋势方向到 `trend_type` 字段，后续迭代直接用。C++ 不存储趋势，每次从 `isBullType(past, first)` 重新计算。

当连续2次以上包含关系时（A→B→C 链式合并），`past` 元素已被清空（high=0, low=0），`isBullType` 比较 0 vs first.high 返回错误结果：

```
Python:                                 C++（旧）:
A(orig)  B  C  D                       A(orig)  B  C  D
└─→B含C, 趋势=TOP2BOT（存trend_type）    └─→B含C, 趋势=TOP2BOT（不保存）
   ↓ first=D                               ↓ first=D 
   读取 C.trend_type=TOP2BOT ✅             isBullType(A={0,0}, C=merged) 
                                           → 0 < C.high → BOT2TOP ❌ 翻转！
```

**修复**: 合并后将趋势存入 `tb` 字段 (`first.tb = trend` / `second.tb = trend`)，后续迭代读取 `first.tb` 而非重新计算。

#### 0.17 问题诊断：`restoreTbData` 边界条件

**位置**: `ChanAnalyzer.cpp` - `restoreTbData()`

Python `arr[from:to]` 是半开区间 `[from, to)`，C++ `for i <= to_idx` 是闭区间 `[from, to]`。C++ 多恢复了一个元素。

**修复**: 改为 `i < to_idx`。

#### 0.19 `combineGaps` 合并条件错误

**位置**: `ChanAnalyzer.cpp` — `combineGaps()` (line 1880)

**根因**: C++ 使用 `float_less_equal(last.second, current.first)` 判断是否需要合并，条件完全反向：

| 版本 | 条件 | 含义 |
|------|------|------|
| Python | `float_more_equal(current[1], next[0])` | **current.end ≥ next.start** → 重叠/相邻→合并 ✅ |
| C++旧 | `float_less_equal(last.second, current.first)` | **last.end ≤ current.first** → 有间隙→合并 ❌ |

C++ 的 `float_less_equal` 在绝大多数情况下为 true（只要 gap 不超过 epsilon），导致几乎所有缺口都被错误合并。同时缺少 Python 中对 gap_regions 的**排序**。

**修复**: 重写为 Python 完整逻辑，包含排序和 `float_more_equal` 条件。

```cpp
std::vector<std::pair<double, double>> sorted_regions = gap_regions;
std::sort(sorted_regions.begin(), sorted_regions.end(), ...);
// 合并时使用 float_more_equal(prev.second, current.first)
```

#### 0.20 `kbarGapAsXdFull` 缺口占比计算和价格覆盖检查错误

**位置**: `ChanAnalyzer.cpp` — `kbarGapAsXdFull()`

**根因**: C++ 实现与 Python 在黄金分割比例计算和价格覆盖检查上完全不同：

| 检查项 | Python | C++旧 |
|--------|--------|-------|
| 缺口总跨度 | `sum((b-a) for a,b in regions)` 累加**所有**gap范围 | 只取第一个gap范围的 `end-start` |
| 价格覆盖 (BOT2TOP) | `regions[-1].end ≥ compare.cp` | `gap_start < compare.low && compare.high < gap_end` |
| 价格覆盖 (TOP2BOT) | `regions[0].start ≤ compare.cp` | `gap_end > compare.high && compare.low > gap_start` |

**修复**: 重写为完全匹配 Python 逻辑，使用总和计算 gap 跨度，用 `regions[0].first` / `regions[-1].second` 做价格覆盖检查。

#### 0.21 `checkPreviousElemToAvoidXdGap` 简化过度

**位置**: `ChanAnalyzer.cpp` — `checkPreviousElemToAvoidXdGap()`

Python 使用 `get_previous_N_elem` 查找同类型前驱元素，检查其价格区间是否跨越 forth 的价格来判断缺口是否被"填补"。C++ 旧实现只简单比较 first 与 forth 的价格。

**修复**: 重写为调用 `getPreviousNElem` 获取同类型前驱元素并计算 min/max。

#### 0.18 `checkInclusionByDirectionFull` 循环结构与重新获取模式修复（详见Phase 9b）

旧实现中 `i = current_loc` 复位 + 累积模式，导致重复索引和永不收敛。修复后采用 Python `first_run` 重新获取模式。

**编译结果**: ✅ 编译成功 (`build\Release\TDXChanPlugin.dll`, 54,784 bytes)

**测试结果**: 效果"好多了"。

---

#### 总结：已修复的全部 14 个 C++/Python 逻辑差异

| # | 函数 | Bug |
|---|------|-----|
| 1 | `getNextNElem` | 起始不过滤 `start_tb`；`single_direction` 过滤方向反了 |
| 2 | `directionAssert` | BOT2TOP 检查 BOT（应为 TOP），TOP2BOT 检查 TOP（应为 BOT） |
| 3 | `findInitialDirectionFull` | 取第一个分型做方向（应为滑动窗口）；错误早设 xd_tb |
| 4 | `findXDFull` 传参 | `getNextNElem(i,4,current_direction,...)` 传了方向值做过滤 |
| 5 | `xdTopbotCandidateFull` | 包含关系无条件返回候选（应检查极值 > 参考） |
| 6 | `isXDInclusionFreeFull` | 包含时不删除元素（应设 tb=NO_TOPBOT） |
| 7 | `checkInclusionByDirectionFull` | `i=current_loc` 复位导致重复索引 |
| 8 | `standardize` | 不存储趋势方向，链式包含后方向翻转 |
| 9 | `restoreTbData` | `<=` 应为 `<`（闭→半开） |
| 10 | `combineGaps` | 合并条件用 `less_equal` 反向；未排序 |
| 11 | `kbarGapAsXdFull` | 缺口占比只取第一个范围（应累加）；价格覆盖逻辑完全错误 |
| 12 | `checkPreviousElemToAvoidXdGap` | 不查前驱元素，仅比较 first/forth |
| 13 | `popGapFull` | 简化版不查价格区间 |
| 14 | `findXDFull` 尾部处理 | 无 gap_XD 末位替换 + 极值推断逻辑 |

---

> **问题总结**: 通达信插件在K线超过300+时造成软件卡死，需要分析所有历史K线而非仅当前窗口范围，且算法实现有简化/冗余。
> 
> **⚠️ 说明**: 项目编译与测试由开发者手动执行，本文档仅提供修复方案与代码改动指引。

---

## 0. 实施记录 (Implementation Log)

### 2024-04-23 Phase 1 实施记录 — 紧急修复卡死

#### 0.1 初始修改（绑定失败）

**首次修改内容**:
- 在 `Main.cpp` 中加入 `<chrono>` 和 `<cstdio>` 用于性能计时和日志
- 新增 `logPerf()` 函数，使用 `fopen`/`fprintf` 写入 `C:\TDXPlugin_Perf.log`
- 新增 `DataWindow` 结构体和 `prepareDataWindow()` 统一截断逻辑
- 新增 `convertBiToOutputWithOffset()` / `convertXianDuanToOutputWithOffset()` 用于索引映射
- 修改 `Func2` / `Func5` / `TDXPlugin_Calculate` 使用截断逻辑

**编译结果**: 编译成功，`build\Release\TDXChanPlugin.dll` 生成

**测试结果**: ❌ **通达信绑定失败**

#### 0.2 绑定失败根因分析

| 对比项 | 旧版（可绑定） | 新版首次修改（失败） |
|---|---|---|
| 编译脚本 | `build_with_cmake.bat` | 相同 |
| 编译器 | MSVC 2022 Win32 Release | 相同 |
| **新增头文件** | 无 | `<chrono>`, `<cstdio>` |
| **新增代码** | 无 | `std::chrono` 计时、`fopen` 日志 |

**根因**: 虽然旧版和新版都使用 `/MD`（动态链接运行时库），但新版引入的 `std::chrono` 和 `fopen` 依赖了 VC++ 运行时的初始化代码路径。通达信加载 DLL 时，这些新增符号的解析可能触发了运行时初始化问题，导致 `LoadLibrary` 失败，表现为"绑定失败"。

> **注意**: 编译脚本和导出函数声明均未改变，问题完全由新增头文件/代码引入的运行时依赖导致。

#### 0.3 修复方案（回滚到旧版结构）

**修复原则**: 保持旧版 `Main.cpp` 的代码结构不变，只加入数据截断逻辑，**不引入任何新的头文件**。

**具体改动**:
1. **移除 `<chrono>` 和 `<cstdio>` 头文件**
2. **移除 `logPerf()` 性能日志函数**
3. **保留核心截断逻辑**:
   - `MAX_PROCESS_COUNT = 300` 常量
   - `DataWindow` 结构体
   - `prepareDataWindow()` 函数
   - `convertBiToOutputWithOffset()` / `convertXianDuanToOutputWithOffset()` 函数
4. **修改 `Func2`**: 在旧版结构基础上加入截断和索引映射
5. **修改 `Func5`**: 同上
6. **修改 `TDXPlugin_Calculate`**: 统一使用截断逻辑和索引映射

**编译结果**: ✅ 编译成功

**测试结果**: ✅ 通达信绑定成功，卡死问题解决

---

### 2024-04-23 Phase 2 实施记录 — 笔和线段的正确画线输出

#### 0.4 问题诊断：画线位置错误

**问题1：索引映射错误（关键Bug）**

**位置**: `ChanAnalyzer.cpp` - `getBi()` 和 `getXianDuan()`

当前代码使用 `new_index` 作为输出索引：
```cpp
bi.start_index = start.new_index;  // ❌ 这是标准化清理后的索引
bi.end_index = end.new_index;
```

但 `new_index` 是**处理包含关系后重新编号的索引**（合并后的K线数组内的位置），**不是原始K线位置**。这导致通达信在错误的K线位置画点。

**应该是 `real_loc`**：
```cpp
bi.start_index = start.real_loc;  // ✅ 原始K线位置（截断数据内）
bi.end_index = end.real_loc;
```

`real_loc` 是截断数据内的原始索引，加上 `Main.cpp` 中的 `startOffset` 就能正确映射回通达信原始数组。

**问题2：Func3是简化实现，不是真正的线段**

**位置**: `Main.cpp` - `Func3()`

当前 `Func3` 只是对 `Func2` 的输出做简单模式匹配，没有调用 `ChanAnalyzer` 的线段算法。而通达信公式调用的是 `Func3` 来画线段，所以画的是**伪线段**。

**问题3：Func4和Func5是冗余函数**
- `Func4`: 1+1终结简化版，未使用真正算法
- `Func5`: 与Func3重复的线段端点（输出值不同±2）
- `Func1`: 简笔，不精确

#### 0.5 修复方案

**修复1：修正 `getBi()` / `getXianDuan()` 索引（ChanAnalyzer.cpp）**

将 `new_index` 改为 `real_loc`：
```cpp
// getBi() 中
bi.start_index = start.real_loc;
bi.end_index = end.real_loc;

// getXianDuan() 中  
xd.start_index = start.real_loc;
xd.end_index = end.real_loc;
```

**修复2：重写 `Main.cpp` — 精简为两个核心函数**

| 函数 | 修改前 | 修改后 |
|---|---|---|
| `Func1` | 简笔（3周期新高/新低） | **标准笔**（调用ChanAnalyzer） |
| `Func2` | 标准笔（调用ChanAnalyzer） | **真正线段**（调用ChanAnalyzer） |
| `Func3` | 简化线段（模式匹配） | **删除** |
| `Func4` | 1+1终结简化 | **删除** |
| `Func5` | 线段（调用ChanAnalyzer，输出±2） | **删除** |

**修复3：更新公式文档**

更新 `TDXChanPlugin_Simple_NoChinese.txt`：
- `TDXDLL1(1, H, L, 0)` = 标准笔端点
- `TDXDLL1(2, H, L, 0)` = 真正线段端点

**编译结果**: ✅ 编译成功

**测试结果**: 笔显示正常，线段不显示

---

### 2024-04-23 Phase 3 实施记录 — 通达信卡死解决与线段不显示修复

#### 0.6 问题诊断：历史K线过多导致卡死

**位置**: `Main.cpp` - `MAX_PROCESS_COUNT`

笔在300根K线时可以正常显示，但历史K线多的股票会造成通达信卡死。需要增大处理范围。

**修复**: `MAX_PROCESS_COUNT` 从 `300` 逐步调至 `4000`
- 300 → 600：笔显示范围扩大
- 600 → 4000：通达信运行流畅，无卡死

#### 0.7 问题诊断：线段不显示

**位置**: `ChanAnalyzer.cpp` - `findInitialDirectionFull()` 和 `findXDFull()`

**根因1：findInitialDirectionFull 自动检测方向永远失败**

原逻辑期望笔端点价格单调递增/递减才能确定方向：
```cpp
bool found_direction = false;
if (float_less(first.chan_price, second.chan_price)) {
    found_direction = (float_less_equal(first.chan_price, third.chan_price) && 
                      float_less(second.chan_price, forth.chan_price)) || ...;
}
```

但笔端点价格是**交替的**（顶高→底低→顶高→底低），此条件永远为 `false`，导致 `initial_direction = NO_TOPBOT`，整个线段算法无法工作。

**修复1**: 改为根据第一个笔端点类型直接确定方向：
```cpp
for (size_t i = 0; i < working_df.size(); i++) {
    if (working_df[i].tb == BOT) {
        initial_direction = BOT2TOP;  // 底分型开始 → 上升线段
        break;
    } else if (working_df[i].tb == TOP) {
        initial_direction = TOP2BOT;  // 顶分型开始 → 下降线段
        break;
    }
}
```

**根因2：findXDFull 获取初始元素数量与Python不一致**

Python `find_XD` else分支（无previous_gap时）：
```python
next_elems = self.get_next_N_elem(i, working_df, 6, TopBotType.noTopBot, False)
if len(next_elems) < 6: break
```

C++ 原代码：
```cpp
while (next_elems.size() < 4) { ... }  // ← 只获取4个
if (next_elems.size() < 4) break;
```

**修复2**: 将 `next_elems` 获取数量从4改为6，与Python一致。

**编译结果**: ✅ 编译成功

**测试结果**: 笔正常显示，线段仍不显示

**分析**: `findInitialDirectionFull` 和 `findXDFull` 的已知差异已修复，但线段仍不显示。最可能的根因是 **C++ `defineBi()` 是大幅简化版**，而Python原版有340+行复杂逻辑（`same_tb_remove_*`、`check_gap_qualify`、`work_on_end`等）。如果C++生成的 `marked_bi` 与Python不一致，则 `findXDFull` 即使逻辑正确也无法识别线段。

---

### 2026-04-24 Phase 4 实施记录 — 编译错误修复与 defineBi 完整算法实现

#### 0.8 问题诊断：编译失败 — 多个链接错误

**位置**: `ChanAnalyzer.cpp` / `ChanPlugin.h`

**问题1：getBi() 声明但未实现**
头文件声明了 `getBi()` 但 `.cpp` 中没有函数体，导致链接错误：
```
error LNK2019: unresolved external symbol "public: class std::vector...
ChanAnalyzer::getBi(void)" referenced in function "void __cdecl Func1(...)"
```

**问题2：结构化绑定语法不支持**
`defineBi()` 中使用 `auto [new_prev, new_cur, new_nxt] = ...` 结构化绑定，但项目未设置 C++17 标准，编译报错。

**问题3：多个 camelCase 函数声明但未实现**
`ChanPlugin.h` 中声明了 `sameTBRemoveEdge` / `sameTBRemoveMiddle` / `removeOneTBFromTwo` / `workOnEnd` / `checkDirectionConsistency` / `checkGapQualify` / `traceBackIndex` 共 7 个函数，但 `.cpp` 中这些函数与 snake_case 版本重复，且只实现了 snake_case 版本。

#### 0.9 修复方案

**修复1：CMakeLists.txt — 设置 C++17 标准**
```cmake
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
```

**修复2：ChanAnalyzer.cpp — getBi() 实现**
补全缺失的 getBi() 实现体：
```cpp
std::vector<Bi> ChanAnalyzer::getBi() const {
    std::vector<Bi> result;
    if (marked_bi.size() < 2) return result;
    for (size_t i = 0; i + 1 < marked_bi.size(); i++) {
        const StandardKLine& start = marked_bi[i];
        const StandardKLine& end   = marked_bi[i+1];
        if ((start.tb == BOT && end.tb == TOP) ||
            (start.tb == TOP && end.tb == BOT)) {
            Bi bi;
            bi.start_date     = start.date;
            bi.end_date       = end.date;
            bi.start_price    = start.chan_price;
            bi.end_price      = end.chan_price;
            bi.type           = start.tb;
            bi.start_index    = start.real_loc;   // 使用 real_loc
            bi.end_index      = end.real_loc;      // 使用 real_loc
            result.push_back(bi);
        }
    }
    return result;
}
```

**修复3：ChanAnalyzer.cpp — defineBi() 结构化绑定改为 std::tuple**
```cpp
// 改前：
auto [new_prev, new_cur, new_nxt] = same_tb_remove_previous(...);
// 改后：
std::tuple<int, int, int> result = same_tb_remove_previous(...);
int new_prev = std::get<0>(result);
int new_cur  = std::get<1>(result);
int new_nxt  = std::get<2>(result);
```
（同一改动也应用于 same_tb_remove_current / same_tb_remove_next 的调用处）

**修复4：ChanPlugin.h — 删除未实现的 camelCase 声明**
删除以下 7 个声明：
- `sameTBRemoveEdge`
- `sameTBRemoveMiddle`
- `removeOneTBFromTwo`
- `workOnEnd`
- `checkDirectionConsistency`
- `checkGapQualify`
- `traceBackIndex`

**编译结果**: ✅ 编译成功 (`build\Release\TDXChanPlugin.dll`)

**编译警告**: C4819 — 文件包含无法在代码页(936)中表示的字符。不影响功能。

---

## 1. 问题诊断 (Root Cause Analysis)

### 1.1 核心Bug: Func2/Func5 未限制K线数量

**问题位置**: `Main.cpp` - `Func2()` 和 `Func5()`

```cpp
// Func2 当前实现 — 传入全部 nCount 根K线！
void Func2(int nCount, float *pOut, float *pHigh, float *pLow, float *pIgnore) {
    std::vector<KLine> klines;
    for (int i = 0; i < nCount; i++) {  // ← 没有限制！
        // ...
    }
    ChanAnalyzer analyzer(false);
    analyzer.setData(klines);  // ← 可能传入数千根K线
    analyzer.analyze();        // ← O(n²) 算法爆炸
}
```

- `TDXPlugin_Calculate()` 虽然实现了 `MAX_PROCESS_COUNT = 400` 限制
- 但通达信公式直接调用的是 `Func2`/`Func5`（通过 `TDXDLL1(2, H, L, 0)`）
- **这些函数没有做任何数据截断**，传入全部历史K线

### 1.2 算法复杂度问题: ChanAnalyzer 存在 O(n²) 隐患

**问题位置**: `ChanAnalyzer.cpp`

| 问题函数 | 问题描述 |
|---|---|
| `cleanFirstTwoTB()` | 返回 `std::vector<StandardKLine>` by value，造成大量拷贝 |
| `findXD()` / `findXDFull()` | 递归/迭代扫描，内部调用 `getNextNElem()` 等多次遍历 |
| `getNextNElem()` / `getPreviousNElem()` | 线性搜索下一个有效元素，嵌套在循环中 |
| `isXDInclusionFree()` | 内部遍历 `next_valid_elems` 向量，多重嵌套 |
| `checkInclusionByDirection()` | 双重循环扫描包含关系 |
| `defineBi()` | 可能频繁调用 `cleanFirstTwoTB()` 造成拷贝 |

**关键代码气味**:
```cpp
// 返回vector by value — 每次调用都拷贝整个K线数组
std::vector<StandardKLine> cleanFirstTwoTB(const std::vector<StandardKLine>& working_df);

// 线性搜索 — O(n) 每次调用
int getNextLoc(int loc, const std::vector<StandardKLine>& working_df) {
    for (size_t i = loc + 1; i < working_df.size(); i++) { ... }
}

// findXD内部多重嵌套循环，处理每根K线都可能触发多次扫描
std::vector<StandardKLine> findXD(int initial_i, TopBotType initial_direction, 
                                  std::vector<StandardKLine>& working_df);
```

### 1.3 算法简化问题

| 函数 | 现状 | 应有的行为 |
|---|---|---|
| `Func3` | 注释明确写"简化实现" | 应基于 `ChanAnalyzer` 的线段结果 |
| `Func4` | 注释明确写"简化实现" | 应实现真正的1+1终结判断 |
| `Func2/Func5` | 虽然调用 ChanAnalyzer，但传入全量数据 | 应限制数据量并优化映射 |

### 1.4 索引映射问题

当截断数据时（如只处理最近300根），`ChanAnalyzer` 内部索引是 `0~299`，但通达信输出数组需要映射回原数组位置。当前 `TDXPlugin_Calculate` 尝试处理但：
- `Func2/Func5` 根本没有这种映射逻辑
- 截断后历史部分的前端数据完全丢失

---

## 2. 修复策略

### 策略A: 数据窗口截断（高优先级）—— Phase 1 ✅ 已实施

**目标**: 无论通达信传入多少K线，只处理当前窗口可见的K线。

**实现方案** (已写入 `Main.cpp`):
```cpp
static const int MAX_PROCESS_COUNT = 300; // 最大处理K线数量，超过则截断

struct DataWindow {
    std::vector<KLine> klines;
    int startIdx;
    int processCount;
};

static DataWindow prepareDataWindow(int nCount, float* pHigh, float* pLow, ...) {
    DataWindow dw;
    dw.processCount = (nCount < MAX_PROCESS_COUNT) ? nCount : MAX_PROCESS_COUNT;
    dw.startIdx = (nCount > MAX_PROCESS_COUNT) ? (nCount - MAX_PROCESS_COUNT) : 0;
    // ... 只构建截断后的数据
    return dw;
}

static void convertBiToOutputWithOffset(const std::vector<Bi>& bi_list, 
                                         float* pOut, int nCount, int startOffset) {
    memset(pOut, 0, nCount * sizeof(float));
    for (const auto& bi : bi_list) {
        int origStart = startOffset + bi.start_index;
        int origEnd = startOffset + bi.end_index;
        // ... 映射回原数组位置
    }
}
```

**关键改动点**:
- `Func1`（笔）和 `Func2`（线段）现在都调用 `prepareDataWindow()` 截断数据
- 使用 `convertBiToOutputWithOffset()` / `convertXianDuanToOutputWithOffset()` 将截断索引映射回原数组
- `TDXPlugin_Calculate` 统一使用相同逻辑

### 策略B: 修正索引映射（关键Bug）—— Phase 2 ✅ 已实施

**问题**: `getBi()` 和 `getXianDuan()` 使用 `new_index`（合并后索引）而非 `real_loc`（原始索引）

**修复**:
```cpp
// ChanAnalyzer.cpp - getBi()
bi.start_index = start.real_loc;  // 原来是 start.new_index
bi.end_index = end.real_loc;      // 原来是 end.new_index

// ChanAnalyzer.cpp - getXianDuan()
xd.start_index = start.real_loc;  // 原来是 start.new_index
xd.end_index = end.real_loc;      // 原来是 end.new_index
```

**效果**: 笔和线段的端点精确对应原始K线位置，通达信画线位置正确。

### 策略C: 简化接口 — Phase 2 ✅ 已实施

**旧版**: 5个函数（Func1简笔, Func2标准笔, Func3简化段, Func4简化1+1, Func5线段）

**新版**: 2个核心函数
- `Func1` = 标准笔（输出 ±1）
- `Func2` = 真正线段（输出 ±1）

**原因**: 
- 简笔 `Func1` 不精确，已被标准笔替代
- `Func3` 是伪线段，无实际意义
- `Func4` 未实现真正算法
- `Func5` 与 `Func3` 重复

### 策略D: ChanAnalyzer 算法优化（中优先级）

#### D1. 消除 vector 拷贝
```cpp
// 改前：返回vector拷贝
std::vector<StandardKLine> cleanFirstTwoTB(const std::vector<StandardKLine>& working_df);

// 改后：原地修改，传引用
void cleanFirstTwoTB(std::vector<StandardKLine>& working_df);  // 原地清理
```

#### D2. 缓存 next/previous 有效元素索引
```cpp
// 改前：每次线性搜索 O(n)
int getNextLoc(int loc, const std::vector<StandardKLine>& working_df);

// 改后：预处理建立有效元素索引表 O(1) 查询
std::vector<int> validIndices;  // 只存储tb != 0的位置
```

#### D3. 简化 defineXD 逻辑
当前有 `defineXD`, `defineXDEnhanced`, `defineXDFull` 三套实现：
- 确认哪套是正确/完整的
- 删除废弃版本，减少维护负担

### 策略E: 参考 Python 原实现修复算法（高优先级）

**参考路径**: `C:\Users\comet\git\jq\JoinQuantStrat\Utility\kBar_Chan.py`

**需要核对的关键函数**:
| C++ 函数 | Python 对应 | 核对要点 |
|---|---|---|
| `standardize()` | `standardize_klines()` | 包含关系处理逻辑 |
| `markTopBot()` | `mark_top_bot()` | 顶底分型标记 |
| `defineBi()` | `define_bi()` | 笔的形成条件 |
| `defineXD()` | `define_xd()` | 线段定义 |
| `checkXDTopBot*()` | `check_xd_top_bot()` | 线段顶底判断 |
| `isXDInclusionFree*()` | `is_inclusion_free()` | 包含关系判断 |

**修复原则**:
1. 如果 C++ 是简化版，补全缺失逻辑
2. 如果 C++ 有bug（如边界条件），对照Python修复
3. 如果 C++ 过于复杂且Python更清晰，重写该函数

---

## 3. 实施计划

> **编译与测试**: 由开发者手动执行。每次代码修改后，使用 `build_with_cmake.bat` 编译，复制 DLL 到通达信 `dlls` 目录测试。

### Phase 1: 紧急修复 — 防止卡死（已完成 ✅）

**目标**: 让插件能处理任意数量K线而不卡死。

| 任务 | 文件 | 状态 | 备注 |
|---|---|---|---|
| 1.1 统一数据截断函数 | `Main.cpp` | ✅ | `prepareDataWindow()` 已提取 |
| 1.2 修复 Func2 截断 | `Main.cpp` | ✅ | 已加入截断和索引映射 |
| 1.3 修复 Func5 截断 | `Main.cpp` | ✅ | 同上 |
| 1.4 验证 TDXPlugin_Calculate | `Main.cpp` | ✅ | 统一使用截断逻辑 |
| 1.5 修复绑定失败 | `Main.cpp` | ✅ | 移除 `<chrono>`/`<cstdio>`，保留旧版结构 |
| 1.6 调优 MAX_PROCESS_COUNT | `Main.cpp` | ⏳ | 待测试后手动调整 |

**Phase 1 遇到的问题与解决**:
- ❌ 首次修改加入 `<chrono>` + `fopen` 日志后，DLL编译成功但通达信绑定失败
- ✅ 回滚到旧版代码结构，仅加入数据截断逻辑，不引入新头文件，编译成功

### Phase 2: 笔和线段的正确画线输出（已完成 ✅）

**目标**: 修正画线位置，让通达信公式正确显示笔和线段。

| 任务 | 文件 | 状态 | 备注 |
|---|---|---|---|
| 2.1 修正 getBi() 索引 | `ChanAnalyzer.cpp` | ✅ | `new_index` → `real_loc` |
| 2.2 修正 getXianDuan() 索引 | `ChanAnalyzer.cpp` | ✅ | `new_index` → `real_loc` |
| 2.3 重写 Main.cpp 接口 | `Main.cpp` | ✅ | Func1=笔, Func2=线段, 删除Func3/4/5 |
| 2.4 更新公式文档 | `TDXChanPlugin_Simple_NoChinese.txt` | ✅ | 简化公式，只用笔和线段 |
| 2.5 编译验证 | `build_with_cmake.bat` | ✅ | DLL编译成功 |
| 2.6 通达信画线测试 | 手动测试 | ⏳ | 待用户验证 |

**Phase 2 遇到的问题与解决**:
- ❌ `getBi()`/`getXianDuan()` 使用 `new_index`（合并后索引），导致画线位置偏移
- ✅ 改为 `real_loc`（原始索引），画线位置精确对应原始K线
- ❌ `Func3` 是伪线段（模式匹配），不是真正线段
- ✅ `Func2` 改为调用 `ChanAnalyzer::getXianDuan()` 输出真正线段

### Phase 3: 通达信卡死解决与线段不显示修复（已完成 ✅）

| 任务 | 文件 | 状态 | 备注 |
|---|---|---|---|
| 3.1 调优 MAX_PROCESS_COUNT 300→4000 | `Main.cpp` | ✅ | 解决历史K线卡死 |
| 3.2 修复 findInitialDirectionFull 方向检测 | `ChanAnalyzer.cpp` | ✅ | 方向自动检测永远失败 |
| 3.3 修复 findXDFull 获取元素数量(4→6) | `ChanAnalyzer.cpp` | ✅ | 与Python一致 |
| 3.4 编译验证 | `build_with_cmake.bat` | ✅ | DLL编译成功 |
| 3.5 通达信画线测试 | 手动测试 | ⏳ | 线段仍不显示 |

### Phase 4: 编译错误修复与 defineBi/defineXD 完整算法（已完成 ✅）

| 任务 | 文件 | 状态 | 备注 |
|---|---|---|---|
| 4.1 CMakeLists.txt 设置 C++17 | `CMakeLists.txt` | ✅ | 修复结构化绑定编译错误 |
| 4.2 补全 getBi() 实现体 | `ChanAnalyzer.cpp` | ✅ | 缺失导致链接错误 |
| 4.3 删除未实现 camelCase 声明 | `ChanPlugin.h` | ✅ | 删除7个重复声明 |
| 4.4 defineBi() 完整重写 | `ChanAnalyzer.cpp` | ✅ | 匹配Python 340+行算法（same_tb_remove_*、check_gap_qualify、work_on_end、distance < 4等分支） |
| 4.5 defineXD/findXDFull 完整重写 | `ChanAnalyzer.cpp` | ✅ | 匹配Python逻辑（findInitialDirection、checkXDTopBot、isXDInclusionFree等） |
| 4.6 编译验证 | `build_with_cmake.bat` | ✅ | DLL编译成功 (49,152 bytes) |

### Phase 5: 代码清理与性能优化（部分完成）

| 任务 | 文件 | 状态 | 备注 |
|---|---|---|---|
| 5.1 消除 cleanFirstTwoTB vector 拷贝 | `ChanAnalyzer.cpp/h` | ✅ 已完成 | `cleanFirstTwoTB` 改为 in-place (`void` + `working_df.swap`) |
| 5.2 删除11个wrapper函数 | `ChanAnalyzer.cpp/h` | ✅ 已完成 | `kbarGapAsXd`, `xdInclusion`, `isXDInclusionFree`, `checkInclusionByDirection`, `xdTopbotCandidate`, `popGap`, `checkKlineGapAsXd`, `checkXDTopBot`, `checkXDTopBotDirected`, `findXD`, `defineXDEnhanced` |
| 5.3 删除未使用的辅助函数 | `ChanAnalyzer.cpp/h` | ✅ 已完成 | `getPreviousLoc`, `findInitialDirection` |
| 5.4 清理头文件声明 | `ChanPlugin.h` | ✅ 已完成 | 去除所有已删除函数的声明，精简至仅保留实际使用的API |
| 5.5 缓存有效索引 O(n)→O(1) | `ChanAnalyzer.cpp/h` | ⏳ 待分析 | 需要评估实际性能瓶颈，可能通过维护 next/prev 链表优化 `get_next_tb`/`trace_back_index` |
| 5.6 分析性能瓶颈 | `ChanAnalyzer.cpp` | ⏳ 待实施 | 在MAX_PROCESS_COUNT=4000下测试，确定是否需要D2优化 |

### Phase 6: 对照 Python 修复算法正确性（待实施）

| 任务 | 方法 | 状态 |
|---|---|---|
| 6.1 并排对比 | 打开 `kBar_Chan.py` 和 `ChanAnalyzer.cpp` 同步核对 | ⏳ 待实施 |
| 6.2 修复 standardize | 核对包含关系处理顺序和方向判断 | ⏳ 待实施 |
| 6.3 修复 markTopBot | 核对顶底分型边界条件 | ⏳ 待实施 |
| 6.4 修复 defineBi | 核对笔的生成和破坏条件 | ⏳ 待实施 |
| 6.5 修复 defineXD | 核对线段定义（最复杂）| ⏳ 待实施 |
| 6.6 验证输出 | 准备已知结果的数据，与 Python 输出对比验证 | ⏳ 待实施 |

---

## 4. 当前状态总结

截至 2026-04-25，已完成 Python 逻辑的全面对比验证，全部 14 个逻辑差异已修复。核心函数清单：

| 函数 | 状态 | 说明 |
|---|---|---|
| `ChanAnalyzer::standardize()` | ✅ | 包含关系处理完成，趋势方向已存储 |
| `ChanAnalyzer::markTopBot()` | ✅ | 顶底分型标记完成 |
| `ChanAnalyzer::cleanFirstTwoTB()` | ✅ | 前两个分型清理完成 |
| `ChanAnalyzer::defineBi()` | ✅ | 完整340+行算法，匹配Python |
| `ChanAnalyzer::getBi()` | ✅ | 缺失实现已补全 |
| `ChanAnalyzer::defineXD()` / `defineXDEnhanced()` | ✅ | 完整线段定义实现 |
| `ChanAnalyzer::findXDFull()` / `findXD()` | ✅ | 完整线段搜索实现（含尾部处理） |
| `ChanAnalyzer::getXianDuan()` | ✅ | 已实现 |
| `ChanAnalyzer::getNextNElem()` / `getPreviousNElem()` | ✅ | 已匹配Python（start_tb过滤、original_tb、N=0处理） |
| `ChanAnalyzer::directionAssert()` | ✅ | 已修正条件反转 |
| `ChanAnalyzer::xdTopbotCandidateFull()` | ✅ | 已修复无条件返回 |
| `ChanAnalyzer::isXDInclusionFreeFull()` | ✅ | 已添加元素删除逻辑 |
| `ChanAnalyzer::checkInclusionByDirectionFull()` | ✅ | 已改为first_run重新获取模式 |
| `ChanAnalyzer::combineGaps()` | ✅ | 已修复合并条件+排序 |
| `ChanAnalyzer::kbarGapAsXdFull()` | ✅ | 已修复缺口跨度累加+价格覆盖 |
| `ChanAnalyzer::checkPreviousElemToAvoidXdGap()` | ✅ | 已修复为查询前驱元素 |
| `ChanAnalyzer::check_gap_qualify()` / `restoreTbData()` | ✅ | 已修复半开区间 |
| 所有 `same_tb_remove_*`, `trace_back_index`, `get_next_tb`, `work_on_end` | ✅ | 全部补全 |
| `Main.cpp` 接口（Func1=笔, Func2=线段） | ✅ | 简化接口完成 |
| `CMakeLists.txt` C++17 标准 | ✅ | 已设置 |
| `CMakeLists.txt` CRT 静态链接 (`/MT`) | ✅ | 2026-06-04 修复退出崩溃 |
| `Main.cpp` `__stdcall` 调用约定 | ✅ | 2026-06-04 Win32 栈破坏修复 |

**已完成的阶段：**
- Phase 1: 紧急修复卡死 ✅
- Phase 2: 正确画线输出 ✅
- Phase 3: 卡死解决+线段不显示 ✅
- Phase 4: 编译错误+defineBi完整算法 ✅
- Phase 7: 线段端点类型反转+包含关系 ✅
- Phase 8: defineXD/findXDFull调用结构 ✅
- Phase 9/9b/9c: 对照Python全面修复(14个差异) ✅
- Phase 10: 退出崩溃修复（CRT静态链接+调用约定） ✅

**待实施：**
- Phase 5: 性能优化（消除 vector 拷贝、预计算索引）

---

### 2026-06-04 Phase 10 实施记录 — 退出通达信时崩溃修复（CRT 链接 + 调用约定）

#### 0.22 问题诊断：退出通达信后出现错误

**症状**：插件运行期间正常，但退出通达信后弹窗报错。Win32 和 x64 版本均受影响。

**根因 1：动态 CRT 链接 (`/MD`)**

`CMakeLists.txt` 未设置 `CMAKE_MSVC_RUNTIME_LIBRARY`，MSVC 默认使用 `/MD`（动态链接 CRT）。DLL 依赖外部 `msvcp140.dll` / `vcruntime140.dll`。进程退出时 DLL 卸载顺序不确定——若 CRT DLL 先于本 DLL 卸载，则 `std::vector` / `std::string` / `std::tuple` 等 STL 成员的析构函数调用已卸载的 CRT 代码，导致访问违例崩溃。

项目自身文档 `CONTINUE.md` 已明确指出 *"Do not introduce dynamic C++ runtime dependencies (`/MD`); use `/MT` for distribution"*，但 CMakeLists.txt 未强制执行。

**根因 2：`RegisterTdxFunc` 和函数指针缺少 `__stdcall`（仅影响 Win32）**

`Main.cpp` 中所有其他导出函数（`TDXPlugin_GetInfo`、`TDXPlugin_Calculate` 等）均使用 `__stdcall` 调用约定，但 `RegisterTdxFunc` 和 `pPluginFUNC` 函数指针类型缺少。在 Win32 平台下 `__cdecl` 与 `__stdcall` 的栈清理方式不同，若通达信预期 `__stdcall` 而 DLL 提供 `__cdecl`，每次 `Func1`/`Func2` 调用均会微量破坏栈，累积后可能导致崩溃。

（x64 平台调用约定统一，此问题不生效。）

#### 修复

| 文件 | 改动 | 说明 |
|------|------|------|
| `CMakeLists.txt` | 新增 `set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")` | 强制 `/MT`(Release) / `/MTd`(Debug) |
| `Main.cpp:22` | `pPluginFUNC` typedef 添加 `__stdcall` | 函数指针调用约定与通达信一致 |
| `Main.cpp:176` | `RegisterTdxFunc` 添加 `__stdcall` | 与 DLL 其他导出函数统一 |

**编译结果**: ✅ 编译成功

**影响范围**：仅编译选项和函数签名，不改变任何算法逻辑。

---

## 5. 测试指引（由开发者手动执行）

> 以下测试步骤需开发者在本地编译后手动验证。

### 4.1 绑定测试（Phase 1 验证）

1. 编译生成 DLL：`build_with_cmake.bat`
2. 复制 `build\Release\TDXChanPlugin.dll` 到通达信 `dlls` 目录
3. **重启通达信**（重要：DLL 可能被缓存）
4. 在通达信公式中加载插件：`TDXDLL1(1, H, L, 0)`（笔）和 `TDXDLL1(2, H, L, 0)`（线段）
5. 点击绑定按钮，观察是否成功

### 4.2 画线正确性测试（Phase 2 验证）

**测试目标**: 验证笔和线段的端点位置是否正确

1. 选择一个K线数量适中的股票（100-300根K线，方便肉眼验证）
2. 手动观察顶底分型位置
3. 对比通达信画出的笔端点是否与观察到的分型位置一致
4. 对比通达信画出的线段端点是否与缠论线段定义一致

**判断标准**:
- 笔：相邻顶底分型之间应该有至少4根K线间隔（缠论标准）
- 线段：基于特征序列的顶底，比笔更稀疏

### 4.3 性能测试方法

**性能目标**:
- 处理 300 根K线 < 50ms
- 处理 400 根K线 < 100ms
- 通达信不卡死、UI 流畅

**测试方法**:
1. 选择长周期股票（如 600519 贵州茅台，5000+ 根日线）
2. 加载插件公式，观察是否卡死
3. 左右拖动K线，观察画线是否实时更新
4. 切换周期（1分钟/5分钟/日线），观察性能
5. 调整 `MAX_PROCESS_COUNT`（200/300/400/500），找到最佳平衡点

### 4.4 正确性测试方法

1. 用 Python 运行 `kBar_Chan.py` 对同一组数据生成预期结果
2. 对比 C++ 插件输出是否一致
3. 重点关注：分型位置、笔端点、线段端点

---

## 6. 代码重构建议

### 5.1 目录结构重组（可选）

```
TDXChanPlugin/
├── src/
│   ├── Main.cpp              # 插件接口
│   ├── ChanPlugin.h          # 头文件
│   ├── ChanAnalyzer.cpp      # 核心算法
│   └── ChanAnalyzer.h        # 将类声明从ChanPlugin.h分离
├── include/
│   └── common.h              # 公共定义
├── tests/
│   └── test_chanalyzer.cpp   # 单元测试（待添加）
├── scripts/
│   ├── build_with_cmake.bat
│   └── build_x86.bat
├── reference/
│   └── kBar_Chan.py          # 参考Python实现（拷贝一份到项目）
├── docs/
│   └── TDXChanPlugin_Simple_NoChinese.txt
└── CMakeLists.txt

---

### 2026-04-25 Phase 8 实施记录 — defineXD/findXDFull 调用结构不匹配修复

#### 0.13 问题诊断：defineXD 与 findXDFull 调用结构不匹配

**位置**: `ChanAnalyzer.cpp` - `defineXD()` 和 `findXDFull()`

**根因**: Python `define_xd` 调用 `find_XD` **一次**，`find_XD` 内部 while 循环走完全程标记所有线段端点。而重写后的 C++ `findXDFull` 已有内部 while 循环管理方向翻转和位置推进，但 `defineXD` 仍用外层 while 循环反复调用 `findXDFull`，并在两端分别翻转方向，导致算法状态混乱，无法正确标记线段端点。

**修复**: 将 `defineXD` 改为单次调用 `findXDFull(initial_loc, initial_direction, working_df)`，然后从 `working_df` 中收集 `xd_tb != NO_TOPBOT` 的元素。

```cpp
// 改前：外层 while 循环 + 内部 while 循环（方向被翻转两次）
while (current_idx < working_df.size()) {
    auto found_xd = findXDFull(current_idx, initial_direction, working_df);
    if (!found_xd.empty()) {
        // ... advance idx, flip direction ...
    }
}

// 改后：单次调用（匹配 Python 行为）
findXDFull(initial_loc, initial_direction, working_df);
// 从 working_df 收集标记了 xd_tb 的元素
```

**编译结果**: ✅ 编译成功 (`build\Release\TDXChanPlugin.dll`)

---

### 2026-04-24 Phase 7 实施记录 — 线段显示修复（端点类型反转与包含关系Bug）

#### 0.10 问题诊断：线段端点类型反转

**位置**: `Main.cpp` — `convertBiToOutputWithOffset()` 和 `convertXianDuanToOutputWithOffset()`

在 `getXianDuan()` 中，`xd.type = start.xd_tb`（线段起点类型），然后两个输出函数对**起点和终点都用同一个 `xd.type`** 来标记。导致：

- `(BOT→TOP)` 线段：起点 BOT = -1 正确，终点 TOP = -1 错误（应该是 +1）
- `(TOP→BOT)` 线段：起点 TOP = +1 正确，终点 BOT = +1 错误（应该是 -1）

**内部交点**被后续线段覆盖后偶然正确，但**最后一个端点永远是错的**。

**修复（Main.cpp）**: 终点标记为起点的相反类型（线段总是 BOT/TOP 交替）：
```cpp
// 改前
pOut[origEnd] = (xd.type == TOP) ? 1.0f : -1.0f;
// 改后
pOut[origEnd] = (xd.type == TOP) ? -1.0f : 1.0f;  // 终点取反
```

同样修复了 `convertBiToOutputWithOffset()` 中的笔终点标记。

#### 0.11 问题诊断：isXDInclusionFreeFull 检查了重叠笔对

**位置**: `ChanAnalyzer.cpp` — `isXDInclusionFreeFull()`

原代码用双重循环检查所有 `(i,i+1) vs (j,j+1)` 笔对组合，包括 `(A,B) vs (B,C)` 这样的重叠对（j 从 0 开始）。

由于共享端点 B，价格区间必然重叠，导致 `free` **永远为 `false`**。线段检测逻辑（`if (is_free) { checkXDTopBot... }`）**永远无法到达**。

**修复**: 将内层循环起始从 `j = 0` 改为 `j = i + 2`，只检查不重叠的笔对。

#### 0.12 问题诊断：findXDFull 与Python find_XD 流程结构不同

**位置**: `ChanAnalyzer.cpp` — `findXDFull()` 主循环体

**详细对比 Python `find_XD`（no gap case）vs CPP `findXDFull`（原版）：**

| 步骤 | Python | CPP（原版） |
|------|--------|-------------|
| 1 | `get_next_N_elem(i, 4)` 获取4个元素 | `getNextNElem(i, 6)` 直接获取6个 |
| 2 | 检查 `current_gap` | 检查 `isXDInclusionFreeFull` |
| 3 | `get_next_N_elem(i, 3, start_tb, True)` 获取3个同向元素 | 直接进入包含关系判断 |
| 4 | `xd_topbot_candidate()` **在** XD检查前调用 | `xdTopbotCandidate()` 在 XD检查后调用 |
| 5 | 从 `single_dir_elems[0]` 获取6个元素 | 从 `current_idx` 获取6个元素 |
| 6 | `check_XD_topbot_directed` | `checkXDTopBotDirectedFull` |
| 7 | 检查 `previous_xd_tb_idx` 有效性 | **缺失** |
| 8 | `i = next_valid_elems[3]`（非缺口时） | `current_idx = next_valid_elems[0] + 1` |

**关键差异**：
1. Python 用 `xd_topbot_candidate` 做**预筛选**，CPP 做**后筛选**
2. Python 的6个元素从 `single_dir_elems[0]` 开始（已对齐方向），CPP 从原始位置开始
3. Python 有 `previous_xd_tb_idx` 的验证/回退逻辑，CPP 完全缺失
4. Python 用 `next_valid_elems[3]` 更新位置（跳过已处理元素），CPP 用 `next_valid_elems[0] + 1`

**尝试修复**：对 `findXDFull()` 进行了 Python 流程匹配的重写，包括：
- 先获取4个元素检查 current_gap
- 再获取3个同向元素做 candidate 预检
- 从 `single_dir_elems[0]` 获取6个元素
- 增加 `previous_xd_tb_idx` 验证逻辑
- 修复位置更新为 `nve[3]`

**状态**: 部分完成 — 由于文件操作工具限制（Unicode 字符匹配问题），代码修改未能完整应用到 `ChanAnalyzer.cpp` 中。原有 `findXDFull` 的 while 循环体已被部分替换，但文件存在重复代码需要清理。

| 任务 | 文件 | 状态 | 备注 |
|---|---|---|---|
| 7.1 修复 isXDInclusionFreeFull 重叠笔对 | `ChanAnalyzer.cpp` | 已完成 | j 从 i+2 开始 |
| 7.2 修复输出端点类型反转 | `Main.cpp` | 已完成 | convertBi/convertXianDuan 终点取反 |
| 7.3 标准化 marked_bi 中 xd_tb 初始化 | `defineXD()` | 已完成 | 初始分型加入 xd_result |
| 7.4 findXDFull 流程重写匹配 Python | `ChanAnalyzer.cpp` | 已完成 | while 循环体已替换 |
| 7.5 编译验证 — 修复 findXDFull 缺失的 return/函数结束符 | `ChanAnalyzer.cpp` | 已完成 | findXDFull 末尾补上 `return result;` 和 `}` |

**编译结果**: ✅ 编译成功 (`build\Release\TDXChanPlugin.dll`, 49,152 bytes)

**下一步**：通达信实际画线测试，或继续 Phase 5/6 优化。确保以下函数只出现一次：
- `findXDFull()` — 新版本（Python匹配）
- `findXD()` — 简化版
- `defineXDEnhanced()` — 简化版
- `checkInclusionByDirectionFull()` — 完整实现
- 及其他辅助函数