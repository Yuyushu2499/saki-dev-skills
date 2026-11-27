# 文档绘图引擎与可扩展适配器规范（Diagram Providers）

本文配合 `saki-docs` 使用，规定如何在文档中智能选择绘图方式、调用本机 **ExcalidrawZ MCP** 或 **Mermaid**、规范文件命名与存储落盘，以及如何扩展接入其他绘图工具。

---

## 1. 场景化智能推荐规则（AI 自主判断，再弹窗确认）

凡在文档（如 `docs/architecture.md`、`docs/modules/*.md`、`README.md`）中需要配图时，先按以下规则判断最合适的绘图引擎，再通过 `ask_question` 把推荐引擎排在第一位标为 `(Recommended)` 供用户确认：

| 图表场景 | 推荐引擎 | 判断依据 |
| --- | --- | --- |
| 复杂系统架构全景图、多子系统/多端拓扑图、概念草图、需要高颜值视觉表达或手工微调排版的大图 | **ExcalidrawZ（本地 MCP）** | 自由布局空间大、视觉清晰度远高于纯文本自动排版，导出 PNG 所见即所得不跑版，同时保留可编辑 `.excalidraw` 源文件 |
| 简洁流程图、时序图（`sequenceDiagram`）、状态机（`stateDiagram-v2`）、ER 数据模型（`erDiagram`）、轻量类图、高频随代码同步的文档插图 | **Mermaid（Markdown 内嵌）** | 纯文本版本管理友好、Git diff 清晰、GitHub / IDE / Antigravity 原生免构建渲染 |
| 核心 `docs/architecture.md` 既要纯文本离线可读，又要高清白板便于评审与演示 | **两者都要** | Markdown 保留轻量 Mermaid 骨架，同时用 ExcalidrawZ 生成高清白板并导出 PNG |

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

#### 存储目录与命名标准
1. **项目仓库落盘目录（默认随 Git 托管）**：统一存放在目标仓库的 **`docs/assets/diagrams/`** 下。
2. **文件命名规范（严格小写英文 kebab-case）**：
   - 格式：`<范围或模块>-<图类型>.<扩展名>`（仅多张强顺序图时加两位序号前缀 `01-`、`02-`）
   - 统一 `<图类型>` 词表：
     - `architecture`（系统/模块架构）
     - `flow`（业务或调用流程）
     - `sequence`（交互时序）
     - `data-model`（数据模型/存储结构）
     - `topology`（部署/多端拓扑）
     - `state`（状态机流转）
   - 同名配对示例：
     - 可编辑源文件：`docs/assets/diagrams/system-architecture.excalidraw`
     - Markdown 嵌入图：`docs/assets/diagrams/system-architecture.png`
     - 模块流程图：`docs/assets/diagrams/export-pipeline-flow.excalidraw` + `export-pipeline-flow.png`
3. **ExcalidrawZ iCloud 图库画布名**（仅当未授权 Local Folder 而使用图库模式时）：
   - 优先通过 `list_groups` 放入与项目同名的分组（无对应分组时提示用户建立），画布命名为：`[<项目名>] <模块或主题> - <图类型>`（如 `[saki-dev-skills] 系统架构 - architecture`），避免不同项目重名混淆。
4. **导出格式与视觉质量**：
   - **默认导出 `.png`**（高清、带纯色背景，避免 GitHub 深色模式下黑线隐身，且彻底规避跨平台中文字体回退跑版问题）；仅在用户显式指定矢量格式时改导出 `.svg`。
   - **默认保留 `.excalidraw` 源文件**在 `docs/assets/diagrams/` 中与 `.png` 严格同名配对，确保随时可重新打开增量编辑。
   - **Markdown 引用**：统一使用相对路径（如 `![系统架构图](./assets/diagrams/system-architecture.png)`），方便 `saki-govern` 自动做死链校验。

#### 三级图标与视觉表现规范（拒绝纯方框）
绘制架构图、流程图或系统拓扑图时，只要涉及具体软件、平台、数据库、外部服务或特色角色，**不得清一色只用单调白方框**，按以下三级优先级配图：

1. **第一优先：ExcalidrawZ 素材库（最原生）**
   - 绘图前先调用 `list_libraries` / `list_library_items` 检索用户素材库中的匹配图标；
   - 命中后直接用 `add_library_item_to_canvas(library_id, item_id, x, y)` 摆放到画布，再用 `adjust_elements` 调整连线与标注（**注意**：`replace_view` 会清空画布上的已有图片与素材库元素，贴完图标后严禁再用 `replace_view` 覆盖）。
2. **第二优先：嵌入真实 PNG/SVG 品牌 Logo 或自定义配图（`excalidraw_icons.py`）**
   - 图标优先从本机共享图标仓 `~/.saki-dev/icons/` 与项目内 `assets/` / `docs/assets/icons/` 查找（可先跑 `python3 "$SKILL_DIR"/scripts/excalidraw_icons.py list-icons`）；缺少特色配图时可调用 Antigravity `image-generator` 生成简洁配图，或生成标准简洁矢量 SVG 图标。
   - 推荐流水线：先在 ExcalidrawZ 用 `replace_view` 画好整体布局、文字、箭头与带标记的占位框（占位框标签写 `icon:<名称>`，如 `icon:github`、`icon:excalidrawz`），导出或落盘为 `docs/assets/diagrams/<name>.excalidraw` → 运行：
     ```text
     python3 "$SKILL_DIR"/scripts/excalidraw_icons.py replace-placeholders \
       docs/assets/diagrams/<name>.excalidraw \
       --icon-dir docs/assets/icons
     ```
     脚本会自动把占位框原地替换为等比居中的标准 Excalidraw `image` 元素（内嵌 base64 `dataURL`）并**保留指向占位框的所有箭头绑定** → 再在 ExcalidrawZ 中打开验证与导出高清 `.png`（注意：若原文件正处于 ExcalidrawZ 打开状态，直接改磁盘文件不会触发内存画布重载，需另存一个新文件名再调 `open_local_file` 载入后导出，完事后清理临时文件）。
3. **第三优先（无对应品牌 Logo 时的兜底视觉层次）**
   - 按语义区分形状与柔和色板：核心协调者用醒目主色圆角框或自由大字节点（如 `Router` → `Worker`），外部服务用虚线分组框，数据存储用椭圆/圆柱组合，辅以简洁中文说明与箭头标注。

#### 标准调用与增量更新流程
1. 检查当前会话工具清单中是否已加载 `excalidrawz` 相关 MCP 工具；未连接或 ExcalidrawZ 未启动时，如实提示用户打开 ExcalidrawZ 并询问是否先回退为 Mermaid，绝不静默失败。
2. **首次调用先执行 `read_me` 与 `list_libraries`** 获取当前工具说明与用户已有素材库。
3. **新建或打开源文件**：
   - 先查 `list_local_folders`：若目标仓库目录已授权，优先用 `create_local_file` / `open_local_file` 直接操作 `docs/assets/diagrams/<name>.excalidraw`；
   - 未授权 Local Folder 时，在 iCloud 图库中用 `create_file` / `open_file` 绘制，再通过 `export(kind="file")` 与 `export(kind="image", format="png", export_scale=2, with_background=true)` 落盘到 `docs/assets/diagrams/`。
4. **绘制、嵌图、原地更新与视觉自检**：
   - 全新绘图或大幅重排用 `replace_view`；既有图或含图标/素材库元素的画布做局部调整时用 `adjust_elements` **原地更新**（直接覆盖同名 `.png` 与 `.excalidraw`，严禁堆积 `v1 / v2 / final` 副本）。
   - 需要嵌入真实 PNG/SVG 图标时，按上方 `excalidraw_icons.py` 流水线替换占位框后再打开校验。
   - 每次绘图或修改完成后，必须调用 **`read_canvas_image`** 检查画面排版（无文字截断、无框线重叠、箭头方向清晰、背景可读），确认无误再导出落盘并写入 Markdown 引用。

---

## 3. 扩展接入其他绘图工具（统一契约）

为保证长期可扩展性，`saki-docs` 不把绘图能力写死在 Mermaid 和 ExcalidrawZ 上。用户可通过**任意以下两种方式**登记新绘图后端（支持任意 MCP Server 或本地 CLI）：

1. **本机个人偏好**（`~/.saki-dev/preferences.md`）：
   ```markdown
   ## saki-docs

   - 扩展绘图工具：
     - `drawio`（MCP: drawio-mcp）：用于 UML / 网络拓扑图，导出至 `docs/assets/diagrams/`
     - `d2`（CLI: `d2 <src.d2> <out.png>`）：用于代码生成的清晰架构图
   ```
2. **项目级约定**（目标仓库 `AGENTS.md` / `GEMINI.md`）：声明项目统一使用的绘图引擎（如 `PlantUML`、`Graphviz dot`、`D2`、`Figma MCP`）及导出目录。

### 扩展引擎接入契约
无论接入哪种外部绘图工具，均遵循相同的输入输出约定：
- **输入**：图表目标与类型、核心节点与连接关系（全部来自已核实代码事实）、目标 Markdown 路径、资产导出目录（默认 `docs/assets/diagrams/`）。
- **输出**：
  - 文本型 DSL（如 Mermaid / PlantUML / D2）：内嵌代码块或保存源文件 + 渲染产物；
  - 画布型工具（如 ExcalidrawZ / Draw.io / Figma MCP）：生成/更新画布，默认在 `docs/assets/diagrams/` 保留同名源文件与 `.png` 导出图（按 `<模块>-<图类型>` 命名），并以相对路径嵌入 Markdown。
