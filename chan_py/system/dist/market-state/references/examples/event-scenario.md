# 事件分支 · 标准样例

> 版本 V2.146.0（与 `docs/` 8.1/8.2 同步）

> 两份：一份前值可得（可排序），一份前值不可得（排序不适用）。数值为示例。

## 样例 1 · CPI（前值可得）

**事件**：2026-12-05 CPI 同比（2026-11），issuer=国家统计局，`calendar_version=7`。

**前值三件核对**

| 检查 | 结果 |
|---|---|
| 口径同版本 | 2026-10 CPI 同比，口径未变 ✅ |
| 是否修正值 | 官方未修正，用初值 ✅ |
| 上期 vs 上年同期 | 用上期（2026-10 同比）✅ |

**分支**

| 分支 | 可观测标志 | 验证来源 | 受影响指标 |
|---|---|---|---|
| 高于前值 | 公布值 > 前值（0.4%） | 国家统计局 CPI 发布页 | `MKT_CPI_YOY` |
| 低于前值 | 公布值 < 前值（0.4%） | 同上 | `MKT_CPI_YOY` |
| 持平 | 公布值 = 前值（按公布精度 0.1pp） | 同上 | `MKT_CPI_YOY` |

排序：按公布值相对前值由高到低（高于 → 持平 → 低于）。
声明：以上为可能结果分支的枚举与可观测标志，不预测哪个分支会发生；影响指标为客观标注；价格印证由用户在外部平台完成。

**对应的记录（`scenario-1.json`）**

```json
{
  "event_id": "EV-2026-12-05-CPI",
  "event_summary": "CPI 同比（2026-11）",
  "observation_time": "2026-11-21T20:00+08:00",
  "calendar_version": 7,
  "prev_value": {
    "indicator_id": "MKT_CPI_YOY",
    "value": "0.4%",
    "data_period": "2026-10",
    "source_link": "https://www.stats.gov.cn/sj/zxfb/",
    "observation_time": "2026-11-21T20:00+08:00"
  },
  "possible_outcomes": [
    { "outcome_label": "高于前值", "observable_flag": "公布值 > 前值（0.4%）",
      "observable_flag_source": "国家统计局 CPI 发布页", "affected_indicators": ["MKT_CPI_YOY"] },
    { "outcome_label": "低于前值", "observable_flag": "公布值 < 前值（0.4%）",
      "observable_flag_source": "国家统计局 CPI 发布页", "affected_indicators": ["MKT_CPI_YOY"] },
    { "outcome_label": "持平", "observable_flag": "公布值 = 前值（0.4%，按 0.1pp 精度）",
      "observable_flag_source": "国家统计局 CPI 发布页", "affected_indicators": ["MKT_CPI_YOY"] }
  ],
  "branch_ordering": "按公布值相对前值由高到低",
  "branch_ordering_applicable": true,
  "no_prediction_statement": "以上为可能结果分支的枚举与可观测标志，不预测哪个分支会发生；影响指标为客观标注；价格印证由用户在外部平台完成。"
}
```

## 样例 2 · 解禁（前值不可得）

**事件**：某板块成分股的解禁（2026-12-10），此前无同口径解禁规模记录。

**处置**：`branch_ordering_applicable=false`，`branch_ordering` 写 **"不适用：前值不可得"**；分支仍可枚举（按公告执行 / 变更 / 取消），但**不排序**。

> 关键：**不推测前值**。没有"上一次解禁多少亿"就写"排序不适用"，不拿解禁市值或历史均值充当前值。

**对应的记录（`scenario-2.json`）**

```json
{
  "event_id": "EV-2026-12-10-UNLOCK",
  "event_summary": "板块成分股解禁",
  "observation_time": "2026-11-21T20:00+08:00",
  "calendar_version": 7,
  "possible_outcomes": [
    { "outcome_label": "按公告执行", "observable_flag": "实际解禁数量 = 公告数量",
      "observable_flag_source": "交易所公告", "affected_indicators": ["INST_INSIDER_NET"] },
    { "outcome_label": "变更", "observable_flag": "新增变更公告且数量 ≠ 原公告",
      "observable_flag_source": "交易所公告", "affected_indicators": ["INST_INSIDER_NET"] },
    { "outcome_label": "取消", "observable_flag": "出现取消公告",
      "observable_flag_source": "交易所公告", "affected_indicators": ["INST_INSIDER_NET"] }
  ],
  "branch_ordering": "不适用：前值不可得",
  "branch_ordering_applicable": false,
  "no_prediction_statement": "以上为可能结果分支的枚举与可观测标志，不预测哪个分支会发生；影响指标为客观标注；价格印证由用户在外部平台完成。"
}
```

## 三条硬规则（自查）

1. **标志必须机械可比**——"高于前值"可以，"好于预期"不行；
2. **受影响指标只标不判**——写 `MKT_CPI_YOY`，不写"CPI 走高压制估值"；
3. **分支不生成比价**——`prev_value` 只是分支定义的参照点，不能拿去和别的东西比。
