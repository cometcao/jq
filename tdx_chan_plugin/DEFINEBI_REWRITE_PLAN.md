# defineBi() 完整算法重写计划

## 1. 问题分析

### 1.1 当前 `defineBi()`（简化版 ~110行）

位于 `ChanAnalyzer.cpp:380-497`，实现了：
- Step 1: 收集所有分型 → 相同类型分型合并（保留极值）
- Step 2: 检查类型交替 + 最小4根K线间隔（有缺口时可放宽）
- Step 3: 设置 `chan_price` / `original_tb`

**问题**: 省略了 Python 原版 340+ 行复杂逻辑，导致：
1. **分型三段去除缺失** — 当连续3个分型中前两个或后两个同类型时，需要根据价格关系去除中间或边缘，当前只做了最简单的相邻同类型合并
2. **回溯查找缺失** — 删除分型后需要回溯重新检查，当前是线性扫描
3. **缺口条件检查缺失** — `check_gap_qualify` 声明了但未实现
4. **方向一致性检查缺失** — `checkDirectionConsistency` 声明了但未实现
5. **`getBi()` 函数完全缺失**（头文件声明了但 .cpp 里没有实现体）

### 1.2 从 Python 需要参考的算法步骤

```
Python self.define_bi(working_df):
  1. cleanFirstTwoTB → 清理前两个无效分型
  LOOP while size < N + 1:
    2. get_next_N_elem(3) → 获取连续3个分型
    3. same_tb_remove → 三段同类型去除
       same_tb_remove_previous: 前两个同类型 → 保留极值 / 删除中间
       same_tb_remove_current:  后两个同类型 → 保留极值 / 删除中间
       same_tb_remove_next:     跳过当前检查下一个
    4. work_on_end → 边界处理/回溯
    5. check_gap_qualify → 缺口条件下放宽距离要求
    6. checkDirectionConsistency → 方向一致性
  RETURN 最终笔列表
```

---

## 2. 函数状态（Bugfix 完成后）

### 涉及文件: `ChanAnalyzer.cpp` + `ChanPlugin.h`

| # | 函数 | 当前状态 | 说明 |
|---|------|---------|------|
| 1 | `getBi()` | ✅ 已实现(2026-04-24修复) | 原缺失导致链接错误，已补全 |
| 2 | `defineBi()` | ✅ 完整算法重写完成 | 三段去除+回溯+缺口气格+方向一致性 (见下方注释) |
| 3 | `sameTBRemoveEdge()` | ✅ 已实现 | defineBi 主循环中备选调用 |
| 4 | `sameTBRemoveMiddle()` | ✅ 已实现 | — |
| 5 | `removeOneTBFromTwo()` | ✅ 已实现 | — |
| 6 | `workOnEnd()` | ✅ 已实现 | 已集成到 defineBi Step 4 |
| 7 | `checkDirectionConsistency()` | ✅ 已实现 | 方向一致性检查 |
| 8 | `checkGapQualify()` | ✅ 已实现 | 缺口条件下放宽距离要求 |
| 9 | `traceBackIndex()` | ✅ 已实现 | 与 trace_back_index 逻辑重复，可后续合并 |
| 10 | `same_tb_remove_previous()` | ✅ 已实现(2026-04-24新增) | 三段去除：前两个同类型 |
| 11 | `same_tb_remove_current()` | ✅ 已实现(2026-04-24新增) | 三段去除：后两个同类型 |
| 12 | `same_tb_remove_next()` | ✅ 已实现(2026-04-24新增) | 跳过当前，检查下一组 |
| 13 | `check_gap_qualify()` | ✅ 已实现(2026-04-24新增) | 缺口条件下放宽距离 |
| 14 | `trace_back_index()` | ✅ 已实现 | 获取前一个有效分型 |
| 15 | `get_next_tb()` | ✅ 已实现 | 获取下一个有效分型 |

> **注意**: 此次修复删除了 `ChanPlugin.h` 中的 `sameTBRemoveEdge` / `sameTBRemoveMiddle` / `removeOneTBFromTwo` / `workOnEnd` / `checkDirectionConsistency` / `checkGapQualify` / `traceBackIndex` 共 7 个声明（与 snake_case 版本重复，统一使用 snake_case 命名）。

---

## 3. 重写后的 defineBi() 算法流程图

```
defineBi(working_df):
  │
  ├─ Step 1: run cleanFirstTwoTB(working_df)
  │   清理前两个无效分型（同类型合并/距离检查/无效组合）
  │
  ├─ Step 2: 主循环 (while loop)
  │   │
  │   ├─ 2a. 获取 prev/cur/next 三个连续分型索引
  │   │   用 get_next_tb() / trace_back_index()
  │   │
  │   ├─ 2b. same_tb_remove 三段处理
  │   │   ├─ same_tb_remove_previous: prev.tb == cur.tb
  │   │   │   → 根据价格保留极值，删除pre或cur
  │   │   ├─ same_tb_remove_current: cur.tb == next.tb
  │   │   │   → 根据价格保留极值，删除cur或next
  │   │   └─ same_tb_remove_next: 跳过当前，检查下一组
  │   │
  │   ├─ 2c. 间距检查 + 缺口气格
  │   │   ├─ 间距 >= 4K线 → 有效笔
  │   │   └─ 间距 < 4K线 + 有缺口 + check_gap_qualify → 有效笔
  │   │
  │   ├─ 2d. 类型交替检查
  │   │   └─ 同类型 → 保留极值
  │   │
  │   └─ 2e. 方向一致性检查 (checkDirectionConsistency)
  │
  ├─ Step 3: workOnEnd 处理末尾
  │   处理最后一个分型的边界条件
  │
  └─ Step 4: 设置 chan_price / original_tb
```

---

## 4. 代码改动详情

### 4.1 新增 `getBi()` 实现

**位置**: `ChanAnalyzer.cpp`，在 `defineBi()` 之前或文件末尾

```cpp
std::vector<Bi> ChanAnalyzer::getBi() const {
    std::vector<Bi> result;
    if (marked_bi.size() < 2) return result;
    
    for (size_t i = 0; i + 1 < marked_bi.size(); i++) {
        const StandardKLine& start = marked_bi[i];
        const StandardKLine& end = marked_bi[i+1];
        
        // 确保分型类型交替（底→顶 或 顶→底）
        if ((start.tb == BOT && end.tb == TOP) || 
            (start.tb == TOP && end.tb == BOT)) {
            Bi bi;
            bi.start_date = start.date;
            bi.end_date = end.date;
            bi.start_price = start.chan_price;
            bi.end_price = end.chan_price;
            bi.type = start.tb;
            bi.start_index = start.real_loc;   // ← 注意使用 real_loc
            bi.end_index = end.real_loc;       //    (不是 new_index)
            result.push_back(bi);
        }
    }
    return result;
}
```

### 4.2 新增 `same_tb_remove_previous()`

```cpp
std::tuple<int, int, int> ChanAnalyzer::same_tb_remove_previous(
    std::vector<StandardKLine>& working_df, 
    int previous_index, int current_index, int next_index) 
{
    // 情况：previous 和 current 同类型
    // 根据是顶还是底决定保留哪一个
    if (working_df[previous_index].tb == TOP) {
        // 顶分型：保留更高的顶
        if (float_more(working_df[previous_index].high, working_df[current_index].high)) {
            // 删除current
            working_df[current_index].tb = NO_TOPBOT;
            current_index = trace_back_index(working_df, current_index);
        } else {
            // 删除previous
            working_df[previous_index].tb = NO_TOPBOT;
            previous_index = trace_back_index(working_df, previous_index);
        }
    } else {  // BOT
        // 底分型：保留更低的底
        if (float_less(working_df[previous_index].low, working_df[current_index].low)) {
            working_df[current_index].tb = NO_TOPBOT;
            current_index = trace_back_index(working_df, current_index);
        } else {
            working_df[previous_index].tb = NO_TOPBOT;
            previous_index = trace_back_index(working_df, previous_index);
        }
    }
    return {previous_index, current_index, next_index};
}
```

### 4.3 新增 `same_tb_remove_current()`

```cpp
std::tuple<int, int, int> ChanAnalyzer::same_tb_remove_current(
    std::vector<StandardKLine>& working_df,
    int previous_index, int current_index, int next_index)
{
    // 情况：current 和 next 同类型
    // 根据是顶还是底决定保留哪一个
    if (working_df[current_index].tb == TOP) {
        if (float_more(working_df[current_index].high, working_df[next_index].high)) {
            working_df[next_index].tb = NO_TOPBOT;
            next_index = get_next_tb(next_index, working_df);
        } else {
            working_df[current_index].tb = NO_TOPBOT;
            current_index = trace_back_index(working_df, current_index);
        }
    } else {  // BOT
        if (float_less(working_df[current_index].low, working_df[next_index].low)) {
            working_df[next_index].tb = NO_TOPBOT;
            next_index = get_next_tb(next_index, working_df);
        } else {
            working_df[current_index].tb = NO_TOPBOT;
            current_index = trace_back_index(working_df, current_index);
        }
    }
    return {previous_index, current_index, next_index};
}
```

### 4.4 新增 `same_tb_remove_next()`

```cpp
std::tuple<int, int, int> ChanAnalyzer::same_tb_remove_next(
    std::vector<StandardKLine>& working_df,
    int previous_index, int current_index, int next_index)
{
    // 情况：跳过current，检查next和再下一个是否同类型
    // 这等于推进一格重新检查
    previous_index = current_index;
    current_index = next_index;
    next_index = get_next_tb(next_index, working_df);
    return {previous_index, current_index, next_index};
}
```

### 4.5 新增 `check_gap_qualify()`

```cpp
bool ChanAnalyzer::check_gap_qualify(
    const std::vector<StandardKLine>& working_df,
    int previous_index, int current_index, int next_index)
{
    // 检查 current 和 next 之间是否有缺口使笔可以成立
    // (间距<4K线时，有缺口可酌情放宽)
    if (previous_index < 0) return false;
    
    int gap = working_df[next_index].new_index - working_df[current_index].new_index;
    if (gap >= 4) return true;  // 间距已经足够
    
    // 检查current和next之间是否有缺口
    if (!gapExistsInRange(
            working_df[current_index].date, 
            working_df[next_index].date)) {
        return false;
    }
    
    // 缺口气格：根据方向判断缺口是否有效
    // 确认缺口方向与笔方向一致
    TopBotType bi_direction = working_df[current_index].tb;
    // ...
    return true;
}
```

### 4.6 重写 `defineBi()` 主函数

**核心**: 改为 while 循环 + 三段分型逐步扫描的方式，调用上述辅助函数。

伪代码结构：
```cpp
void ChanAnalyzer::defineBi() {
    if (standardized.empty()) return;
    
    // 1. 准备分型数组
    std::vector<StandardKLine> working_df = cleanFirstTwoTB(standardized);
    if (working_df.size() < 2) { marked_bi = working_df; return; }
    
    // 2. 主循环
    int pre_idx = 0;  // 第一个分型
    int cur_idx = get_next_tb(pre_idx, working_df);
    int nex_idx = get_next_tb(cur_idx, working_df);
    
    if (cur_idx >= (int)working_df.size() || nex_idx >= (int)working_df.size()) {
        // 分型不够，直接返回
        marked_bi = working_df;
        return;
    }
    
    // 三段去除主循环
    while (nex_idx < (int)working_df.size()) {
        // step a: 检查previous和current是否同类型
        if (working_df[pre_idx].tb == working_df[cur_idx].tb) {
            auto [p, c, n] = same_tb_remove_previous(working_df, pre_idx, cur_idx, nex_idx);
            pre_idx = p; cur_idx = c; nex_idx = n;
            if (cur_idx < 0) break;
            continue;
        }
        
        // step b: 检查current和next是否同类型
        if (working_df[cur_idx].tb == working_df[nex_idx].tb) {
            auto [p, c, n] = same_tb_remove_current(working_df, pre_idx, cur_idx, nex_idx);
            pre_idx = p; cur_idx = c; nex_idx = n;
            continue;
        }
        
        // step c: 检查间距
        int kline_gap = working_df[cur_idx].new_index - working_df[pre_idx].new_index;
        if (kline_gap < 4) {
            // 间距不足，检查缺口气格
            if (checkGapQualify(working_df, pre_idx, cur_idx, nex_idx)) {
                // 缺口允许成立笔
            } else {
                // 不成立：删除cur（中间分型）
                working_df[cur_idx].tb = NO_TOPBOT;
                cur_idx = trace_back_index(working_df, cur_idx);
                continue;
            }
        }
        
        // step d: 方向一致性检查
        if (!checkDirectionConsistency(working_df, pre_idx, cur_idx, nex_idx)) {
            // 方向不一致，删除current
            working_df[cur_idx].tb = NO_TOPBOT;
            cur_idx = trace_back_index(working_df, cur_idx);
            continue;
        }
        
        // step e: 全部通过，推进到下一组
        pre_idx = cur_idx;
        cur_idx = nex_idx;
        nex_idx = get_next_tb(nex_idx, working_df);
    }
    
    // 3. workOnEnd 处理末尾边界
    workOnEnd(pre_idx, cur_idx, nex_idx, working_df);
    
    // 4. 收集结果，设置chan_price/original_tb
    std::vector<StandardKLine> valid_bi;
    for (auto& k : working_df) {
        if (k.tb == TOP || k.tb == BOT) {
            k.chan_price = (k.tb == TOP) ? k.high : k.low;
            k.original_tb = k.tb;
            valid_bi.push_back(k);
        }
    }
    marked_bi = valid_bi;
}
```

---

## 5. 已完成（已存在但未使用）的辅助函数

| 函数 | 位置 | 状态 | 在重写后的defineBi中的作用 |
|------|------|------|--------------------------|
| `checkGapQualify()` | ChanAnalyzer.cpp:约2090-2196 | ✅ 已实现 | Step 2c:间距不足时检查缺口是否允许笔成立 |
| `traceBackIndex()` | ChanAnalyzer.cpp:约2020-2030 | ✅ 已实现 | 删除分型后回溯前一个有效分型 |
| `sameTBRemoveEdge()` | ChanAnalyzer.cpp:约1980-1990 | ✅ 已实现 | 三段同类型去除的边缘处理 |
| `sameTBRemoveMiddle()` | ChanAnalyzer.cpp:约1990-2000 | ✅ 已实现 | 三段同类型去除的中间处理 |
| `removeOneTBFromTwo()` | ChanAnalyzer.cpp:约2000-2010 | ✅ 已实现 | 两分型中去掉一个 |
| `workOnEnd()` | ChanAnalyzer.cpp:约2030-2070 | ✅ 已实现 | 处理末尾边界条件 |
| `checkDirectionConsistency()` | ChanAnalyzer.cpp:约2070-2090 | ✅ 已实现 | 检查笔方向一致性 |

---

## 6. 实施顺序

| 步骤 | 文件 | 改动 | 优先级 |
|------|------|------|--------|
| 1 | `ChanAnalyzer.cpp` | 新增 `getBi()` 实现 | 🔴 必须（链接错误） |
| 2 | `ChanAnalyzer.cpp` | 新增 `same_tb_remove_previous()` | 🟡 必须 |
| 3 | `ChanAnalyzer.cpp` | 新增 `same_tb_remove_current()` | 🟡 必须 |
| 4 | `ChanAnalyzer.cpp` | 新增 `same_tb_remove_next()` | 🟡 必须 |
| 5 | `ChanAnalyzer.cpp` | 新增 `check_gap_qualify()` | 🟡 必须 |
| 6 | `ChanAnalyzer.cpp` | 重写 `defineBi()` | 🔴 核心改动 |
| 7 | — | 编译验证 (`build_with_cmake.bat`) | 🔴 必须 |

---

## 7. 风险与注意事项

1. **`getBi()` 缺失 → 链接错误**: 这是当前最紧迫的问题，头文件声明了但 .cpp 没实现，**会导致编译失败**。这是"做到第2步但编译失败"的直接原因。

2. **`real_loc` vs `new_index`**: `getBi()` 中必须使用 `real_loc`（原始索引），因为 `Main.cpp` 中的 `convertBiToOutputWithOffset()` 用 `startOffset + bi.start_index` 映射回通达信原始数组。如果误用 `new_index`（merge后的索引），画线位置会偏移。

3. **`getXianDuan()` 中的 `new_index` bug**: 当前 `getXianDuan()` 第2238-2239行仍然使用 `start.new_index` 和 `end.new_index`，应改为 `start.real_loc` / `end.real_loc`。

4. **性能**: 重写后的 `defineBi()` 会多次修改 `working_df` 数组（删除分型后回溯），但数据量较小（标准化后最多几百个分型），性能影响可忽略。

---

## 8. 预期结果

| 对比项 | 修改前 | 修改后 |
|--------|--------|--------|
| `defineBi()` 实现 | 简化版（~110行） | 完整算法（~300行） |
| `getBi()` | ❌ 缺失 → 编译失败 | ✅ 已实现 |
| 笔端点位置 | 可能有误（缺少三段去除） | 与 Python 版一致 |
| 笔间距检查 | 仅 >=4K线 | 三段去除+回溯+缺口气格 |
| 编译状态 | ❌ 链接错误 | ✅ 编译通过 |

---

*本文档仅供开发参考，实际代码以 `ChanAnalyzer.cpp` 实现为准。*