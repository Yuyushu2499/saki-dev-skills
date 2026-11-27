# 文档绘图引擎与可扩展适配器规范（Diagram Providers）

本文配合 `saki-docs` 使用，规定如何在文档中智能选择绘图方式、调用本机 **ExcalidrawZ MCP** 或 **Mermaid**，以及如何以插件化方式扩展接入其他绘图工具。

---

## 1. 场景化智能推荐规则（AI 自主判断，再弹窗确认）

凡在文档（如 `docs/architecture.md`、`docs/modules/*.md`、`README.md`）中需要配图时，先按以下规则判断最合适的绘图引擎，再通过 `ask_question` 把推荐引擎排在第一位标为 `(Recommended)` 供用户确认：

| 图表场景 | 推荐引擎 | 判断依据 |
| --- | --- | --- |
| 复杂系统架构全景图、多子系统/多端拓扑图、概念草图、需要高颜值视觉表达或手工微调排版的大图 | **ExcalidrawZ（本地 MCP）** | 自由布局空间大、视觉清晰度远高于纯文本自动排版，支持导出 SVG/PNG 并保留可编辑白板 |
| 简洁流程图、时序图（`sequenceDiagram`）、状态机（`stateDiagram-v2`）、ER 数据模型（`erDiagram`）、轻量类图、高频随代码同步的文档插图 | **Mermaid（Markdown 内嵌）** | 纯文本版本管理友好、Git diff 清晰、GitHub / IDE / Antigravity 原生免构建渲染 |
| 核心 `docs/architecture.md` 既要纯文本离线可读，又要高清白板便于评审与演示 | **两者都要** | Markdown 保留轻量 Mermaid 骨架，同时用 ExcalidrawZ 生成高清白板并按需导出图片 |

### 绘图前确认弹窗（`ask_question`）
每次准备绘图前（除非用户本次指令已明确指定“用 Mermaid 画”或“用 ExcalidrawZ 画”），调用 `ask_question` 弹出单选选项：
1. 将上述规则选出的最佳引擎放第一位并加 `(Recommended)` 前缀；
2. 其余内置引擎（`Mermaid` / `ExcalidrawZ` / `两者都要`）紧随其后；
3. 若本机偏好（`~/.saki-dev/preferences.md` 的 `## saki-docs`）或目标项目 `AGENTS.md` 注册了额外绘图后端，一并动态加入选项列表。

---

## 2. 内置引擎规范

### 2.1 `mermaid`（默认内嵌 Markdown 引擎）
- 使用标准围栏代码块 ` ```mermaid ` 直接写入目标 Markdown。
- 优先使用通用兼容度最高的图表类型：`flowchart TD` / `flowchart LR`、`sequenceDiagram`、`stateDiagram-v2`、`erDiagram`、`classDiagram`。
- 包含括号、冒号、斜杠等特殊字符的节点标签必须加双引号（如 `api["API Gateway (HTTP)"]`），避免渲染语法报错。

### 2.2 `excalidrawz`（macOS 本地 ExcalidrawZ MCP 引擎）
- **本机前置条件**：打开 macOS **ExcalidrawZ → 设置 → AI → MCP**，开启 **MCP 服务器**（推荐 **优化** 模式）。
- **Antigravity 接入配置**（写入本机全局 `~/.gemini/config/mcp_config.json`，不硬编码进业务项目或开源插件仓库）：
  ```json
  {
    "mcpServers": {
      "excalidrawz": {
        "url": "http://127.0.0.1:8490/mcp"
      }
    }
  }
  ```
  *（Antigravity 原生支持 Streamable HTTP，直接填 `url` 即可；若端口不同，按 ExcalidrawZ 连接面板显示的实际端口修改。）*
- **调用流程**：
  1. 检查当前会话工具清单中是否已加载 `excalidrawz` 相关 MCP 工具；
  2. **已连接时**：首次调用先执行 ExcalidrawZ MCP 自带的 `read_me` 工具获取当前可用工具与元素格式说明，再打开/新建画布并调用对应写工具（如 `replace_view` 等）绘制并合理分层排版；若用户需要把图片嵌入 Markdown，则导出为 SVG/PNG 存到文档同级 `assets/`（如 `docs/assets/<diagram-name>.svg`），并在 Markdown 中使用相对路径引用 `![图名](./assets/<diagram-name>.svg)`；
  3. **未连接或 ExcalidrawZ 未启动时**：如实提示用户打开 ExcalidrawZ 并确认 MCP 运行中，同时询问是否先回退为 Mermaid 绘制，绝不静默失败或假装已画完。

---

## 3. 扩展接入其他绘图工具（统一契约）

为保证长期可扩展性，`saki-docs` 不把绘图能力写死在 Mermaid 和 ExcalidrawZ 上。用户可通过**任意以下两种方式**登记新绘图后端（支持任意 MCP Server 或本地 CLI）：

1. **本机个人偏好**（`~/.saki-dev/preferences.md`）：
   ```markdown
   ## saki-docs

   - 扩展绘图工具：
     - `drawio`（MCP: drawio-mcp）：用于 UML / 网络拓扑图，导出至 `docs/assets/`
     - `d2`（CLI: `d2 <src.d2> <out.svg>`）：用于代码生成的清晰架构图
   ```
2. **项目级约定**（目标仓库 `AGENTS.md` / `GEMINI.md`）：声明项目统一使用的绘图引擎（如 `PlantUML`、`Graphviz dot`、`D2`、`Figma MCP`）及导出目录。

### 扩展引擎接入契约
无论接入哪种外部绘图工具，均遵循相同的输入输出约定：
- **输入**：图表目标与类型、核心节点与连接关系（全部来自已核实代码事实）、目标 Markdown 路径、资产导出目录（默认 `docs/assets/`）。
- **输出**：
  - 文本型 DSL（如 Mermaid / PlantUML / D2）：内嵌代码块或保存源文件 + 渲染产物；
  - 画布型工具（如 ExcalidrawZ / Draw.io / Figma MCP）：生成/更新画布，并按需导出 SVG/PNG 相对路径嵌入 Markdown，同时记录源文件或画布名称以便后续增量维护。
