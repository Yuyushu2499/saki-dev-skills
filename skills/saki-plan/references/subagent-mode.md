# 子 Agent 模式

子 Agent 模式下，主 Agent 只做决策，所有执行都交给子 Agent。主 Agent 的上下文因此保持干净，只装需求、方案、契约和各子 Agent 的汇报，用来做判断；读代码、改代码、跑测试的细节留在子 Agent 里。

## 1. 开启与关闭

只有用户明确要求时才开启，Agent 不自行开启：

- 用户在本次对话里要求，例如“用子 Agent 模式”“你只做决策，活都交给子 Agent”。只对本次任务生效。
- 用户在个人偏好的 `## saki-plan` 一节里写了要用子 Agent 模式。开工前运行 `PREFS get saki-plan --host <宿主>` 读取；读取失败或没写时按普通方式工作。

用户说“这次你自己做”或“关掉子 Agent 模式”时关闭。

开启后严格执行：再小的执行工作也交给子 Agent，主 Agent 不自己顺手做。当前宿主开不了子 Agent、用户又没有显式指定外部 CLI 时，告诉用户无法进入子 Agent 模式，问是改用普通方式还是换个环境，不要悄悄自己执行。

## 2. 分工

| 主 Agent 做 | 交给子 Agent |
| --- | --- |
| 澄清需求、分级、拆任务 | 读代码、查调用链、盘点可复用基建（按 `saki-explore`，只读） |
| 写方案和派发契约，决定允许修改的文件 | 按契约写代码和测试、跑局部快测 |
| 拍板取舍；能定的自己定，涉及产品取舍或高风险的问用户 | 原因不明的缺陷：复现、找根因、修复（按 `saki-bug-fix`） |
| 验收：读汇报，看 `git status` 和 `git diff --stat`，跑契约里的一条验收命令只看结果 | 独立审查和方案挑刺 |
| 决定返工、合并、止损或砍掉 | 合并前跑门禁、整理 Worktree 并汇报 |

主 Agent 不打开源码文件逐行阅读，不修改文件。需要看代码细节才能做决定时，派一个只读子 Agent（`saki-explorer`）去看，并让它回答一个具体问题，例如“导出入口在哪个函数、有没有现成的进度回调”。

## 3. 派给谁（默认纯 Antigravity 原生闭环）

| 工作 | 默认派发方式（Antigravity 原生） | 显式跨 CLI 时 |
| --- | --- | --- |
| 探索、回答代码问题 | `invoke_subagent` → **`saki-explorer`**（`Model: "flash"`，未注册时退回 `research`），按 `saki-explore` 查 | 仅用户显式要求外部 CLI 时走 `saki-delegate` |
| 实现 | `invoke_subagent` → **`saki-coder`**（未注册时退回 `self`）；多路并行时传 `Workspace: "share"` | 仅用户显式点名外部 CLI 时走 `saki-delegate --role implement`（未指明模型先弹窗） |
| 方案挑刺 | `invoke_subagent` → **`saki-reviewer`**（只读，未注册时退回 `research`） | 仅用户显式点名外部 CLI 时走 `saki-delegate --role critique`（未指明模型先弹窗） |
| 代码审查 | `invoke_subagent` → **`saki-reviewer`**（只读，按 `saki-code-review`） | 仅用户显式点名外部 CLI 时走 `saki-delegate --role review`（未指明模型先弹窗） |
| 原因不明的缺陷 | `invoke_subagent` → **`saki-coder`**，要求按 `saki-bug-fix` 执行并在确认点停下汇报 | 止损双路会诊仅在用户显式要求时走 `saki-delegate --role diagnose` |
| 合并门禁 | `invoke_subagent` → **`saki-coder`** 跑门禁并汇报结果；提交、合并、删除分支仍由主 Agent 决定并经用户确认 | 同上 |

## 4. 派发提示与汇报格式

每次派发的提示都包含下面几项。实现任务直接使用 [严格派发契约](plan-rubric.md#3-审批通过后的严格派发契约含执行快规则)，再补上最后两项：

```text
任务：<一句话目标>
工作目录：<路径>（只在这里读写）
读写权限：<只读 / 可修改的文件或通配符>
要遵循的 Skill：<如 saki-explore、saki-bug-fix；没有就省略>
遇到需要取舍、超出范围或卡住两轮时：停下，不要自己决定，在汇报里写明选项和你的倾向。
汇报（15 行以内）：
1. 结论
2. 改动的文件（只读任务写“无”）
3. 运行过的命令和结果
4. 需要主 Agent 决定的问题
5. 没有验证的部分
```

## 5. 验收与返工

1. 对照契约看汇报，再用 `REVIEW_HELPER --allow <允许的路径>` 或 `git diff --stat` 确认没有越界改动。
2. 跑契约里的一条局部快测，只看通过与否和失败用例名。
3. 不通过时，把问题清单交回同一个子 Agent 返工：Antigravity 原生子 Agent 直接用 `send_message` 续接其 `conversationId`；外部 CLI 用 `--session` 续接；不能续接时再开全新子 Agent，附上上一轮的汇报和问题清单。
4. 返工两轮仍不通过，转 `saki-bug-fix` 的止损步骤，同样派给子 Agent 执行。

## 6. 并行与隔离

- 多个写代码的子 Agent 同时工作时，优先给 `saki-coder` 传 `Workspace: "share"` 获得共享仓库目录的独立工作副本（外部 CLI 场景用独立 Git Worktree），契约里允许修改的文件互不重叠。
- 只读子 Agent（`saki-explorer` / `saki-reviewer`）共用主工作目录即可（`Workspace: "inherit"`）。
- 记下每个写任务子 Agent 的任务、分支和工作区路径，收尾合并时用。
- **控制拆单粒度，减少冷启动往返**：多子 Agent 拆单用于互不依赖的并行子任务、独立审查或疑难双路会诊；同一模块内的紧密跟进与小步修复优先用 `send_message` 续接原执行子 Agent，不反复另开只读探索加全新执行器重读同一批大文件。
- **独占资源分工验证，不重复空跑**：涉及真机、模拟器、远程独占环境或高耗时集成套时，由单一角色运行并产出日志与产物证据，其余审查或核验角色按职责分工复用该证据，避免多个子 Agent 串行重复跑同一套重测。

## 7. 向用户汇报

主 Agent 对用户只讲决策层面的事：做了哪些决定和理由、各子 Agent 的结果摘要（一两句话一条）、需要用户拍板的问题、没有验证的部分。不要把子 Agent 的完整输出原样贴给用户。
