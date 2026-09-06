# Blog discovery draft

> This file is private working memory for exploration. It is not publishable article prose.
> Store it only at `<article-directory>/.draft/draft.md` and delete the `.draft` directory after both published language versions are complete and validated.

## State

- Status: `exploring`
- Working slug: `dsh-agent-runtime`
- Started: 2026-09-06
- Last updated: 2026-09-06
- Writing approved by:
- Approval date:

Allowed status values are `exploring` and `approved-for-writing`. Never set the latter without explicit user approval after discovery.

## Current synthesis

文章将放弃原先“Loader 启动后整个 Agent 怎样运行”的宽泛叙事，集中解释 DSH Base Bundle 的“Agent 与模型核心”组件组。暂定从 `ctx.sessions` 与 `ctx.agents` 建立基础认识，再继续研究 `agent-loop`、`llm`、模型 Provider、`system-prompt` 与 `tools` 怎样共同完成一次 LLM call。

第一轮源码探索确认：`ctx.sessions` 是 `@deepseek-ai/dsh-session` 提供的进程内 Session 注册表，管理活跃 Session 及其追加式事件日志；`ctx.agents` 是 `@deepseek-ai/dsh-agent` 提供的进程内 Agent 注册表，管理活跃 Agent，但把 Agent 的具体创建和恢复委托给 `@deepseek-ai/dsh-agent-loop`。两者使用同一个 `SessionId` 标识同一条 Agent/Session 生命周期，不过 Session 可以脱离 Agent 单独创建。

## Central question and motivation

- Central question: DSH Base Bundle 中与 Agent 和模型相关的核心组件如何分工，又怎样共同把用户输入变成一次模型调用与后续工具执行？
- Why it matters to the user: Base Bundle 将 Agent Runtime 拆成多个小组件，这种分类和职责划分值得单独解释；旧文章范围过宽，没有把核心 Service 之间的边界讲清楚。
- Triggering questions or observations:
  - 文章重新聚焦“Agent 与模型核心”主题，并先修改标题方向。
  - 第一轮先理解 `ctx.sessions` 与 `ctx.agents` 对应的组件和代码区域。

## Reader and depth

- Target readers: 没有 DeepSeek Harness 项目背景、但知道 AI Agent 会调用模型和工具的普通技术读者。
- Assumed knowledge: 不要求熟悉 Cordis、事件溯源、TypeScript declaration merging 或 DSH 包结构。
- Intended technical depth: 用一次 Agent 运行作为主线，解释必要的源码结构与关键调用，不枚举无助于理解的内部类型。
- What readers should understand or be able to do afterward: 能说清 Session、Agent、AgentLoop、LLM、SystemPrompt 和 Tools 各自负责什么，并能沿源码找到一次模型请求的组装与执行路径。

## Information boundary

### In scope

- Base Bundle 中的 `session`、`agent`、`agent-loop`、`llm`、模型 Provider、`system-prompt`、`tools`。
- 为解释主链所必需的 `sessionProjections`、默认模型和重试行为。
- 关键 Service 的组件来源、进程内对象、职责边界和一次调用链。

### Out of scope

- Session 持久化、查询、telemetry 与 checkpoint 的完整实现；只在解释核心边界时提及。
- Shell、安全、Skills、Goal、Plan、Compaction、Subagent、Workflow 与 Web 等外围组件组。
- Web UI、API proxy 和特定产品入口的完整路由。

### Boundary still being negotiated

- `ctx.sessions` 的事件模型需要讲到多深：只解释追加式日志，还是展开 surface、projection 与 request header。
- 是否以 `ctx.agents.create()` 作为全文入口，还是先用结构图介绍所有核心 Service。
- 模型 Provider 之间的差异需要多少篇幅。

## Thesis and conclusions

### Candidate thesis

- DSH 没有把 Agent Runtime 做成一个包办一切的对象，而是把“事实记录”“活跃执行者”“循环驱动”“模型适配”“提示组装”和“工具执行”拆成独立 Service，再由 `agent-loop` 沿一次运行链把它们连接起来。

### Key conclusion candidates

- `ctx.sessions` 管理活跃 Session；真正的 `Session` 是普通对象，核心数据是一份只追加的事件日志。
- `ctx.agents` 管理活跃 Agent 和运行时所有权；它定义创建接口，但不实现 Agent 循环。
- `agent-loop` 向 `ctx.agents` 注册工厂，具体构造 `ReactLoopAgent`，并协调 Session 与 Agent 的发布和销毁顺序。
- 一个活跃 Agent 持有一个同 ID 的 Session；Agent 表示“现在能够继续运行的执行者”，Session 表示“已经发生过什么以及接下来模型能看到什么”的事实记录。
- Session 的进程内管理与磁盘持久化是两个边界；`dsh-session` 本身不负责写盘。

### Counterarguments and limitations

- “Session 就是聊天记录”过于简化：它还保存 turn、step、tool call、request header 等运行事件，并派生模型可见历史。
- “AgentRegistry 创建 Agent”容易误导：公开调用从 `ctx.agents.create()` 进入，但具体创建由注册的 `AgentFactory` 完成，默认实现来自 `agent-loop`。
- 当前结论只对应本地 `deepseek-harness` commit `d347e703908d0406b7a7ef80e3a0e594d86b2215`（2026-09-04），预稳定 API 可能变化。

## Evidence and examples

| Claim or example | Kind | Source | Confidence | How it may be used |
| --- | --- | --- | --- | --- |
| Base Bundle 将 `session` 和 `agent` 分别装载为 `@deepseek-ai/dsh-session` 与 `@deepseek-ai/dsh-agent` | Observed fact | `packages/bundle/base/cordis.patch.yml:33-34,67-68` | High | 解释组件名与 Service 名不是同一层概念 |
| `SessionStore extends Service` 并通过 `super(ctx, 'sessions')` 提供 `ctx.sessions` | Observed fact | `packages/core/session/src/index.ts:34-37,880-902` | High | 说明 `ctx.sessions` 的来源 |
| `Session` 是普通类，不是 Service；内部维护 `SessionEvent[]` 与 `SurfaceManager` | Observed fact | `packages/core/session/src/index.ts:427-454` | High | 区分注册表与单条 Session |
| `Session.append()` 验证并复制 JSON 数据，分配连续 seq，写入日志后通知观察者 | Observed fact | `packages/core/session/src/index.ts:663-749` | High | 解释 Session 是追加式事实记录 |
| `SessionStore` 提供 `create/prepare/enter/announce/get/list/flush/fork` 等生命周期操作 | Observed fact | `packages/core/session/src/index.ts:925-1191` | High | 展示 Service 的职责边界 |
| `dsh-session` 明确不实现持久化 | Observed fact | `packages/core/session/src/index.ts:880-885` | High | 防止把内存注册表与磁盘存储混为一谈 |
| `AgentRegistry extends Service` 并通过 `super(ctx, 'agents')` 提供 `ctx.agents` | Observed fact | `packages/core/agent/src/index.ts:27-41,239-292` | High | 说明 `ctx.agents` 的来源 |
| Registry 内部用 `Map<SessionId, AgentEntry>` 保存 Agent、owner、scope carrier 与生命周期标记 | Observed fact | `packages/core/agent/src/index.ts:216-226,250-253` | High | 解释它保存的是活跃 Agent 和运行时所有权 |
| Agent 的运行时接口包含 `session`、`inbox`、`status`、`ctx` 以及 send/followup/steer/inject | Observed fact | `packages/core/agent/src/runtime-types.ts:109-188` | High | 解释一个活跃 Agent 对象具有什么能力 |
| `ctx.agents.create/resume` 委托给已注册的 `AgentFactory` | Observed fact | `packages/core/agent/src/index.ts:176-207,355-425` | High | 纠正“AgentRegistry 自己实现循环”的误解 |
| `AgentLoop` 实现 `AgentFactory`，并在构造时调用 `ctx.agents.setFactory(this)` | Observed fact | `packages/core/agent-loop/src/index.ts:358-420` | High | 连接 agent 与 agent-loop 两个组件 |
| `AgentLoop` 构造 `ReactLoopAgent`，按 Session enter → Agent enter → Session announce → Agent announce 的顺序发布 | Observed fact | `packages/core/agent-loop/src/index.ts:645-667` | High | 作为后续讲解创建事务的入口 |
| Agent 与其 Session 必须共享同一个 ID | Observed fact | `packages/core/agent/src/index.ts:469-477` | High | 解释两个注册表如何关联同一运行实体 |

Source baseline: local `/Users/yangxiao/Documents/github repos/deepseek-harness`, commit `d347e703908d0406b7a7ef80e3a0e594d86b2215`.

## Terminology

| Term | Working definition | Translation or wording notes |
| --- | --- | --- |
| Component | Loader 装载的 Cordis 插件单元，例如 npm 包 `@deepseek-ai/dsh-session` | 正文首次出现时解释，不直接假设读者理解 Cordis |
| Service | 组件挂到 Context 上、供其他组件调用的共享能力，例如 `ctx.sessions` | 保留英文 Service，与源码一致 |
| SessionStore | `ctx.sessions` 指向的进程内 Session 注册表 | 不简称为“Session”，避免与单条 Session 混淆 |
| Session | 一条带 header 和追加式事件日志的运行记录对象 | 不能只称作聊天记录 |
| AgentRegistry | `ctx.agents` 指向的进程内活跃 Agent 注册表 | 它不是具体 Agent，也不是对话循环 |
| Agent | 持有 Session、Inbox、状态与作用域，并能被驱动继续工作的运行时对象 | 与模型本身区分 |
| AgentFactory | `ctx.agents.create/resume` 委托的具体创建实现 | 默认由 `AgentLoop` 实现 |
| AgentLoop | 创建 `ReactLoopAgent` 并驱动 turn、step、LLM call 和工具调用的 Service | 后续轮次重点探索 |

## Open questions

- 下一轮先沿 `ctx.agents.create()` 追踪 Agent 与 Session 的联合创建，还是先深入 Session 事件日志怎样变成模型消息？
- 正文是否需要介绍 `prepare → enter → announce` 三阶段发布，还是只保留它解决“避免半创建对象可见”的结论？
- `ctx.agents` 的 initiator scope 是否属于本文主线，还是留到工具调用和 subagent 相关话题？
- 新标题是否采用“DSH Agent 与模型核心：从 Session、Agent 到一次模型调用”，还是在探索完模型侧后再收窄？

## Outline options

### Option A：按一次调用链推进

1. Base Bundle 为什么把核心拆成多个 Service
2. `ctx.sessions`：记录已经发生的事实
3. `ctx.agents`：管理仍能继续工作的 Agent
4. `agent-loop`：创建 Agent，并把一轮工作向前推进
5. `system-prompt`、`tools` 与 Session 历史怎样组成 LLM 输入
6. `ctx.llm` 和 Provider 怎样完成流式模型调用
7. 模型输出、工具结果怎样重新写回 Session

### Option B：先画组件图，再拆职责

1. 六个核心 Service 的依赖图
2. 状态层：Session 与 Agent
3. 驱动层：AgentLoop
4. 请求组装层：SystemPrompt 与 Tools
5. 模型层：LLM Service 与 Provider
6. 用一次完整运行验证组件如何协作

## Decision log

| Date | Decision or discovery | Reason / user signal | Effect on the article |
| --- | --- | --- | --- |
| 2026-09-06 | 重新探索并重写现有 `dsh-agent-runtime` 文章 | 用户明确要求 | 正式正文暂不修改，先建立新的 discovery draft |
| 2026-09-06 | 范围集中到 Base Bundle 的“Agent 与模型核心”组件组 | 用户明确指定 topic | Shell、Skills、Subagent 等其他组件组不进入本文主线 |
| 2026-09-06 | 暂定标题为“DSH Agent 与模型核心：从 Session、Agent 到一次模型调用” | 用户要求先改标题；当前仍处于探索阶段 | 先作为 working title，进入正式写作后再同步修改中英文 frontmatter |
| 2026-09-06 | 第一轮从 `ctx.sessions` 与 `ctx.agents` 的组件、对象和源码边界开始 | 用户明确指定首个问题 | 后续决定先追创建链还是消息投影链 |
| 2026-09-06 | 使用本地 `deepseek-harness` commit `d347e703908d0406b7a7ef80e3a0e594d86b2215` 作为本轮证据基线 | 本地仓库 `master` 与 `origin/master` 一致 | 所有实现结论都绑定该预稳定源码版本 |

## Approved writing brief

Fill this section only when the user explicitly approves formal writing.

- Approved direction:
- Approved audience:
- Approved depth:
- Approved scope:
- Approved key conclusions:
- Approved outline:
