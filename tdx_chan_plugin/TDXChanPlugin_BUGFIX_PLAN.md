# TDXChanPlugin 修复记录

按时间倒序排列的关键修复汇总。

---

## 2026-10-08 — 线段划分: 恢复 Python 原版口径 + 非法端点对清理 + 标准化开关

**背景**: 反馈"不少线段的顶底在划分时被完全避开"。逐层核对后确认两件事:
1. **"端点=线段极值"是缠论第78课允许的\*\*标准化\*\*后处理, 不是划分标准**。原文明确承认
   "线段中, 最高或最低点不是线段的端点"的情形(第一种情况的笔破坏最终没有在该方向发展成
   线段破坏), 并要求此时保留原划分、需要时再标准化。
2. 与 Python 原版对比, **笔与线段两层都发生了改动**: 笔端点序列只有 8/20 一致; 线段端点
   序列只有 5/20 一致(即使用户记忆中的缺口记账 `with_gap`/`gap_XD` 原版确实有, 原文要求的
   "第二种情况需反向特征序列分型确认"原版也没有, 用的是价格突破近似, 且 `pop_gap`/
   `check_XD_topbot`/`check_kline_gap_as_xd` 都是死代码)。

**逐层一致率** (20 组随机游走数据, 与 Python 原版 `kBar_Chan.py` 同输入对比):

| 层级 | 修复前 | 修复后 |
|------|--------|--------|
| 笔端点序列 | 8/20 | 8/20 (未动) |
| 线段端点序列(纯划分, 标准化关闭) | 5/20 | **12/20** |

**改动**:

| 位置 | 改动 | 依据 |
|------|------|------|
| `findXDOnFeatureSeq` | 按 Python 原版重写: 单一循环、`i += 1` 滑动窗口、K线缺口检查与标准分型走同一路径、`kg2` 状态化并据此判定 `is_kg2_backstep` | 原文第67课两种情况 |
| `defineXD` 主循环 | 补回 `!found` 时的缺口回退+重扫(Python 1406-1422)、带缺口端点回退(Python 1427-1442)、`prev_xd` 失效回退改用 `getPreviousNElem(..., reverse(type))`; 去掉 C++ 特有的"紧邻同类型笔端点替换" | 对齐原版 |
| `checkPreviousElemToAvoidXdGap` | 新增(对照 Python 1355-1374): 缺口判定再用前一同类型特征元素收窄 | 原文第67课第一种情况 |
| `cleanXdMarks` | 新增: 相邻同类型端点只保留更极端者。Python 原版会留下这种结果, 而 C++ `getXianDuan()` 会因类型不交替把整对丢弃 → 线段凭空少一段 | 线段端点必须顶底交替 |
| `repairXdExtremes` | 保留为**标准化**步骤, 由 `CHAN_STANDARDIZE_XD` 控制(默认开) | 原文第78课 |
| `CHAN_MIN_BI_SPAN` | 标准化移动范围下限(默认 3 = 线段至少三笔) | 原文第65课 |

**效果** (20 组随机游走数据; 口径为"端点是否为该段内同类型最极端的笔端点"):

| 版本 | 线段 | 非极值端点 | 非法端点对 | 少于三笔 | 纯划分与原版一致 |
|------|------|-----------|-----------|---------|-----------------|
| git HEAD(修复前) | 87 | 11 (12.6%) | 0 | 0 | 5/20 |
| 仅"端点=极值"补丁 | 86 | 2 (2.3%) | 0 | 0 | 2/20 |
| **本次(原版口径+清理+标准化)** | 69 | 3 (4.3%) | 0 | 0 | 12/20 |
| 本次但关闭标准化 | 68 | 14 | 0 | 0 | 7/20(清理后) |

真实数据抽查: 600519(1151 根日线)端点 = `[46,116,197,251,340,380,622,665,745,772,1061,1108,1147]`,
与 Python 原版**完全一致**; 残留的 2 处"端点非本段极值"属第78课的"古怪线段" —— 强行标准化会
产生不足三笔的线段, 故保留原划分。


### 补充 (同日): 笔阶段包含处理修复 + 第二种情况确认

**笔阶段根因** (对照原文第62课"向上取两K线最高点+低点中较高者, 向下取最低点+高点中较低者"):
C++ `standardize` 用 `high=0/low=0` 当"已被合并"的标记, 而 Python 原版把合并结果放在
`new_high/new_low`、被合并元素**保留原始 high/low**。被合并元素仍会被 `isBullType(past, first)`
读取, 于是方向恒判为 BOT2TOP, 合并取 max/min 取错, 标准化序列与分型数量/位置全偏。

修复: `StandardKLine` 新增 `merged_away` 标志, 去掉 0 哨兵。效果:

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 分型阶段与 Python 原版一致 | 0/20 | 7/20 (残余差异被 defineBi 清理吸收) |
| 笔端点序列与 Python 原版一致 | 8/20 | **19/20** |

注: 笔的阈值(`new_index` 间距 >= 4)对应原文第62课"顶和底之间至少有一根K线"的严格(老笔)
口径; 缠师另有放宽的新笔口径(分型不共用K线, 间距 >= 3), 如需切换改一个常数即可。

**第二种情况** (原文第67课 + 第78课): 新增 `secondFeatureSeqConfirms()` —— 候选端点带特征
序列缺口时不立即提交, 而是自该端点之后构造**第二特征序列**(元素=笔的区间), 按第78课要求
严格做包含处理, 寻找反向分型; 找不到则视为 A/B/C 应合并为一段, 该候选不成立继续扫描。
效果: 20 组数据中 3 个未获确认的缺口端点被正确剔除(70 -> 67 段); 与 Python 原版的纯划分
一致率 10/20 -> 9/20 —— 这是**朝原文方向**的预期变化(Python 原版并未实现该确认, 只用价格
突破近似)。

**线段阶段的工程补充保留**: `kbarGapAsXdFull`(0.618)、尾部推断、`gap_XD` 记账等按需求保留。

**已知残留**:
- 笔阶段与 Python 原版仍有 12/20 分歧(笔数量互有多寡), 直接限制线段一致率的上限;
- 笔完全相同的情况下仍有 2/8 数据集的线段不同(缺口路径细节);
- `CHAN_STANDARDIZE_XD=1` 视觉规整但不是"划分原样", 需要原样输出时设为 0。

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

### 收尾 (同日): 新笔默认 / 摘除诊断追踪 / 清理死状态

-  `CHAN_BI_MIN_SPAN` 默认 4 -> **3 (新笔)**; 需要老笔(原文第62课严格口径)时构建加 `-DCHAN_BI_MIN_SPAN=4`。
   实测: 笔更细 -> 线段 73 -> 95 段; 非极值端点 4.2% (持平); 标准化序列与原版一致 14/20 (不受影响);
   注: 与 Python 原版(用老笔)的"笔端点一致率"指标在此默认下不再可比, 对比时须同口径构建。
-  摘除 `CHAN_TRACE_STD` 逐步追踪: 含 `<cstdio>/<cstdlib>` 引入、`std_trace_on()`、`STRACE` 宏与其调用。
-  清理死状态: 合并时把 trend 写入 `tb` 的两处赋值 (方向已改为每次按当前K线重算, `tb` 不再承载 trend)。

### 最终定性: 标准化序列与 Python 基线的 6/20 差异

已定位到"元素上的粘滞方向"(b005 bar132/133): 规则层 434 步的 incl/first/second 两侧完全一致, 差异只在
两侧复用旧方向的取值不同。原文第62课只规定合并时按当前K线比较定方向, 未提复用 ⇒ 本插件每次重算的做法
符合原文, 该差异属**基线偏离原文**, 保留现状并在此记录, 不再追。

### 收尾 (同日): 少于三笔的相邻端点对不成线段 (线段待形成)

原文第65课"线段至少三笔": 若相邻两个端点的跨度不足三笔, 那一段尚未成为线段, 不应作为线段输出。
实现: defineXD 输出前新增一趟清理 —— 跨度不足 `CHAN_MIN_BI_SPAN` 的相邻端点对, 去掉后一个端点,
该段并入相邻线段待其形成; 随后重跑 `cleanXdMarks` 消除由此产生的同类型相邻。

实测 (20 组): 少于三笔的线段 1 -> **0**; 线段 95 -> 93; 非极值端点 4 (4.3%); 真实 600519 端点序列
与 Python 原版仍完全一致 (12 段, 0 个不足三笔)。

### 性能优化 (15000 根窗口) —— 全部通过逐字节等价验证

背景: 窗口由 6000 提到 15000 后单次计算从 43ms 涨到 5.6s。剖析发现主因不是缺口查询本身,
而是 defineXD 主循环在 >=9000 根时出现的"重放": 980 笔却跑出 35,664 轮 / 25,751 次"找到" /
8,955 次回退 (回退后从旧位置重扫, 把同一串端点重复提交)。

已落地 (每一步都与优化前的 27 个数据集 + 9000/12000/15000 三份参照逐字节比对, 全部相同):

1. 缺口查询索引化: detectGaps 里建 gap_prefix_ 前缀计数 + 日期非递减校验,
   gapExistsInRange/gapRegion 改按K线下标区间查询; 日期倒退时自动回退到原逐根扫描。
2. 删除线段阶段的 tb 死维护: applyCleanSequence 的 O(n) 清零循环、两处 restoreTbData
   (线段阶段只读 original_tb / xd_tb / 特征序列自身的 tb, working_df.tb 从不被读取)。
3. buildFeatureSeqInto: 主循环复用特征序列缓冲, 不再每轮重新分配。
4. processInclusions 由 O(L^2) 的 vector::erase 改为等价的"栈式"合并 (O(L)),
   保留 [0,start_offset) 前缀与"先判长度<6 再处理"的原有顺序。
5. A3: (tail_start, direction) -> 特征序列的 LRU 缓存 (96 条, 每次 defineXD 与 setData 时清空)。
   依据: 特征序列只依赖 original_tb / high / low (笔阶段后不变) 与方向; chan_price 回写幂等,
   同一键只需执行一次。findXDOnFeatureSeq 改为 const 引用 (已验证其从不修改序列)。

实测 (同一合成序列, 取 3 次最优):
  1500 -> 1.2ms | 3000 -> 4.2ms | 6000 -> 12.1ms | 9000 -> 82.9ms | 12000 -> 118.9ms | 15000 -> 161.2ms
  (优化前同尺寸: 6000 为 26ms, 15000 为 5631ms)

MAX_PROCESS_COUNT 6000 -> 15000 (Main.cpp)。
