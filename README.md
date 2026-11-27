English · [中文](README.zh-CN.md)

# saki-dev-skills

An **Antigravity-native plugin** and standard Agent Skills toolkit for disciplined software development, adapted from [oil-dev-skills](https://github.com/oil-oil/oil-dev-skills).

By default, every step stays **100% inside Antigravity** using built-in lightweight subagents (`saki-explorer`, `saki-reviewer`, `saki-coder`) with zero external CLI calls. When you explicitly ask in chat to invoke another CLI (such as Codex, Claude Code, or Cursor), `saki-delegate` activates and pops up an interactive model picker with a task-appropriate recommendation before running.

## What is included

### 1. Seven Agent Skills (`skills/`)
- **Explore · [`saki-explore`](skills/saki-explore/SKILL.md)**: Read-only codebase inventory, call-chain tracing, reusable infrastructure discovery, and parallel exploration via `saki-explorer` (`flash`).
- **Plan · [`saki-plan`](skills/saki-plan/SKILL.md)**: Complexity-graded planning (`L1` / `L2` / `L3`), independent plan critique via `saki-reviewer`, strict dispatch contracts with fast-rule test cadence, optional sub-agent mode, and a closing merge checklist.
- **Code Review · [`saki-code-review`](skills/saki-code-review/SKILL.md)**: Risk-graded code diff review checking scope drift, `do-not-edit` boundaries, file bloat, and five-dimension quality in a clean `saki-reviewer` context.
- **Bug Fix · [`saki-bug-fix`](skills/saki-bug-fix/SKILL.md)**: Root-cause debugging workflow—reproduce first, trace to the origin, fix at the source, scan systemic patterns, and run dual-path read-only diagnosis via `saki-reviewer` on stop-loss.
- **Docs · [`saki-docs`](skills/saki-docs/SKILL.md)**: Generates living project documentation from real source code when onboarding a repository (`README.md`, `docs/architecture.md`, and on-demand API/data-model/module/ADR/changelog docs), and incrementally syncs affected docs from `git diff` after user confirmation (Chinese by default).
- **Govern · [`saki-govern`](skills/saki-govern/SKILL.md)**: Audits `AGENTS.md` / `GEMINI.md`, test tiering, `.agents/skills/` & `.agents/plugins/`, worktree merge state, and interactive branch boards (rendered via Antigravity `generative_ui` when available).
- **Delegate · [`saki-delegate`](skills/saki-delegate/SKILL.md)**: Explicit-only cross-CLI delegation (`claude`, `codex`, `agy`, `cursor`, `opencode`, `workbuddy`, `dsh`, `grok`, `kimi`). Never triggered automatically—always prompts with `ask_question` to choose a model (with a task-based `(Recommended)` default) whenever no model is specified in your message.

### 2. Antigravity Native Enhancements
- **Plugin manifest ([`plugin.json`](plugin.json))**: Install and toggle the entire bundle as a single plugin in Antigravity while keeping `skills/` compatible with other skill-based coding agents.
- **Dedicated MCP-stripped subagents ([`agents/`](agents/saki-explorer.md))**:
  - [`saki-explorer`](agents/saki-explorer.md): Strictly read-only (`read_file`, `run_command`, `inheritMcp: false`).
  - [`saki-reviewer`](agents/saki-reviewer.md): Strictly read-only independent critic, reviewer, and risk checker (`inheritMcp: false`).
  - [`saki-coder`](agents/saki-coder.md): Contract-bound implementer (`read_file`, `edit_file`, `write_file`, `run_command`, `manage_task`, `inheritMcp: false`).
- **Upfront `do-not-edit` guard ([`hooks.json`](hooks.json) + [`hooks/guard_do_not_edit.py`](hooks/guard_do_not_edit.py))**: `PreToolUse` hook on `edit_file|write_file` that blocks edits matching `do-not-edit` patterns declared in your repository's `saki-dev` dev profile (`AGENTS.md`, `GEMINI.md`, or `CLAUDE.md`).

## Installation

### Option 1: Install as an Antigravity Plugin (recommended)

Clone or symlink this repository into your global or workspace Antigravity plugins folder:

```bash
# Global (all workspaces)
git clone https://github.com/Yuyushu2499/saki-dev-skills.git ~/.gemini/config/plugins/saki-dev-skills

# Or workspace-specific
git clone https://github.com/Yuyushu2499/saki-dev-skills.git .agents/plugins/saki-dev-skills
```

### Option 2: Install standard `skills/` only

```bash
npx skills add Yuyushu2499/saki-dev-skills
```

## Project dev profile (`saki-dev`)

Add a section whose heading contains `saki-dev` to your repository's `AGENTS.md` (or `GEMINI.md`):

```markdown
## Dev profile (saki-dev)

- quick-test: `pytest tests/{target} -q`
- merge-gate: `make ci`
- high-risk: `src/storage/**`, `src/auth/**`, `migrations/`
- do-not-edit: `vendor/`, `src/generated/**`
```

Once configured, `saki-explore`, `saki-plan`, `saki-code-review`, `saki-govern`, and the `PreToolUse` hook read it directly. See [dev-profile.md](skills/saki-govern/references/dev-profile.md) for all supported keys.

## Personal preferences

User-specific preferences live in `~/.saki-dev/preferences.md` (override with `SAKI_DEV_HOME`). Cross-CLI delegate state lives in `~/.saki-delegate` (override with `SAKI_DELEGATE_HOME`). Neither is written into project repositories.

## Maintenance and testing

Run all unit tests without calling any models:

```bash
python3 scripts/verify_repo.py
```

## Attribution & License

Adapted from [oil-oil/oil-dev-skills](https://github.com/oil-oil/oil-dev-skills) under the [MIT License](LICENSE).
