# kBar_Chan.py — Plan A 重构计划

> 创建日期: 2026-05-05
> 参考: `ChanTheory_Compliance_Analysis.md` (C++ Plan A/v2 合规性分析)
> 目标: 将 kBar_Chan.py 的 `find_XD`/`defineXD` 从"删除法"重构为"合并法", 贴近缠论原文

---

## 1. 背景

### 1.1 演化路径

```
kBar_Chan.py (Python 原版, 删除法)
    ↓ 翻译
ChanAnalyzer.cpp (C++ 初版, 14个Bug修复, 对齐Python)
    ↓ Plan A (2026-04-26)
FeatureSeqElement 合并法 (price/orig_price 分离)
    ↓ 方向感知修复 (2026-04-27)
processInclusions + mergeFeatureSeqPair 按 direction 合并
    ↓ Plan v2 (2026-04-28)
多段迭代重建 (每段独立 build→merge→detect→advance)
    ↓ 2026-04-28 fix
applyCleanSequence chan_price 全量刷新
    ↓ 2026-04-30 fix
非单调 orig_market_idx 修复 (is_kg2_backstep)
    ↓
当前 C++ 版本 (成熟)
```

### 1.2 Python 当前状态

| 模块 | 状态 | 说明 |
|------|------|------|
| `standardize` | ✅ 合规 | `trend_type` 存储趋势方向, 链式包含正确 |
| `markTopBot` | ✅ 合规 | 检测逻辑正确, 允许 K 线共用在 defineBi 中清理 |
| `defineBi` | ✅ 合规 | `same_tb_remove_*`, `check_gap_qualify`, `work_on_end` 完整 |
| **`find_XD` / `defineXD`** | ⚠ 删除法 | **需要重构** |

### 1.3 核心差异: 删除法 vs 合并法

| 维度 | Python 当前 (删除法) | C++ 当前 (合并法) |
|------|---------------------|-------------------|
| 包含处理 | `is_XD_inclusion_free` 删除 2 个元素 (tb=NO_TOPBOT) | `mergeFeatureSeqPair` 合并 4→2 (保留极值) |
| 包含检查 | `check_inclusion_by_direction` 迭代删除 | `processInclusions` 单趟扫描+回退合并 |
| 价格语义 | `chan_price` 身兼判断和检测二职 | `price`(判断) / `orig_price`(检测) 分离 |
| XD 检测 | `find_XD` 单次 while, 方向切换后用残值 | `defineXD` 多段迭代, 每段独立 build→merge→detect |
| 合并方向 | `is_XD_inclusion_free` 方向只决定删哪两个, 不决定合并价格 (BUG) | 方向统一 MAX/MIN (上升全 max, 下降全 min) |
| 非合并元素 chan_price | 不适用 (被删除的元素无法恢复) | `applyCleanSequence` 全量刷新 |

---

## 2. 更改概览 (5 项改动 A→E)

### 改动 A: 新增特征序列合并系统

**新增函数**:

| 函数 | 行数 | 替代的旧函数 |
|------|------|------------|
| `build_feature_seq()` | ~20 | — (新) |
| `_has_feature_inclusion()` | ~5 | `xd_inclusion()` (沿用, 改用 price 字段) |
| `merge_feature_seq_pair()` | ~30 | `is_XD_inclusion_free()` 的删除分支 |
| `process_inclusions()` | ~25 | `check_inclusion_by_direction()` |
| `apply_clean_sequence()` | ~20 | — (新) |

**保留的旧函数**:

| 函数 | 状态 |
|------|------|
| `xd_inclusion()` | 保留 (`kbar_gap_as_xd` 等内部使用 `chan_price`, 不使用 feature_seq 的 `price`) |
| `is_XD_inclusion_free()` | **删除** (被 merge_feature_seq_pair 替代) |
| `check_inclusion_by_direction()` | **删除** (被 process_inclusions 替代) |

### 改动 B: 方向感知修复

- `merge_feature_seq_pair`: 按线段方向统一合并操作符 (BOT2TOP→全部 MAX, TOP2BOT→全部 MIN)
- `process_inclusions`: 按 direction 跳到正确类型起点 (上升→首个 TOP, 下降→首个 BOT)

### 改动 C: 多段迭代重建

- **新增** `find_xd_on_feature_seq()`: 纯滑动窗口 XD 端点检测 (从 feature_seq 的 orig_price 读取)
- **重写** `defineXD()`: 多段迭代循环

```
defineXD 迭代循环:
  1. build_feature_seq(working_df, tail_start)
  2. process_inclusions(feature_seq, direction)
  3. apply_clean_sequence(feature_seq, working_df, tail_start)
  4. find_xd_on_feature_seq(feature_seq, working_df, direction)
     → 返回 XDFindResult
  5. popGap 检查 → 回退 tail_start, flip direction, continue
  6. prev_xd 验证 → 回退 tail_start, clear prev_xd, flip direction, continue
  7. 记录 xd_tb, 管理 gap_XD
  8. clamp tail_start (改动E)
  9. flip direction, continue
```

- **删除** `find_XD()` (被 defineXD 迭代循环 + find_xd_on_feature_seq 替代)

### 改动 D: chan_price 全量刷新

`apply_clean_sequence` 中, **所有** feature_seq 元素的 `chan_price` 都写入 `elem.orig_price`, 不只是 `is_merged` 的元素。

**根因**: 多段迭代中, 前一段的 `apply_clean_sequence` 可能已将某位置的 `chan_price` 设为前一段方向的合并值。当前段该元素非合并时, 若不刷新, 会残留错误方向的合并价格。

### 改动 E: 非单调 orig_market_idx 修复

- `merge_feature_seq_pair` 中, 合并后 `orig_market_idx` 可能非单调 (两个合并元素一个取较大索引, 一个取较小索引)
- `find_xd_on_feature_seq` 返回 `is_kg2_backstep` 标志
- `defineXD` 循环中 clamp: 非 kg2 退行时, `tail_start = max(tail_start, xd_market_idx)`

---

## 3. 函数签名速查

### 3.1 新增函数

```python
def build_feature_seq(self, working_df, start_loc):
    """从 original_tb + high/low 构建特征序列元素列表"""

def _has_feature_inclusion(self, e0, e1, e2, e3):
    """检查两对特征序列元素是否存在包含关系 (使用 price 字段)"""

def merge_feature_seq_pair(self, feature_seq, i, direction):
    """合并 i 和 i+2 (pair 1), i+1 和 i+3 (pair 2), 4→2"""

def process_inclusions(self, feature_seq, direction):
    """按方向处理特征序列包含, 合并 (4→2) 替代删除"""

def apply_clean_sequence(self, feature_seq, working_df, start_loc):
    """将合并后的特征序列写回 working_df, 清除 tb, 全量刷新 chan_price"""

def find_xd_on_feature_seq(self, feature_seq, working_df, direction):
    """在已清理的特征序列上做滑动窗口 XD 检测, 返回 XDFindResult dict"""
```

### 3.2 重写函数

```python
def defineXD(self, initial_status=TopBotType.noTopBot):
    """多段迭代: rebuild → merge → detect → advance → flip"""

def _xd_tail_inference(self, working_df, direction):
    """尾部推断 (从原 find_XD 尾部提取)"""
```

### 3.3 删除函数

```python
def is_XD_inclusion_free(self, ...)    # 删除, 替代: merge_feature_seq_pair
def check_inclusion_by_direction(self, ...)  # 删除, 替代: process_inclusions
def find_XD(self, ...)                 # 删除, 替代: defineXD + find_xd_on_feature_seq
```

### 3.4 保留不变函数

```python
def kbar_gap_as_xd(self, ...)          # 保留 (内部使用 working_df, 非 feature_seq)
def check_XD_topbot(self, ...)         # 保留 (find_xd_on_feature_seq 内联替代, 但保留供参考)
def check_kline_gap_as_xd(self, ...)   # 保留 (find_xd_on_feature_seq 可能内联)
def check_previous_elem_to_avoid_xd_gap(self, ...)  # 保留 (find_xd_on_feature_seq 中调用)
def pop_gap(self, ...)                 # 保留 (defineXD 迭代循环中调用)
def xd_topbot_candidate(self, ...)     # 删除 (不再需要, 合并法不需要 candidate 预检)
def restore_tb_data(self, ...)         # 保留 (popGap/prev_xd 回退时使用)
def direction_assert(self, ...)        # 保留
```

---

## 4. 数据流对比

### 4.1 当前 (删除法)

```
defineXD
  └→ find_XD (单次 while)
       ├→ check_inclusion_by_direction (迭代删除)
       │    └→ is_XD_inclusion_free (删除 2 个元素, tb=NO_TOPBOT)
       ├→ xd_topbot_candidate (预检候选)
       ├→ check_XD_topbot_directed (XD 检测)
       ├→ pop_gap (缺口回退)
       └→ 尾部推断
```

### 4.2 目标 (合并法 + 多段迭代)

```
defineXD
  ├→ gap_XD = []; tail_start = initial_i
  └→ loop:
       ├→ build_feature_seq(tail_start)       # 从 original_tb, high, low 重建
       ├→ process_inclusions(seq, direction)   # 按方向合并
       ├→ apply_clean_sequence(seq, tail_start) # 写回 + 刷新 chan_price
       ├→ find_xd_on_feature_seq(seq, direction) # 滑动窗口检测
       ├→ popGap / prev_xd 验证 (回退机制)
       ├→ 记录端点 + clamp tail_start (改动E)
       └→ flip direction, advance
  └→ _xd_tail_inference (尾部推断)
```

---

## 5. 实施顺序

| 步骤 | 内容 | 优先级 |
|------|------|--------|
| 1 | 新增 `build_feature_seq`, `_has_feature_inclusion` | 🔴 基础 |
| 2 | 新增 `merge_feature_seq_pair` | 🔴 基础 |
| 3 | 新增 `process_inclusions` | 🔴 基础 |
| 4 | 新增 `apply_clean_sequence` | 🔴 基础 |
| 5 | 新增 `find_xd_on_feature_seq` (全量滑动窗口检测) | 🔴 核心 |
| 6 | 新增 `_xd_tail_inference` (从原 find_XD 尾部提取) | 🟡 尾部 |
| 7 | 重写 `defineXD` 为迭代循环 | 🔴 核心 |
| 8 | 删除 `is_XD_inclusion_free`, `check_inclusion_by_direction`, `find_XD`, `xd_topbot_candidate` | 🟡 清理 |
| 9 | 验证语法 (`python -m py_compile`) | 🔴 必须 |

---

## 6. FeatureSeqElement 数据结构

```python
# feature_seq 中每个元素是一个 dict:
{
    'tb': int,              # TopBotType.top.value or TopBotType.bot.value
    'price': float,         # 方向合并值, 用于包含判断 (上升→max, 下降→min)
    'orig_price': float,    # 原始市场极值, 用于 XD 端点检测 (永不丢失)
    'orig_market_idx': int, # working_df 中的原始索引
    'is_merged': bool       # 是否参与了合并
}
```

---

## 7. find_xd_on_feature_seq 详细逻辑

```
find_xd_on_feature_seq(feature_seq, working_df, direction):

  target_tb = (direction == BOT2TOP) ? TOP : BOT
  i = 定位首个 target_tb 的元素位置
  if i + 5 >= len(feature_seq): return {found=False}

  while i + 5 < len(feature_seq):
    e0, e1, e2, e3, e4, e5 = feature_seq[i:i+6]

    # --- 标准 XD 检测 ---
    if direction == BOT2TOP (上升, 找 TOP):
      条件 = e2.tb==TOP &&
             orig_price(e2) > orig_price(e0) &&
             orig_price(e2) > orig_price(e4) &&
             orig_price(e3) > orig_price(e5)
      xd_type = TOP
      with_gap = orig_price(e0) < orig_price(e3)
    else (下降, 找 BOT):
      条件 = e2.tb==BOT &&
             orig_price(e2) < orig_price(e0) &&
             orig_price(e2) < orig_price(e4) &&
             orig_price(e3) < orig_price(e5)
      xd_type = BOT
      with_gap = orig_price(e0) > orig_price(e3)

    # --- K线缺口 XD 检测 ---
    if not 标准XD_found:
      kg2 = 检查 kline_gap_as_xd (映射 orig_market_idx → working_df → kbar_gap_as_xd)
      if kg2: xd_type = kg2_type, with_gap = True

    if xd_type != noTopBot:
      # prev_xd 验证 → 不通过则返回 {found=False, rollback=prev_xd_idx}
      # check_previous_elem_to_avoid_xd_gap → 闭合 gap 检查
      new_i = i + 1 if kg2 else i + 3
      return {
        found: True,
        xd_market_idx: feature_seq[i+2].orig_market_idx,
        xd_type: xd_type,
        with_gap: with_gap,
        next_market_start: feature_seq[new_i].orig_market_idx,
        is_kg2_backstep: (new_i == i + 1)
      }

    i += 1

  return {found: False}
```

---

## 8. 风险与注意事项

1. **`kbar_gap_as_xd` 适配**: 原函数使用 `working_df` 和 `chan_price`。在 feature_seq 版本中, 需要通过 `orig_market_idx` 映射回 `working_df` 获取 date/chan_price。需要在 `find_xd_on_feature_seq` 中添加这个映射逻辑, 或写一个适配版本 `kbar_gap_as_xd_feature_seq`。

2. **`pop_gap` 适配**: 原函数使用 `working_df` 和 `chan_price`。在 feature_seq 版本中, 需要保持原样 (因为 popGap 操作 working_df 的 xd_tb 和 tb)。放在 `defineXD` 循环中处理, 不进入 `find_xd_on_feature_seq`。

3. **`previous_with_xd_gap` 状态管理**: 这个变量在 `check_kline_gap_as_xd` (原) 中管理。在 feature_seq 版本中, 它应该放在 `defineXD` 的循环中, 跨迭代持留 (只清零一次)。`find_xd_on_feature_seq` 读取和修改它 (通过引用或作为类成员)。

4. **`restore_tb_data`**: popGap 回退时需要恢复 `tb = original_tb`。在新的合并法架构中, 因为 `apply_clean_sequence` 已经清除了 `tb`, `restore_tb_data` 的行为可能需要适配 (从 `original_tb` 恢复)。但在合并法中, 回退后下一轮 rebuild 会从 `original_tb` 重建, 所以 `restore_tb_data` 的恢复可能是多余的但无害。保留它以兼容 gap_XD 路径中的 popGap。

5. **尾部推断**: 原 `find_XD` 的尾部推断 (line 1687-1785) 需要完整迁移到 `_xd_tail_inference`, 使用 `working_df` 的 `chan_price`/`tb`/`original_tb` 字段 (这些在 `apply_clean_sequence` 后仍然可用, 因为 `orig_price` 是最后一段方向正确的合并值)。

6. **`xd_topbot_candidate` 删除**: 合并法不需要 candidate 预检, 因为包含关系在 `process_inclusions` 中已经处理完毕, `find_xd_on_feature_seq` 直接在清理后的序列上做滑动窗口检测。

7. **与 `getFenDuan` 的兼容性**: `getFenDuan` 调用 `self.defineXD(initial_state)`, 返回值预期是 `self.kDataFrame_xd`。重写后保持相同的接口和行为。

---

## 9. 预期结果

| 对比项 | 修改前 (删除法) | 修改后 (合并法) |
|--------|---------------|----------------|
| 包含处理 | 删除被包含元素 (tb=NO_TOPBOT) | 合并 4→2, 保留极值 |
| 极值保留 | 被删元素的极值永久丢失 | `orig_price` 始终保留市场最极值 |
| 合并方向 | 方向只决定删哪两个 (不控制合并价格) | 方向统一 MAX/MIN |
| 方向切换后价格 | 旧方向的值继续使用 (可能错误) | 每段独立 rebuild + 重合并 |
| 非合并元素 chan_price | 不适用 | 全量刷新, 无前段残留 |
| 索引非单调 | 不适用 (无合并) | is_kg2_backstep + clamp |
| 缠论对应 | 删除法 ≠ 原文"合并" | 合并法 = 原文规则 |
