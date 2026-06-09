# TDXChanPlugin 修复记录

按时间倒序排列的关键修复汇总。

---

## 2026-06-09 — 线段端点紧邻替换 + shortcut 连锁修复

**问题**: 无缺口模式下，defineXD 循环翻转方向后更高同类型端点无法被替换；且 xdTopbotCandidate shortcut 存在连锁跳跃。

**最终修复**:
| 位置 | 改动 | 目的 |
|------|------|------|
| `:1292-1294` | shortcut `continue` → `cand+5 < size` bounds | 消除连锁跳跃，确保逐级判定 |
| `:1368 之后` | 删除死代码 | 条件互斥，永不可达 |
| `:1479 之后` | in-loop: 扫描紧邻同类型笔端点，价格更优则替换 xd_tb | 方向翻转前修正端点 |

**关键 guards**: `j > xd_idx + 4`（不跨半张图）、`j + 2 < size`（下段有足够元素）。

**`with_gap` 过滤已移除**: `with_gap` 是特征序列缺口（TOP_ref < BOT_right），在上升趋势中天然频繁出现，与"无 K 线缺口"是不同概念。移除过滤后替换逻辑对所有端点生效。

---

## 2026-06-04 — Phase 10: 退出崩溃修复 (CRT + 调用约定)

**问题**: 退出通达信时 DLL 崩溃 (`0xC0000005`)。

**根因 1**: CMake 默认 `/MD` 动态链接 CRT，DLL 依赖 `msvcp140.dll`/`vcruntime140.dll`。进程退出时 CRT DLL 可能先于本 DLL 卸载，STL 析构访问已卸载代码。
**根因 2** (仅 32-bit): `RegisterTdxFunc` 和函数指针缺少 `__stdcall`，栈清理方式不同导致累积栈破坏。

**修复**:
- `CMakeLists.txt`: 添加 `CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"` → 强制 `/MT` / `/MTd`
- `Main.cpp`: `Func1`/`Func2`/`pPluginFUNC` 添加 `__stdcall`

**结果**: 64-bit 完全解决，32-bit 仍残留（不影响实际功能）。

---

## 2026-04-28~30 — Plan A 迭代: 线段检测重构

`defineXD` 从"删除法"重构为"合并法" (FeatureSeqElement):

- **2026-04-26**: 引入 `buildFeatureSeq`/`processInclusions`/`applyCleanSequence`/`findXDOnFeatureSeq`，price/orig_price 分离
- **2026-04-27**: 方向感知修复 — `processInclusions` 增加 `direction` 参数，修复上升/下降段处理错误特征序列类型的 bug
- **2026-04-28**: 多段迭代重建 — 每段独立 build→merge→detect→advance
- **2026-04-28 fix**: `applyCleanSequence` chan_price 全量刷新
- **2026-04-30 fix**: 非单调 `orig_market_idx` 修复 (`is_kg2_backstep`)

---

## 2026-04-26 — 对照 Python 全面修复 (Phase 9)

14 个逻辑差异全部修复，核心改动:

| Bug | 问题 | 修复 |
|-----|------|------|
| `getNextNElem` 起始过滤 | 返回错误元素类型 | 匹配 Python start_tb 过滤 |
| `directionAssert` 方向判断 | BOT2TOP/TOP2BOT 颠倒 | 反转检查条件 |
| `findInitialDirectionFull` | 简化过度，方向判断错误 | 滑动窗口 4 元素 chan_price 检测 |
| `findXDFull` start_tb | 传 current_direction(3/4) 而非枚举 | 传 NO_TOPBOT |
| `xdTopbotCandidateFull` | 无条件返回，从不调用检查 | 添加价格超过参考检查 |
| `isXDInclusionFreeFull` | 缺少元素删除逻辑 | 添加删除被包含元素 |
| `checkInclusionByDirectionFull` | first_run 重复过滤 | 重取模式 |
| `combineGaps` | 合并条件错误 + 未排序 | 排序 + 修正合并条件 |
| `kbarGapAsXdFull` | 缺口跨度只取第一个 | 累积所有 gap_range |
| `checkPreviousElemToAvoidXdGap` | 未查前驱元素 | 添加前驱查询 |
| `check_gap_qualify`/`restoreTbData` | 半开区间错误 | 修正区间边界 |

---

## 2026-04-25 — Phase 8: defineXD/findXDFull 调用结构

修复 `defineXD` 与 `findXDFull` 之间的调用结构，使线段端点检测正常工作。

---

## 2026-04-25 — Phase 7: 线段端点类型反转 + 包含关系

- 修复线段端点类型反转 bug
- 修复包含关系判断

---

## 2026-04-24 — Phase 4: 编译错误 + defineBi 完整实现

- 补全 `getBi()` 实现体（原缺失导致链接错误）
- 将 `auto [a,b,c] = ...` 结构化绑定改为 `std::tuple` + `std::get`（兼容 C++14 编译）
- `defineBi()` 完整重写（same_tb_remove_*、check_gap_qualify、work_on_end、distance < 4 分支等 340+ 行算法）
- 补全所有辅助函数: `same_tb_remove_previous/current/next`、`trace_back_index`、`get_next_tb`

---

## 2026-04-24 — Phase 5: 性能优化 (数据截断)

- 添加 `MAX_PROCESS_COUNT = 6000` 截断保护，防止历史 K 线过多导致卡死
- `Main.cpp` 新增 `prepareDataWindow()` 统一截断逻辑

---

## 2026-04-23 — Phase 2: 画线位置修复

**问题**: `getBi()`/`getXianDuan()` 使用 `new_index`（合并后索引）而非 `real_loc`（原始索引），导致画线位置偏移。

**修复**: 改为 `real_loc`，配合 `startOffset` 映射回通达信原始数组。

---

## 2026-04-23 — Phase 1: 紧急修复卡死

**问题**: 历史 K 线过多时 `analyze()` 处理时间过长导致通达信卡死。

**修复**: 添加 `MAX_PROCESS_COUNT = 300` 数据截断（后续 Phase 5 增大到 6000）。
