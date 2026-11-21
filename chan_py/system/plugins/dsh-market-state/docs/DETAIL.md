# 市场状态（dsh-market-state）

在 DSH 里把「市场状态」六环（C1–C6）直接摆出来，并能一键重建。

## 它做什么

- 读工作区里的两份证据报告，不重新抓数：
  - 市场层：`reports/<as-of>-market-state.md`
  - 板块层：`reports/<as-of>-sector-<目标板块>-state.md`（取文件名日期最新的一份）
- 把每份报告 ```代码块``` 里的证据行解析成「环 / 状态 / 数据期 / 依据 / 边界」四段结构化数据。
- 面板放在输入框下方（slot `conversation.composer.dock`），显示：
  - 当前层的 as-of 日期；
  - C1–C6 六枚环标签，同一环有多条证据时用 `·` 连接（例如 `C3 短端变贵 · 长端变贵`）；
  - 点某一环展开其「依据 / 边界」原文；
  - 「市场 / 板块」切换；
  - 「刷新」按钮。
- 「刷新」会用 `C:\miniconda3\envs\py311\python.exe scripts/state.py --layer <layer> --write` 重建两层的报告，然后重新读取并显示；每个层的结果（成功 / 退出码 / stderr 摘要）显示在面板底部。

## 面板与 Host 的接口

面板通过 Host 注册的一条精确路由取数，该路由挂在共享 web server 上：

| 方法 | 路径 | 行为 |
|---|---|---|
| `GET` / `HEAD` | `/dsh-market-state/state` | 返回两层解析结果（JSON） |
| `POST` | `/dsh-market-state/state` | 先重建（body 可带 `{"layers":["market","sector"]}` 限定层），再返回同样结构的 JSON 加 `refresh` 状态 |
| 其他 | 同上 | `405`，`Allow: GET, HEAD, POST` |

返回形状：

```json
{
  "ok": true,
  "generatedAt": "2026-11-21T23:20:00.000Z",
  "workspace": "C:\\Users\\comet\\git\\jq\\chan_py\\system",
  "layers": [
    { "layer": "market", "file": "reports/2026-11-20-market-state.md", "asOf": "2026-11-20", "target": null,
      "rows": [ { "ring": "C1", "state": "不变", "period": null, "evidence": "…", "boundary": "…" } ] },
    { "layer": "sector", "file": "reports/2026-11-20-sector-半导体-state.md", "asOf": "2026-11-20", "target": "半导体",
      "rows": [ ] }
  ],
  "labels": { "title": "市场状态", "refresh": "刷新", "…": "…" }
}
```

面板文字由 Host 随 payload 下发（按请求的 `Accept-Language` 选中文或英文），Client 端只保留一份「未连上路由时」的兜底文案。

## 配置

本版没有 `Config` 字段，避免把 schemastery 变成插件的运行时依赖。两个可选项用环境变量覆盖，重启 DSH 生效：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DSH_MARKET_STATE_WORKSPACE` | `C:\Users\comet\git\jq\chan_py\system` | 存放 `reports/`、`scripts/` 的工作区 |
| `DSH_MARKET_STATE_PYTHON` | `C:\miniconda3\envs\py311\python.exe` | 跑 `scripts/state.py` 的解释器（本机 `python` 不在 PATH 上） |

## 边界与已知限制

- **不抓数**：只读 `reports/` 里已有的报告；重建用的是已落盘的 facts，不触网。要新数据仍由 `scripts/fetch.py` 负责。
- **不做定时**：没有 cron / schedule；只有打开面板（GET）和点「刷新」（POST）两处触发。
- **不改现有逻辑**：`dist/market-state/**`、`docs/**`、`scripts/**` 全部只读。
- **无 web server 的 profile 不显示面板**：路由注册放在 `ctx.inject(['webServer'])` 里，没有该服务时插件仍可启用，但面板取数会显示「读取失败」。
- **路由不校验 cookie**：它注册为精确路由，优先于静态页的兜底路由；只在本机回环地址上提供 `reports/` 里的内容。
- **UI 文案未走 Client locale 服务**：文案由 Host 下发，未使用 `ctx.locale`。
