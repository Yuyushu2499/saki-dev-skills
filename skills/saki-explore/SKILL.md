---
name: saki-explore
description: "严格只读的代码库结构盘点与并行探索：输出目录规模、开发约定、调用链、可复用基建与快测入口。需要摸清陌生仓库、定位功能实现、盘点可复用组件或为方案收集代码事实时使用；不用于改代码、写方案（saki-plan）、代码审查（saki-code-review）或仓库治理（saki-govern）。"
license: MIT
metadata:
  version: "1.0.0"
---

# saki-explore

`SKILL_DIR` 指当前 Skill 的绝对目录；`<python>` 指 Python 3.10+（macOS/Linux 通常为 `python3`，Windows 通常为 `py -3`）；`REPO_MAP` 是 `<python> "$SKILL_DIR"/scripts/repo_map.py` 的简写，`PREFS` 是 `<python> "$SKILL_DIR"/scripts/preferences.py` 的简写。

## 核心规则

- **全程严格只读**：探索阶段绝不修改、新建或删除项目文件，不安装依赖，不触发会改动工作区状态、抢占前台窗口焦点或弹出系统权限框的命令。
- **按熟悉度选最轻路径**：在已知结构或单点定位任务上，直接用宿主自带的检索工具（如 `read_file` / `rg` / 代码骨架工具）直奔目标文件，不强行多跑一轮全仓脚本；只有在进入陌生仓库或做跨模块大改造摸底时才先跑 `REPO_MAP`。
- **低成本局部读取与原生只读子 Agent**：默认在 Antigravity 内闭环，派发并行探索时优先使用插件内置只读子 Agent **`saki-explorer`**（无写入工具、`inheritMcp: false`）并显式指定轻量快速模型档位（如 `Model: "flash"` 或 `"flash_lite"`；用户的[个人偏好](#个人偏好)另有要求时照偏好）；只按局部行号精读关键函数与类型定义，不把整篇大文件原样塞进主上下文。
- **必查现成基建与真实测试入口**：除了查清目标业务链路，必须顺手确认仓库已有的公共组件、共享核心模块、`AGENTS.md` / `GEMINI.md` / `DESIGN.md` 硬约束，以及项目规定使用的真实快测命令（注意排查是否禁用了默认的慢速全量命令）。若 `AGENTS.md` / `GEMINI.md` 有标题含 `saki-dev` 的开发约定小节（`REPO_MAP` 会直接展示），快测与门禁命令、高风险与禁改目录以它为准。

## 先选探索档位

| 档位 | 适用场景 | 执行方式 | 默认停止点 |
| --- | --- | --- | --- |
| `quick` | 熟悉仓库查单个符号、配置项、报错位置 | 直接检索目标关键词并局部读 1–3 处代码片段（无需跑脚本、无需子 Agent） | 给出精确 `file:line` 结论后停止 |
| `medium` | 梳理单个功能模块的入口、状态流转与可复用组件 | 局部检索 + 读取 `AGENTS.md` / `GEMINI.md` / `DESIGN.md` 相关约束 + 精读模块核心文件 | 输出模块调用链、可复用基建与局部快测命令 |
| `thorough` | 初入陌生大仓库、跨多子系统改造前摸底 | 先跑 `REPO_MAP` 看全局结构 → 按独立子系统边界并行派发 2–3 个 `saki-explorer`（`Model: "flash"`） | 汇总结构化探索简报，准备交接方案阶段 |

## 工作流

### 1. 全局快照（仅陌生仓库或 `thorough` 档需要）

初入陌生项目或不清楚目录结构与并行工作树分布时，运行轻量结构快照（遵循 Git 忽略规则，秒级返回目录规模、后缀分布、规范文件、已定义脚本与 Worktree 列表）：

```text
REPO_MAP --workspace "<项目路径>"
```

若输出显示存在 `AGENTS.md`、`GEMINI.md`、`DESIGN.md` 或自定义 `scripts/` 测试脚本，优先读取其中与当前任务相关的命令约定和禁令，不凭经验臆造默认测试命令。输出里的 `ci_run_steps` 是 CI 实际执行的命令，确认快测与门禁命令时以它和仓库已定义脚本为准。

### 2. 按真实模块边界只读深挖

- **`quick` / `medium` 档**：直接定位相关文件，每次按行号读取 40–100 行确认真实调用关系，顺手查看同模块或公共目录下的可复用组件与辅助函数。
- **`thorough` 档**：阅读 [并行只读探索切片指南](references/parallel-exploration.md)。**按互不重叠的子系统目录划分切片**（不要把强耦合在同一批文件里的视图与状态硬拆给多个子 Agent 重复读取）：
  - 若当前环境支持原生子 Agent：先运行 `PREFS get saki-explore --host <宿主>` 读取[个人偏好](#个人偏好)。`shared` 对所有宿主生效，`host_text` 只对当前宿主生效，两者冲突时以 `host_text` 为准。偏好写了用哪种子 Agent 机制、什么模型、派几个或怎么回收，就照着做；没写到的部分按默认：在 Antigravity 中通过 `invoke_subagent` 并行启动 2–3 个只读子 Agent（优先 `TypeName: "saki-explorer"`，未注册时退回 `research`），显式指定 `Model: "flash"`（或 `"flash_lite"`）。不要在用户未要求 `/swarm` 且偏好未写明时擅自启动 swarm。命令失败或没有设置时按默认做法继续，不为此打断用户。
  - 若当前环境不支持子 Agent：主 Agent 按子系统顺序逐块做局部行号读取，每读完一块记下 `file:line` 摘要再看下一块。

### 3. 交叉核验并输出探索简报

交付前核对所有结论均有代码依据：

1. 关键结论附上准确的 `文件路径:行号` 与核心符号名，区分“代码已确认事实”与“待用户拍板的产品问题”。
2. 明确列出本次任务**可直接复用的公共组件、设计令牌或底层模块**。
3. 明确列出改动该模块后对应的**局部快测命令**与现有测试路径。

## 个人偏好

整个 `saki-dev` 系列共用一份本机偏好文件 `~/.saki-dev/preferences.md`（环境变量 `SAKI_DEV_HOME` 可以改目录），用自然语言写：每个 Skill 一节（如 `## saki-explore`），紧跟在 Skill 标题下的文字对所有宿主生效，`### 宿主名` 下面的文字只对该宿主生效。它只放跟用户本人有关的设置；团队共享的约定写在仓库 `AGENTS.md` / `GEMINI.md` 的 `saki-dev` 小节。

`<宿主>` 是你当前运行在哪个 Agent 产品里，用小写连字符名称，例如 `antigravity`、`claude-code`、`codex`、`opencode`、`workbuddy`、`kimi-code`、`grok-build`、`deepseek-harness`、`gemini-cli`。

`saki-explore` 只在 `thorough` 档派发子 Agent 时读取偏好。常见的内容是派发机制、模型、数量上限和回收方式，例如：

```markdown
## saki-explore

探索子 Agent 最多 3 个。

### antigravity

- 用 `invoke_subagent` 派发 `saki-explorer`，模型选 `flash`。
```

不要主动询问偏好。用户说“以后探索子 Agent 用某个模型”“探索最多派 2 个子 Agent”这类话时保存：`set` 会整段替换，所以先用 `PREFS get` 取出现有文字，把新要求合并进去再保存，最后把保存后的内容告诉用户。

```text
PREFS set saki-explore --host <宿主> --text "<合并后的完整文字>"
```

对所有宿主生效的要求，把 `--host <宿主>` 换成 `--all-hosts`。用户要求查看时运行 `PREFS show`，要求删除时运行 `PREFS unset saki-explore --host <宿主>`。命令返回 `status: ERROR` 时，把 `error` 原样告诉用户。

## 输出与后续衔接

探索简报交付后停止，不顺手改代码，也不在未获要求时直接铺开长篇方案。

| 下游意图 | 衔接动作 |
| --- | --- |
| 基于探索事实制定开发方案 | 进入 `saki-plan`，直接复用本次查清的 `file:line`、可复用组件与局部快测命令 |
| 发现常驻文档描述与当前代码目录明显脱节 | 进入 `saki-govern` 做文档与规范治理 |

## 资源导航

- [references/parallel-exploration.md](references/parallel-exploration.md)：进入 `thorough` 档并行探索时阅读，说明子系统切片原则与简报格式。
- [scripts/repo_map.py](scripts/repo_map.py)：零第三方依赖的 Git 文件分布、规范入口、真实脚本列表（含 justfile 与 CI 命令）与 Worktree 快照工具。
- [scripts/preferences.py](scripts/preferences.py)：读写本机个人偏好文件，零第三方依赖。
- [tests/test_repo_map.py](tests/test_repo_map.py)、[tests/test_preferences.py](tests/test_preferences.py)：两个脚本的回归测试，仅在修改脚本时运行。
