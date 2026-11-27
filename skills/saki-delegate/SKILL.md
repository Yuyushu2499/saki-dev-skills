---
name: saki-delegate
description: "仅在用户在对话框中显式要求调用外部 CLI Agent（cc/wb/agy/codex/cursor/opencode/dsh/grok/kimi）时使用：先弹出模型选择选项（带按任务推荐默认项），再委托边界清楚的任务、返回结构化结果并支持续接原会话。默认日常开发走 Antigravity 内部闭环，不要在其他 Skill 中自动触发本 Skill。"
license: MIT
metadata:
  version: "1.0.0"
---

# saki-delegate

`SKILL_DIR` 指当前 Skill 的绝对目录；`<python>` 指 Python 3.10+（macOS/Linux 通常为 `python3`，Windows 通常为 `py -3`）；`DELEGATE` 是 `<python> "$SKILL_DIR"/scripts/delegate.py` 的简写。

## 核心规则

- **显式触发原则（严禁自动外派）**：平时默认在 Antigravity 内闭环（使用 `saki-explorer` / `saki-reviewer` / `saki-coder`）。**只有用户在对话框里明确提到要调用外部 CLI**（如“用 codex 审一下”“让 claude 实现”“用 saki-delegate 派给 cursor”）时才调用本 Skill；其他 Skill 不得默认自动触发外部 CLI 或强制走 onboarding。
- **未指明模型时每次必弹窗确认（`ask_question`）**：只要用户本次对话里**没有显式指定模型 ID / 模型名**，无论本地 `config.json` 是否存过默认模型，**每次调用外部 CLI 前都必须先用 `ask_question` 弹出模型选择卡片**，按任务场景给出 `(Recommended)` 默认推荐项，等用户点选后再执行（`dsh` 不支持 `--model` 参数，直接如实说明而不弹模型选框）。
- 用户只说自然语言，由当前 Agent 执行包装器，不要求用户另开终端。
- 每次只委托一个边界清楚的任务；严格使用用户点名的 runner，绝不自动静默替换成其他 runner。
- 沿用各 CLI 的 provider 与登录，不传递或保存密钥，不把密钥写入提示词。
- 调用方负责范围、权限和最终验收；外部 Agent 的自报结果不能替代工作区检查与真实测试。

## 先选择模式

| 模式 | 适用情况 | 路径 | 默认停止点 |
| --- | --- | --- | --- |
| 显式新任务 | 用户在对话中显式要求把分析、评审或修改交给某个外部 CLI | 检查 runner → 未指明模型时弹 `ask_question` 选模型 → 整理委托契约 → `run` → 验收 | 汇报结论与验证证据 |
| 续接任务 | 用户要求对同一 CLI 的上一轮结果追问或返工 | 核对 runner 与 session ID → 未指明是否换模型时弹 `ask_question`（默认推荐沿用原会话模型）→ `run --session` | 汇报本轮变化 |
| 显式按角色委托 | 用户显式要求用外部 CLI 执行 review / critique / diagnose / implement | 确认 runner 与模型（未指明模型先弹窗）→ `run --role <角色> --runner <CLI> --model <所选模型>` → 验收 | 汇报结论与验证证据 |
| 配置与诊断 | 用户主动要求扫描本机 CLI、查看模型列表、预览权限或排查失败 | `onboard --scan`、`config`、`models`、`run --dry-run` | 给出明确下一步 |

## 委托契约

提示词应简洁覆盖：

1. **目标与边界**：要查明或修改什么，明确不应改动的范围。
2. **完成标准**：预期行为、边界情况、最终必须交付的结果。
3. **入口线索**：用 `--file` 提供 1–4 个已确认文件，其余让外部 Agent 自行探索。
4. **验证**：从仓库配置确认真实测试、检查或构建命令，不写空泛的“运行测试”。
5. **最终报告**：改动与原因、涉及文件、验证命令和结果、未完成事项。

缺少仓库事实先查找，不猜测。诊断与评审要求引用文件和行号，并区分事实与推断。

## 工作流

### 1. 确认目标外部 CLI（显式点名优先）

- 用户已经点名外部 CLI（如 `codex`、`cc`、`claude`、`cursor`、`agy`、`opencode`、`wb`、`grok`、`kimi`、`dsh`）时，直接通过 `--runner <名称或别名>` 使用它；未完成 onboarding 时显式传 `--runner` 会直接执行，不会卡在首次引导。
- 如果用户只说“调用外部 CLI”而未点名具体哪一个：先静默运行 `DELEGATE onboard --scan --json` 检查本机已安装的 CLI，再用 `ask_question` 列出已安装的 CLI 让用户选择（优先把最贴合本次任务的 CLI 标为 `(Recommended)`）。
- 只有用户主动要求批量配置启用池和默认项时，才运行 `DELEGATE onboard --enable ... --default-runner ...`；首次配置前读 [Runner 适配参考](references/runners.md)，讲清权限差异、外部服务费用与数据出境边界。

名称不区分大小写，完整别名映射见 [Runner 适配参考](references/runners.md)。

查看配置或指定非标准二进制路径：

```text
DELEGATE config
DELEGATE config --set-bin <runner>=<可执行文件绝对路径>
```

### 2. 模型选择弹窗（未指明模型时必走）

在真正运行 `DELEGATE run` 之前，按下面规则确定模型：

1. **用户本次已明确说出模型名/ID**（如“用 claude opus 审一下”“让 agy 的 gemini-4-carbon-high 看一下”）：
   - 对支持列模型的 CLI（`antigravity`、`opencode`、`cursor`、`grok`），先静默执行 `DELEGATE models --runner <名称> --json` 校验真实 ID 后直接传入 `--model <id>`；其余 CLI 直接传官方模型名/ID，无需再弹窗。
2. **目标 CLI 不支持 `--model` 参数（`dsh`）**：
   - 如实告知用户 `dsh` 由其自身 profile 决定模型、不支持 `--model` 参数，不弹模型选框，直接继续。
3. **用户本次未指明模型（每次必弹窗）**：
   - 先准备候选列表：
     - 支持 `models` 子命令的 CLI（`antigravity`、`opencode`、`cursor`、`grok`）：先静默运行 `DELEGATE models --runner <名称> --json`，从真实返回结果中挑选 3–5 个最具代表性的模型（覆盖最强推理、主力编码、轻量快速三档）。
     - 无非交互 `models` 子命令的 CLI（`claude`、`codex`、`workbuddy`、`kimi`）：提供该 CLI 常用官方档位或“使用 CLI 默认模型”（不编造未核实的冷门版本号）。
       - `claude` 常用候选：`opus`（强推理/审查）、`sonnet`（主力编码）、`haiku`（快速轻量）、`使用 CLI 默认模型`
       - `codex` 常用候选：`使用 CLI 默认模型（--effort high，强推理）`、`使用 CLI 默认模型（--effort medium，主力编码）`、`使用 CLI 默认模型（--effort low，快速轻量）`
       - `workbuddy` / `kimi` 常用候选：`使用 CLI 默认模型`（及用户本机已确认的常用模型别名）
   - 按**当前任务场景**确定推荐项，排在第一个选项并加上 `(Recommended)` 前缀：
     - **代码审查 / 方案挑刺 / 疑难会诊**（`review` / `critique` / `diagnose`）：推荐**最强推理档**；
     - **功能实现 / 重构 / 写代码**（`implement` / `write`）：推荐**主力均衡编码档**；
     - **轻量探索 / 简单查询**：推荐**快速轻量档**。
   - 调用 **`ask_question`**（单选，问题写明目标 CLI、任务类型与为什么推荐第一项；UI 会自动附带“Other”供用户输入任意自定义模型 ID），**等用户选择后再执行**。
   - 如果用户选了“使用 CLI 默认模型”，执行时省略 `--model`（若所选项附带思考强度如 `high`，则传 `--effort high`）。

### 3. 派发新任务与显式角色委托

- 常规显式委托默认省略 `--mode`（使用 `write` 和各 CLI 最高权限）；用户要求只读/审查/挑刺/诊断，或使用读类 `--role`（`review` / `critique` / `diagnose`）时自动使用只读模式（`kimi` 非交互模式无法保证只读，拒绝读类任务）。
- 默认使用当前工作目录，跨项目时显式指定 `--workspace`。
- 调用示例：

```text
DELEGATE run --runner <名称> \
  --model <用户选中的模型ID> \
  --workspace "<项目绝对路径>" \
  --file "<相对入口文件>" \
  --prompt "<目标、边界、完成标准与真实验证命令>"
```

按角色显式委托（仅在用户显式点名外部 CLI 执行审查、挑刺、会诊或实现时使用）：

| 角色 | 用途 | 权限 |
| --- | --- | --- |
| `review` | 独立代码审查 | 只读 |
| `critique` | 动手前的方案挑刺 | 只读 |
| `diagnose` | 疑难问题双模型会诊（配合 `--role-slot 1` / `2`） | 只读 |
| `implement` | 按已确认方案实现 | 写入 |

```text
DELEGATE run --role review --runner <用户指定的 CLI> \
  --model <用户选中的模型ID> \
  --workspace "<项目绝对路径>" \
  --prompt "<审查范围与要求>"
```

启动前需要核对参数时追加 `--dry-run`；预览不会启动外部 Agent。

### 4. 续接原会话

读取上一轮输出的 `session_id`，只对同一 runner 续接。若用户本轮未指明是否切换模型，先用 `ask_question` 弹出快捷确认（第一项为 `(Recommended) 沿用上一轮会话模型`，其余项为可切换的常用模型，不适用 `--model` 的 `dsh` 除外）：

```text
DELEGATE run --runner <原 runner> \
  --workspace "<原工作区>" \
  --mode <read|write> \
  --session <session_id> \
  --prompt "<本轮新发现、追问或修正要求>"
```

续接只发送本轮新信息，不重复整个任务；跨 runner 不能复用 session ID；DSH 续接必须使用原 cwd，其 ownership、preset 与 cwd 校验失败时如实报告，不绕过。

### 5. 验收与失败恢复

1. 读取 `output_path` 的摘要；需要退出码、session ID 或错误结构时读取 `result_path`，原始协议诊断才读取 `events_path`。
2. 检查工作区改动是否越界，检查测试是否被删除、跳过或弱化，再重新运行真实验证命令。
3. 需要返工时续接原会话，只发送新发现和修正要求。
4. 非零退出、协议错误或超时后不盲目重试。先根据错误修正配置、登录状态、任务范围或权限，再决定新任务或续接。
5. 缺少 CLI 或登录时停止并给出对应官方入口；安装与登录必须另行获得用户授权。

## 输出与停止条件

成功后脚本输出 `status`、`session_id`、`runner`、`model`、`model_source`、`effort`、`effort_source`、`output_path`、`result_path`、`events_path` 和 `elapsed`（来源字段取值为 `flag`、`config` 或 `cli-default`）。每次运行有独立目录（默认 `~/.saki-delegate`，可用 `SAKI_DELEGATE_HOME` 覆盖），包含 prompt、精简 Markdown、结构化 result、原始 stdout/stderr 与事件日志。result 里的 `resume_command` 是用户在终端直接续接该会话的命令。

给其他程序调用时追加 `--json`：stdout 只输出一个 JSON 对象，带 `contract_version`（当前为 1）。最终回复只保留用户需要的结论、实际改动、验证证据、未完成事项和必要 session ID。完成当前委托与验收后停止。

## 资源导航

- [references/runners.md](references/runners.md)：只在首次配置、显式只读、排查特定 CLI 或维护适配器时阅读相关 Runner 小节。
- [scripts/delegate.py](scripts/delegate.py)：扫描、配置、调用、解析与运行产物的确定性工具；使用 Skill 时不需要阅读源码。
- [tests/test_delegate.py](tests/test_delegate.py)：九种 Runner 的回归测试；只在开发或整改时读取相关部分。
