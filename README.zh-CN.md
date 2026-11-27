[English](README.md) · 中文

# saki-dev-skills

面向 **Antigravity 原生闭环**深度定制的工程化开发插件与 Agent Skills 套件，基于 [oil-dev-skills](https://github.com/oil-oil/oil-dev-skills) 二次开发。

日常研发默认 **100% 在 Antigravity 内部闭环**（通过插件内置的轻量净身子 Agent `saki-explorer` / `saki-reviewer` / `saki-coder` 完成探索、挑刺、实现、审查与排错，不自动调用任何外部 CLI）；只有在对话框中**显式要求调用其他 CLI**（如 Codex、Claude Code、Cursor 等）时，才会激活 `saki-delegate`，并在未指明模型时**每次弹出交互式模型选择卡片**（带按任务场景的默认推荐项）。

## 套件构成

### 1. 九个核心 Skill（`skills/`）
- **探索 · [`saki-explore`](skills/saki-explore/SKILL.md)**：严格只读的结构盘点与调用链追踪，大仓库默认按独立模块派发 `saki-explorer`（`flash` 模型）并行摸底。
- **方案 · [`saki-plan`](skills/saki-plan/SKILL.md)**：按 `L1 / L2 / L3` 分级制定平实方案，默认由 `saki-reviewer` 独立挑刺，生成带测试与重构建控频红线的派发契约，支持子 Agent 模式与收尾合并清单。
- **审查 · [`saki-code-review`](skills/saki-code-review/SKILL.md)**：先核对方案范围、禁改目录与文件膨胀，再由 `saki-reviewer` 在干净只读上下文执行五维深度审查。
- **排错 · [`saki-bug-fix`](skills/saki-bug-fix/SKILL.md)**：先复现再定位根因，在坏数据源头修复，判断普遍问题并全仓排查，止损时默认开两路 `saki-reviewer` 并行诊断。
- **文档 · [`saki-docs`](skills/saki-docs/SKILL.md)**：遵循“2 核心 + 4 按需”活文档体系（默认中文），支持中途接手项目从真实源码反推生成文档，以及随功能迭代按 `git diff` 列出影响清单、经确认后做精准增量同步。
- **注释 · [`saki-comment`](skills/saki-comment/SKILL.md)**：按多语言行业权威规范（Google Python / TSDoc / JSDoc / GoDoc / Rustdoc / Javadoc / Doxygen）为无注释老项目补全函数文档与核心块中文注释（只解释 Why 不复述 What），同时主动扫描清理过期误导、废话、作者日期与大段注释死代码，严格零逻辑改动。
- **交付 · [`saki-ship`](skills/saki-ship/SKILL.md)**：交付前分支保护与敏感文件预检 + 中文提交规范（`Conventional Commits` 前缀 + 中文描述）并推送远端；开发分支测试通过后可直接自动提交推送，`main` / `master` 保护分支必须先确认，也可随时手动调用。
- **治理 · [`saki-govern`](skills/saki-govern/SKILL.md)**：体检并治理 `AGENTS.md` / `GEMINI.md`、`.agents/skills/` 与 `.agents/plugins/`、快慢测试分层、Worktree 卫生，以及支持 Antigravity `generative_ui` 渲染的交互式分支看板。
- **显式跨 CLI 委托 · [`saki-delegate`](skills/saki-delegate/SKILL.md)**：支持 9 种外部 CLI（`claude`、`codex`、`agy`、`cursor`、`opencode`、`workbuddy`、`dsh`、`grok`、`kimi`）。仅在你显式点名外部 CLI 时触发；只要本次未指明模型，每次均通过 `ask_question` 弹出模型选择卡片并给出按任务推荐的默认模型。

### 2. Antigravity 原生增强能力
- **原生 Plugin 清单（[`plugin.json`](plugin.json)）**：可作为单个插件在 Antigravity Customizations 页面一键启停，同时保留标准 `skills/` 结构兼容其他宿主。
- **插件常驻工程规则（[`rules/AGENTS.md`](rules/AGENTS.md)）**：随插件开启自动生效——开发分支测试通过后自动按 `saki-ship` 中文提交推送（保护主分支），日常写代码自动补合理中文注释并顺手清理劣质注释。
- **专用轻量净身子 Agent（`agents/`）**：全部设置 `inheritMcp: false` 剥离无关 MCP 底座 Token 开销：
  - [`saki-explorer`](agents/saki-explorer.md)：纯只读探索子 Agent（无 `edit_file`/`write_file`）。
  - [`saki-reviewer`](agents/saki-reviewer.md)：纯只读独立审查、方案挑刺与高危操作检查子 Agent。
  - [`saki-coder`](agents/saki-coder.md)：严格遵循派发契约与快规则测试节奏的实现子 Agent。
- **禁改目录事前硬拦截（[`hooks.json`](hooks.json) + [`hooks/guard_do_not_edit.py`](hooks/guard_do_not_edit.py)）**：`PreToolUse` 钩子自动读取目标仓库 `AGENTS.md` / `GEMINI.md` / `CLAUDE.md` 中 `saki-dev` 小节的 `禁改`（`do-not-edit`）规则，在 `edit_file` / `write_file` 动手前一瞬间直接拦截越界写入。

## 安装方式

### 方式一：作为 Antigravity 原生 Plugin 安装（推荐）

克隆或软链到全局插件目录（或项目 `.agents/plugins/`）：

```bash
# 全局安装（对所有工作区生效）
git clone https://github.com/Yuyushu2499/saki-dev-skills.git ~/.gemini/config/plugins/saki-dev-skills

# 或仅对当前项目生效
git clone https://github.com/Yuyushu2499/saki-dev-skills.git .agents/plugins/saki-dev-skills
```

### 方式二：仅安装标准 `skills/`

```bash
npx skills add Yuyushu2499/saki-dev-skills
```

## 项目开发约定（`saki-dev`）

在目标仓库根目录的 `AGENTS.md`（或 `GEMINI.md`）中加入标题含 `saki-dev` 的小节：

```markdown
## 开发约定（saki-dev）

- 快测：`pytest tests/{target} -q`
- 门禁：`make ci`
- 高风险：`src/storage/**`、`src/auth/**`、`migrations/`
- 禁改：`vendor/`、`src/generated/**`
```

配置后，`saki-explore`、`saki-plan`、`saki-code-review`、`saki-govern` 与 `PreToolUse` 钩子都会直接读取该约定。详细字段见 [dev-profile.md](skills/saki-govern/references/dev-profile.md)。

## 个人偏好与本地配置

- 个人偏好保存在 `~/.saki-dev/preferences.md`（可用环境变量 `SAKI_DEV_HOME` 覆盖）。
- `saki-delegate` 的状态与运行产物保存在 `~/.saki-delegate`（可用 `SAKI_DELEGATE_HOME` 覆盖，二进制路径可用 `SAKI_DELEGATE_<RUNNER>_BIN` 覆盖）。
- 以上配置均仅存本机，不会写入项目仓库。

## 回归测试

无需调用任何模型即可在几秒内跑完全仓单元测试（含插件清单、子 Agent、Hook 拦截与 6 个 Skill 脚本）：

```bash
python3 scripts/verify_repo.py
```

## 开源协议与致谢

本项目基于 [oil-oil/oil-dev-skills](https://github.com/oil-oil/oil-dev-skills) 进行二次开发，遵循 [MIT License](LICENSE)。
