---
name: saki-docs
description: "基于真实代码生成项目文档，并随功能/需求迭代按 git diff 增量维护活文档（README、架构、接口/数据契约、模块说明、ADR 与变更记录）。中途接手项目需要通读代码生成文档，或完成功能开发后需要同步更新项目文档时使用；不用于文档死链体检与瘦身治理（saki-govern）、只读查代码（saki-explore）或写开发方案（saki-plan）。"
license: MIT
metadata:
  version: "1.0.0"
---

# saki-docs

`SKILL_DIR` 指当前 Skill 的绝对目录；`<python>` 指 Python 3.10+（macOS/Linux 通常为 `python3`，Windows 通常为 `py -3`）；`DOC_HELPER` 是 `<python> "$SKILL_DIR"/scripts/doc_helper.py` 的简写。

## 核心规则

- **默认使用中文写作**：除非用户在对话中显式指定其他语言（如“用英文写 README”），否则所有新建与补充的项目文档内容默认使用简体中文。
- **只维护“活文档”，拒绝需求流水账**：文档反映的是**系统当前的真实状态**，不把一次性需求单永久堆进 `docs/features/`。采用行业标准的 **2 核心 + 4 按需** 体系（详见 [文档体系与写作模板](references/doc-templates.md)），绝不生成没有内容的空模板文件。
- **先列清单确认，再落盘写入（半自动低摩擦）**：无论是中途接手从零生成文档，还是随需求改动做增量同步，动手写文件前都先用几行列出**准备新建/修改哪几份文档、每份改什么**，经用户确认后再落盘。
- **100% 以真实代码和 `git diff` 为事实源，零臆测**：所有入口路径、命令、配置项、接口字段必须从源码、清单或 CI 中真实核实；代码里看不出来的业务背景或外部约定显式标注 `[待补充]`，严禁脑补。
- **精准局部更新，不无故重写全文**：增量同步时只更新与本次变更相关的段落与引用，保留原有风格和未受影响的内容；`L1` 内部重构、小样式微调或不影响外部行为/目录/契约的小修补直接判定为“无需更新文档”，不制造噪音 diff。
- **单源维护，绝不撑爆 `AGENTS.md` / `GEMINI.md`**：详细架构、接口与模块文档落在 `README.md` 和 `docs/` 中；根目录 `AGENTS.md` / `GEMINI.md` 仅在路由表中通过相对链接指向这些文档，绝不把长篇文档抄进常驻规则文件。
- **智能绘图与可扩展引擎**：文档需要配图（架构图、流程图、数据流图等）时，结合图表复杂度与维护形态自主判断更适合 **Mermaid** 还是本机 **ExcalidrawZ MCP**（或已扩展的其他绘图工具），并通过 `ask_question` 弹出带 `(Recommended)` 推荐项的选项卡片请用户确认后再绘（详见 [文档绘图引擎规范](references/diagram-providers.md)）。
- **默认纯 Antigravity 内部闭环**：接手大仓库需要并行读源码时，默认使用 `invoke_subagent` 派发只读子 Agent **`saki-explorer`**（`Model: "flash"`，未注册时退回 `research`），不自动触发 `saki-delegate` 或外部 CLI。

## 先选文档模式

| 模式 | 适用场景 | 执行路径 | 默认停止点 |
| --- | --- | --- | --- |
| **接手项目生成（Bootstrap）** | 中途接手陌生仓库，或仓库缺少基础文档需要从代码反推 | `DOC_HELPER inventory` → `saki-explorer` 并行读核心源码 → 给出文档规划清单与大纲 → 用户确认后落盘 | 完成文档写入并提议挂入 `AGENTS.md` 路由表 |
| **随需求增量同步（Sync）** | 功能开发完成/审查通过准备合并，或用户要求按近期改动同步文档 | `DOC_HELPER impact` 分析真实 diff 与文档引用 → 过滤无外部影响的噪音改动 → 列受影响文档与改动摘要 → 用户确认后局部更新 | 完成精准增量更新并核对相对链接 |
| **定向撰写 / ADR** | 用户指定补写某一份文档（如 `docs/api.md`、`docs/modules/<x>.md` 或一条架构决策记录 ADR） | 核实对应模块源码与已有文档 → 确认大纲与写入位置 → 精准撰写 | 完成单篇文档写入与路由更新 |

## 推荐文档体系（2 核心 + 4 按需）

| 层级 | 路径 | 何时创建/维护 |
| --- | --- | --- |
| **核心必选** | `README.md` | 所有项目：用途、核心能力、环境依赖、安装/运行/测试/构建命令、顶层目录一览 |
| **核心必选** | `docs/architecture.md` | 中型及以上或接手项目：模块职责、核心调用链与数据流（配 Mermaid 图）、关键外部依赖 |
| **按需生长** | `docs/api.md` / `docs/data-model.md` | 存在对外 HTTP/RPC 接口、CLI 参数、配置项或持久化数据结构时 |
| **按需生长** | `docs/modules/<模块>.md` | 某个核心子系统足够复杂、`architecture.md` 放不下时再拆分 |
| **按需生长** | `docs/decisions/NNN-<主题>.md`（ADR） | 发生重大技术选型或架构取舍时，用半页纸记录“为什么选 A 不选 B” |
| **按需生长** | `CHANGELOG.md` | 对外发版的产品/库，或仓库本身已有该文件时维护 |

## 工作流

### 模式 A：中途接手项目 → 通读代码生成文档（Bootstrap）

1. **采集客观盘点快照**：
   ```text
   DOC_HELPER inventory --workspace "<项目路径>"
   ```
   查看仓库现有文档、顶层代码目录规模、清单/入口文件、配置与接口线索，以及尚未被文档覆盖的模块。
2. **只读精读源码核实事实**：
   - 中小型仓库：直接按局部行号精读入口文件、核心配置、路由/接口定义与关键模块。
   - 大型或多子系统仓库：按互不重叠的模块目录边界，用 `invoke_subagent` 并行派发 2–3 个只读子 Agent **`saki-explorer`**（`Model: "flash"`）分别梳理各子系统的职责、关键入口（`file:line`）、数据流与对外契约。
3. **先给规划清单与大纲，等用户确认**：
   阅读 [文档体系与写作模板](references/doc-templates.md)，按“2 核心 + 4 按需”原则提出精简方案（例如：更新 `README.md` + 新建 `docs/architecture.md` + 仅当检测到接口/配置时提议 `docs/api.md`），用几行说明每份文档的定位与核心章节，**经用户确认后再落盘**。
4. **写入文档、配图并同步路由**：
   - 用简体中文（除非用户另指定语言）落盘文档；代码里无法确认的业务背景或部署信息标 `[待补充]`。
   - 若文档包含架构图、调用链图或数据流图：阅读 [文档绘图引擎规范](references/diagram-providers.md)，先按图表特征给出推荐（复杂架构全景/多模块拓扑/需手工美化倾向 `ExcalidrawZ MCP`，轻量流程/时序/状态机/ER 图倾向 `Mermaid`），读取 `~/.saki-dev/preferences.md` 与项目 `AGENTS.md` 中已登记的扩展绘图工具，再用 `ask_question` 弹窗确认本次绘图引擎后执行绘图（若所选 MCP 未启动则提示并支持一键回退 Mermaid）。
   - 核对文档内所有相对路径链接与导出图片路径真实存在。
   - 若仓库存在 `AGENTS.md`（或 `GEMINI.md`），提议在其路由表中补充 1–2 行指向新建 `docs/` 的相对链接（同样先征得同意再改常驻规则文件）。

### 模式 B：随功能 / 需求迭代 → 按 `git diff` 增量维护（Sync）

1. **采集改动与文档影响面**：
   ```text
   # 分析当前工作区改动（工作区干净时自动回退到当前分支领先 main 的提交或最近一次提交）
   DOC_HELPER impact --workspace "<项目路径>"

   # 对比指定基准分支（合并前推荐）
   DOC_HELPER impact --workspace "<项目路径>" --base main
   ```
   脚本会列出：变更/新增/删除/重命名的文件、受影响的顶层模块、清单/CI/配置变更、以及**现有文档中明确引用到变更路径或已删除路径的精确行号**。
2. **判断是否需要更新文档**：
   - 仅涉及内部私有实现重构、局部样式调整、普通单测补充或小 bug 修复，且**未改变外部功能、命令、配置、接口、数据结构或目录结构**时：明确告诉用户“本次改动不影响对外行为与项目文档，无需更新文档”并结束。
   - 命中以下任一变化时，进入更新准备：
     - 新增/修改/下线对外功能或用户可见行为；
     - 新增/重命名/删除核心目录、模块或入口文件（影响 `README.md` / `docs/architecture.md`）；
     - 变更安装、运行、测试、构建或 CI 命令（影响 `README.md`）；
     - 变更对外 API、CLI 参数、环境变量、配置字段或持久化数据格式（影响 `docs/api.md` / `docs/data-model.md`）；
     - 涉及重大架构或技术选型取舍（可提议补充一条简短 ADR）。
3. **先列受影响文档与改动摘要，确认后局部落盘**：
   - 用几行简洁清单告诉用户：准备更新哪几份文档、每份具体补充/修正哪一块（例如：“① `README.md`：补充 `--format` 参数说明；② `docs/architecture.md`：更新导出管线调用链与新增的 `src/export/worker.py`”）。
   - **得到用户确认后**，只修改受影响的段落，不重写无关章节；若本次删除或重命名了文件，同步清理文档中全部失效旧路径引用。
4. **交付核对**：
   - 确认所有修改过的文档中的相对链接指向真实文件，简要汇报更新了哪些文档的哪些位置。

## 输出与后续衔接

文档写入完成后交付修改摘要（新建/更新的文件与核心变化点）并停止，不顺手修改业务代码。

| 下游意图 | 衔接动作 |
| --- | --- |
| 全面体检文档死链、过期度与 `AGENTS.md` 臃肿问题 | 进入 `saki-govern` 做文档与规范治理 |
| 生成文档过程中发现复杂模块调用链需要深度排错 | 进入 `saki-bug-fix` 或 `saki-explore` |
| 收尾同步文档完成，准备合并回主干 | 回到 `saki-plan` 完成收尾合并清单 |

## 资源导航

- [references/doc-templates.md](references/doc-templates.md)：创建或更新 `README.md`、`docs/architecture.md`、`docs/api.md` / `docs/data-model.md`、`docs/modules/`、ADR 与 `CHANGELOG.md` 时阅读，含精简结构规范与反模式清单。
- [references/diagram-providers.md](references/diagram-providers.md)：文档需要画架构图、流程图或接入 ExcalidrawZ MCP 及其他自定义绘图工具时阅读，含场景推荐规则、弹窗流程与可扩展契约。
- [scripts/doc_helper.py](scripts/doc_helper.py)：零第三方依赖的文档现状盘点（`inventory`）与基于 `git diff` 的文档影响面分析脚本（`impact`）。
- [tests/test_doc_helper.py](tests/test_doc_helper.py)：`doc_helper.py` 的回归测试，仅在修改脚本时运行。
