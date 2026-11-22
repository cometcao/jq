# market-state · 独立 Skill 包

> 规则版本：**V2.60.1**（源自 `docs/`；升级主文档时须同步本包的 `references/data-layer.md   数据层：优先级、档位、as-of、修订
references/`）

一个自包含的 DSH Skill：把当前数据压缩成"六环 + 证据行"的客观状态描述，不做判断、不给建议、不预测。

## 装到哪里

DSH 的 Skill 用**目录包**形式被发现（`<根>/skills/<name>/SKILL.md`）。把它复制到任一扫描根即可：

```powershell
# 用户级（对所有项目生效）
Copy-Item .\market-state "$env:USERPROFILE\.dsh\skills\" -Recurse

# 或项目级（只对某个 git 仓库生效）
Copy-Item .\market-state "<repo>\.dsh\skills\" -Recurse
```

放好之后不用重启：文件系统 provider 会监听目录，新 Skill 进入下一轮目录。

## 包里有什么

| 路径 | 作用 |
|---|---|
| `SKILL.md` | 主干：何时用、输入、七步流程、输出格式、失败态、禁止 |
| `references/framework.md` | 六环 × 两层、每环逻辑理由、R1–R3 |
| `references/reading-rules.md` | L1–L6、两张判定表、证据行、禁用清单 |
| `references/anchors.md` | 七锚、算子白名单、默认窗口、stale 阈值 |
| `references/events.md` | 事件面：日历三态、确定性标准、分支三支、前值三件核对 |
| `references/render.md` | 渲染契约：六环覆盖条（默认）、并排小格（多标的）、折线（按需，≤1 条） |
| `references/registry.json` | 53 条指标（attribute / transform / 量纲 / 频率） |
| `references/schema/*.json` | 事实、比价、事件、分支四份 JSON Schema |
| `references/examples/` | 两份 golden + 真实跑通 + 事件日历/分支样例（含 9 条记录） |
| `check.py` | 自检：记录（结构 + 语义）与页面（证据行 + 措辞） |

## 自检

```powershell
python check.py --demo                                        # 8 个用例
python check.py --page output.md                              # 校验输出正文
python check.py --as-of 2026-11-21 references/examples/real-01/*.json
```

当前状态：`--demo` 8/8 PASS；`--page` 对两份 golden 与真实跑通报告均 0 错误。


## 唯一校验实现

仓库里**只有这一份校验实现**（原 `validator/validate.py` 已于 V2.60.1 合并进来）。它同时承担两件事：

- **仓库测试**：对本仓 `examples/` 下的记录与页面做回归；
- **Skill 自检**：Skill 输出前自查（`--page` 与记录模式）。

**同步点**：`references/registry.json` 由 `docs/09_指标本体表.md` 生成；`docs/09` 增删指标后，须重跑下面的生成片段（否则 Skill 会按旧注册表校验）：

```python
# 在仓库根执行：重新生成 references/registry.json
import io, json, re
rows = {}
for line in io.open("docs/09_指标本体表.md", encoding="utf-8"):
    if not line.startswith("|"): continue
    c = [x.strip() for x in line.strip().strip("|").split("|")]
    if len(c) < 8 or not re.match(r"^[A-Z]{2,6}_[A-Z0-9_]+$", c[0]): continue
    rows[c[0]] = {"name": c[1], "layer": c[2], "channel": c[3], "subject": c[4],
                  "attribute": c[5], "transform": c[6], "value_kind": c[7],
                  "unit": c[8] if len(c) > 8 else None, "frequency": c[9] if len(c) > 9 else None,
                  "comparable_from": None}
rows["MKT_M1_YOY"]["comparable_from"] = "2024-01-01"
io.open("dist/market-state/references/registry.json", "w", encoding="utf-8").write(
    json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
```

## 本期覆盖

**已覆盖**：市场层六环、板块层六环（含 R1–R3）、比价（七锚）、空环与 stale 标注、证据行输出、自检。
**未覆盖**：事件面（日历 + 分支枚举）——接口已留，下一版补齐。
