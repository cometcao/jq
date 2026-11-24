# Schemas · 机器可读契约 · V2.120.0

> 本目录是"文档规则"的机器可读版本，供唯一校验实现 `dist/market-state/check.py` 与外部实现共用。文档仍是规则唯一来源；schema 只负责结构，语义规则由校验器补。

## 文件与对应章节

| 文件 | 对应文档 | 用途 |
|---|---|---|
| `fact.schema.json` | `docs/01_框架核心.md` 第四节 + 第五节 | 事实记录（含 subject/channel/proves/does_not_prove） |
| `compare.schema.json` | `docs/02_口径附件.md` 附录 B | 比价记录（七锚、operand_order、universe、reference） |
| `event.schema.json` | `docs/01_框架核心.md` 8.1 | 事件日历条目（三态、entry_mode、快照版本） |
| `scenario.schema.json` | `docs/01_框架核心.md` 8.2 | 事件分支枚举（可观测标志、受影响指标、排序不适用） |

## schema_version 策略

- schema 自身版本 **1.0.0**（本目录）；与文档版本（V2.13.x）**解耦**，各自演进。
- 破坏性改动（必填项增减、字段改名、枚举收敛）→ major +1；新增可选字段 → minor +1；描述修正 → patch +1。
- 记录的兼容性由**校验器**负责：读到 `schema_version` 不匹配时，按 minor 兼容规则自动降级/升级，major 不匹配则拒收并提示升级。

## 校验顺序（校验器必须按此顺序）

1. **结构**：JSON Schema 校验（四份 schema）。
2. **跨字段规则**（schema 表达不了的，见下表）。
3. **语义与口径**：查指标注册表（attribute/transform）、成分表版本（R1）、加总口径（R2）、跨版本（R3）。
4. **呈现**：`docs/05_输出与校验契约.md` 的 V-a…V-n。

## schema 表达不了、必须由校验器补的规则

| 规则 | 原因 |
|---|---|
| 同质锚（attribute + transform 均相同） | 需查指标注册表 |
| 归属锚（细层 ↔ 所属粗层 + 来源版本） | 需查成分表版本 |
| `operand_order` 的符号方向 | schema 只查非空，方向要靠工单约定（如"M2同比 − M1同比"） |
| 状态词是否在判定表内 | 需查第六节两张判定表 |
| stale 的 2 倍 / 3 倍阈值 | 需计算 `as-of − data_period` 与频率 |
| 空环是否保留 | 结构性检查（按六环顺序逐环比对） |
| 事实层列白名单 | 列级检查（同比/分位/排名等不得出现在事实层） |
| 禁用词与因果连词 | 词表匹配（V-d/V-k） |
| 事实域封闭（不得引用 `prev_value`） | 需追踪 inputs 的来源类型 |

## 与 golden 的关系

`examples/golden-market.md` 与 `examples/golden-sector.md` 是**语义基线**；本目录是**结构基线**。校验器要同时通过两者：结构不过 → 拒收；语义不过 → 拒输出该区块。
