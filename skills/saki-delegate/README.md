# saki-delegate

`saki-delegate` 是 `saki-dev-skills` 的显式跨 CLI 委托工具。日常开发默认在 Antigravity 内闭环（使用 `saki-explorer` / `saki-reviewer` / `saki-coder` 原生子 Agent）；**只有在你在对话框中显式点名外部 CLI 时**，才会激活本 Skill 派发任务。

## 特点

- **显式触发，不擅自外派**：其他 Skill（`saki-plan` / `saki-code-review` / `saki-bug-fix`）不会默认自动触发外部 CLI，只有你明确说出要调用某个 CLI 时才进入。
- **未指明模型每次必弹窗确认**：只要本次对话未写明具体模型，先用交互式选项卡片（`ask_question`）列出候选模型并按任务场景给出默认推荐项（`(Recommended)`），点选后再执行。
- **支持 9 种外部 CLI 与连续对话**：支持 `claude`、`codex`、`antigravity (agy)`、`cursor`、`opencode`、`workbuddy`、`dsh`、`grok`、`kimi`，并可按 `session_id` 续接同一会话。

## 支持的外部 CLI 与别名

| Agent | 简称与别名 |
| --- | --- |
| Claude Code | `cc`、`claude`、`claude-code` |
| WorkBuddy | `wb`、`workbuddy`、`codebuddy`、`cbc` |
| Antigravity | `agy`、`antigravity`、`anti` |
| Codex | `codex` |
| OpenCode | `opencode` |
| DeepSeek Harness | `dsh`、`deepseek`、`deepseek-harness` |
| Grok Build | `grok`、`grok-build` |
| Kimi Code | `kimi`、`kimi-code` |
| Cursor | `cursor`、`cursor-agent`、`cursor-cli` |

## 使用示例

```text
用 codex 审查当前分支的改动，只读分析并列出高风险隐患。
```

```text
让 claude 帮我给这个方案挑刺。
```

```text
用 cursor 实现这个重构方案，并在完成后跑局部快测。
```

以上示例均未指定模型，执行前都会自动弹出模型选择卡片并给出按任务推荐的默认模型。

## 使用条件与边界

- 需要 Python 3.10+，以及至少一个本机已安装并登录的受支持 CLI。
- 运行产物和配置默认保存在 `~/.saki-delegate`（可通过 `SAKI_DELEGATE_HOME` 覆盖，二进制路径可通过 `SAKI_DELEGATE_<RUNNER>_BIN` 覆盖）。
- 任务内容会交给你指定的外部 Agent 及其模型服务，切勿在提示词中放置密钥或敏感凭据。
- 特定 CLI 的调用细节与排错见 [Runner 适配参考](references/runners.md)。

## License

基于 [oil-dev-skills](https://github.com/oil-oil/oil-dev-skills)（MIT License）二次开发。许可见 [LICENSE](LICENSE)，素材来源见 [NOTICE.md](assets/readme/NOTICE.md)。
