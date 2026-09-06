# DSH Base Bundle 与 Agent Runtime 候选选题

这份文档整理 DSH Base Bundle 中与 Agent Runtime 强相关的组件，作为后续选题与源码探索索引，不是正式文章。当前分类来自初步梳理；真正写作前，还需要回到对应版本的本地源码核对组件名称、依赖方向和启用条件。

## 整体阅读地图

Base Bundle 中约 85 个组件并不是彼此平行的功能清单。它们可以先按下面十类问题理解：

| 分类 | 主要回答的问题 | 核心 Service |
| --- | --- | --- |
| Agent 与模型核心 | 一次 Agent 运行由谁创建、驱动并调用模型？ | `ctx.agents`、`ctx.agentLoop`、`ctx.llm`、`ctx.tools`、`ctx.systemPrompt` |
| Session、持久化与投影 | 对话事件如何保存、查询并转换成可消费状态？ | `ctx.sessions`、`ctx.sessionPersistence`、`ctx.sessionProjections` |
| 设置、凭证与通用存储 | 配置、密钥和业务数据分别存在哪里？ | `ctx.settings`、`ctx.credentials`、`ctx.storage`、`ctx.storageDomain` |
| 本地执行与安全 | Shell 和文件操作怎样受到沙箱、审批与权限控制？ | `ctx.subprocess`、`ctx.sandbox`、`ctx.shell`、`ctx.fs` |
| 工具执行与后台任务 | 工具怎样注册、执行，并处理超时、长输出和后台进程？ | `ctx.tools`、`ctx.jobs`、`ctx.spillStore` |
| Agent 上下文与 Skills | Agent 怎样发现项目指令和可用 Skill？ | `ctx.skills`、`ctx.sessionProjections` |
| 人机交互、Goal、Plan 与 Todo | 用户交互和任务管理能力怎样接入 Agent？ | `ctx.userQuestions`、`ctx.commands`、`ctx.goals`、`ctx.planMode` |
| Compaction | 上下文过长时怎样测量、裁剪和压缩？ | `ctx.tokenMeter`、`ctx.toolResultPruner`、`ctx.compaction` |
| Subagent 与 Workflow | 子 Agent 怎样创建、通信并组成多轮工作流？ | `ctx.subagents`、`ctx.workflowEngine` |
| Web 搜索与抓取 | 模型怎样获得搜索和网页抓取能力？ | `ctx.web` |

从全局看，最值得先理解的主干是：

```text
                    ctx.sessionPersistence
                            │
                            ▼
ctx.sessions → ctx.agents → ctx.agentLoop
                                │
                ┌───────────────┼────────────────┐
                ▼               ▼                ▼
             ctx.llm         ctx.tools      ctx.systemPrompt
                ▲               ▲                ▲
                │               │                │
          模型 Provider      各类 tool-*       上下文插件
```

其余分类大多是在这条主干周围补充状态保存、安全边界、上下文管理和协作能力。

## 1. Agent 与模型核心

### 组件

- `session`
- `agent`
- `agent-loop`
- `llm`
- `llm-deepseek`
- `llm-pi-ai`
- `deepseek-llm-api-extensions`
- `session-log-deepseek`
- `plugin-package-inventory-deepseek`
- `llm-retry`
- `agent-default-model`
- `system-prompt`
- `tools`

### 主要 Service

| 组件 | Service |
| --- | --- |
| `session` | `ctx.sessions` |
| `agent` | `ctx.agents` |
| `agent-loop` | `ctx.agentLoop` |
| `llm` | `ctx.llm` |
| `deepseek-llm-api-extensions` | `ctx.deepseekLlmApiExtensions` |
| `agent-default-model` | `ctx.agentDefaultModel` |
| `system-prompt` | `ctx.systemPrompt` |
| `tools` | `ctx.tools` |

### 关键关系

- `agent-loop` 是最终执行者，硬依赖 `ctx.agents`、`ctx.sessions`、`ctx.llm`、`ctx.tools`、`ctx.systemPrompt` 和 `ctx.sessionProjections`。
- `llm-deepseek` 与 `llm-pi-ai` 是模型 Provider，向 `ctx.llm` 注册具体实现；它们读取 `ctx.settings` 和 `ctx.credentials`。
- `session-log-deepseek` 与 `plugin-package-inventory-deepseek` 向 `ctx.deepseekLlmApiExtensions` 注册字段，再由 `llm-deepseek` 使用。
- `llm-retry` 依赖 `ctx.agents` 与 `ctx.sessionProjections`，负责模型调用的重试行为。
- `agent-default-model` 提供默认模型选择，并允许 `ctx.settings` 覆盖。

### 候选问题

- `ctx.agentLoop` 怎样把一次用户输入拆成 Turn、Step、LLM call 与工具调用？
- 模型 Provider 的注册接口如何把 DeepSeek 与 Pi AI 隔离在统一的 `ctx.llm` 之后？
- 系统提示词、工具 Schema、Session 历史是在什么时候组合成模型输入的？
- `llm-retry` 如何判断可重试错误，重试又会不会改变 Session 事件？

## 2. Session、持久化与投影

### 组件

- `session-title`
- `session-title-llm`
- `session-persistence-jsonl`
- `attachment-local`
- `session-query-sqlite`
- `session-projection`
- `session-projection-cache`
- `session-telemetry-otel`
- `session-checkpoint-policy`

### 主要 Service

| 组件 | Service |
| --- | --- |
| `session-title` | `ctx.sessionTitle` |
| `session-persistence-jsonl` | `ctx.sessionPersistence` |
| `attachment-local` | `ctx.attachments` |
| `session-query-sqlite` | `ctx.sessionQuery` |
| `session-projection` | `ctx.sessionProjections` |
| `session-projection-cache` | `ctx.sessionProjectionCache` |
| `session-telemetry-otel` | `ctx.sessionTelemetry` |

### 关键关系

- `session-title` 从 `ctx.sessions` 取得 Session；`session-title-llm` 再利用 `ctx.llm` 注册标题生成器。
- `session-projection` 提供 `ctx.sessionProjections`，`session-projection-cache` 为投影结果增加缓存。
- `session-persistence-jsonl` 提供完整 Session 日志的持久化能力，并被 `agent-loop`、Session 查询和 checkpoint 策略使用。
- `session-checkpoint-policy` 同时关联 `ctx.sessions`、`ctx.llm`、`ctx.tools` 与 `ctx.sessionPersistence`。
- `attachment-local` 相对独立，向模型 Provider、文件工具和上层 API 提供本地附件存储。

### 候选问题

- 为什么 DSH 把 Session 事件日志与 Session 投影分开？
- JSONL 日志、SQLite 查询索引和投影缓存分别保存什么，谁才是事实来源？
- checkpoint 在什么条件下产生，恢复时又如何重建 Agent 可见状态？
- 附件如何从本地文件变成模型可消费的输入？

## 3. 设置、凭证与通用存储

### 组件

- `settings`
- `credentials`
- `storage`
- `storage-json`
- `storage-domain`

初步材料还出现了 `settings-file` 与 `credentials-local` 两个具体实现名，需要在写作前确认它们是否由 Base Bundle 直接装配。

### 主要 Service

| 组件 | Service 或作用 |
| --- | --- |
| `settings` | `ctx.settings` |
| `credentials` | `ctx.credentials` |
| `storage` | `ctx.storage` |
| `storage-domain` | `ctx.storageDomain` |
| `storage-json` | 向 `ctx.storage` 注册 JSON backend |

### 关键关系

- 设置和凭证分别流向 `llm-deepseek`、`llm-pi-ai`；设置还可以覆盖默认 Agent 模型。
- `storage-json` 向 `ctx.storage` 注册 backend，`storage-domain` 在其上提供面向业务记录的 `ctx.storageDomain`。
- `ctx.storageDomain` 可用于投影缓存、Web workspace 和 Web feedback。
- `ctx.sessionPersistence` 与 `ctx.storageDomain` 不能混为一谈：前者保存完整 Session 日志，后者保存 Workspace、投影缓存等业务记录。

### 候选问题

- DSH 为什么把 settings、credentials、storage 拆成不同边界？
- `ctx.storage` 与 `ctx.storageDomain` 的抽象层次有何差异？
- 替换 JSON backend 时，上层业务组件是否完全无感？

## 4. 本地执行与安全

### 组件

- `subprocess`
- `sandbox`
- `sandbox-policy`
- `bash-sandbox`
- `pwsh-sandbox`
- `fs-sandbox`
- `fs-observation-policy`
- `approval`
- `permission`
- `shell-env`

### 主要 Service

| 组件 | Service |
| --- | --- |
| `subprocess` | `ctx.subprocess` |
| `sandbox` | `ctx.sandbox` |
| `sandbox-policy` | `ctx.sandboxPolicy` |
| `bash-sandbox` / `pwsh-sandbox` | `ctx.shell` |
| `fs-sandbox` | `ctx.fs` |
| `approval` | `ctx.approval` |
| `permission` | `ctx.permissionPresets` |
| `shell-env` | `ctx.shellEnv` |

### 关键关系

- `ctx.subprocess`、`ctx.sandbox` 与 `ctx.sandboxPolicy` 共同支撑平台对应的 Shell Provider；Unix/macOS 使用 `bash-sandbox`，Windows 使用 `pwsh-sandbox`。
- `fs-sandbox` 在 `ctx.sandboxPolicy` 约束下提供 `ctx.fs`；文件事件还会交给 `fs-observation-policy`。
- `permission` 综合 `ctx.shell`、`ctx.approval`、`ctx.sessions` 和 `ctx.sessionProjections`，形成 `ctx.permissionPresets`。

### 候选问题

- 一条 Shell 命令从工具参数到子进程启动，依次经过哪些安全边界？
- sandbox policy、permission preset 与人工 approval 各自解决什么问题？
- 文件观察策略如何把 Agent 对工作区的修改转成可审计事件？
- Bash 与 PowerShell Provider 如何保持跨平台行为一致？

## 5. 工具执行与后台任务

### 组件

- `jobs`
- `tool-bash`
- `tool-pwsh`
- `tool-jobs`
- `tool-fs`
- `tool-fs-search`
- `tool-str-replace-editor`
- `timeout-policy`
- `spill-local`
- `spill-policy`
- `repeat-tool-reminder`

这一组中只有 `jobs` 与 `spill-local` 产生独立 Service：

| 组件 | Service |
| --- | --- |
| `jobs` | `ctx.jobs` |
| `spill-local` | `ctx.spillStore` |

### 关键关系

- `tool-bash` 与 `tool-pwsh` 使用 `ctx.shell`、`ctx.shellEnv` 和 `ctx.systemPrompt`，并向 `ctx.tools` 注册模型工具。
- Shell 工具可以向 `ctx.jobs` 注册后台进程，`tool-jobs` 再把后台任务管理能力暴露给模型。
- `tool-fs` 和 `tool-str-replace-editor` 基于 `ctx.fs`；`tool-fs-search` 基于 `ctx.subprocess`。
- 文件工具还会向 `ctx.systemPrompt` 贡献使用说明。
- `timeout-policy`、`spill-policy` 与 `repeat-tool-reminder` 注册的是工具执行流水线，不会增加新的模型工具名。
- `spill-local` 提供 `ctx.spillStore`，供 `spill-policy` 保存过大的工具结果。

### 候选问题

- 一个工具从注册、进入模型 Schema 到真正执行，完整路径是什么？
- 工具策略如何在不改变工具名称的情况下包裹所有调用？
- 后台 Job 怎样跨越一次模型调用继续运行，又怎样把结果带回 Agent？
- 超长工具结果为什么需要 spill，而不是直接全部写进 Session？

## 6. Agent 上下文与 Skills

### 组件

- `agent-instructions`
- `skill`
- `skill-filesystem`
- `skill-badge`（默认关闭）
- `tool-skill`

### 主要 Service 与关系

- `skill` 提供 `ctx.skills`。
- `skill-filesystem` 向 `ctx.skills` 注册本地 Skill，`skill-badge` 可以注册额外 Skill，但默认关闭。
- `tool-skill` 同时使用 `ctx.skills` 与 `ctx.agents`，并向 `ctx.tools` 注册 Skill 相关工具。
- `agent-instructions` 根据 `ctx.sessionProjections`，为 Agent 请求补充 `AGENTS.md` 等项目上下文。

### 候选问题

- `AGENTS.md` 在哪一阶段被发现、裁剪并注入模型输入？
- Skill 的说明、资源与工具分别如何加载？
- 文件系统 Skill 与其他 Skill Provider 是否具有相同的生命周期？
- Agent instructions 与 system prompt 的职责边界在哪里？

## 7. 人机交互、Goal、Plan 与 Todo

### 组件

- `user-questions`
- `commands`
- `command-feedback`
- `goal`
- `goal-round-driver`
- `command-goal`
- `plan-mode`
- `tool-goal`
- `tool-todo`

### 主要 Service

| 组件 | Service |
| --- | --- |
| `user-questions` | `ctx.userQuestions` |
| `commands` | `ctx.commands` |
| `goal` | `ctx.goals` |
| `plan-mode` | `ctx.planMode` |

### 关键关系

- `command-feedback` 与 `command-goal` 向 `ctx.commands` 注册命令，后者还会操作 `ctx.goals`。
- `goal` 使用 `ctx.agents` 与 `ctx.sessionProjections`，再由 `command-goal`、`goal-round-driver` 和 `tool-goal` 从不同入口消费。
- `goal-round-driver` 还依赖 `ctx.sessions`，`tool-goal` 则向 `ctx.tools` 注册模型工具。
- `plan-mode` 联结 `ctx.sessionProjections`、`ctx.systemPrompt` 与 `ctx.tools`。
- `tool-todo` 使用 `ctx.sessionProjections` 并向 `ctx.tools` 注册 Todo 工具。
- `ctx.userQuestions` 在 Base 中只建立交互能力；具体的 `tool-ask-user` 由上层 composition 或 preset 挂载。

### 候选问题

- Goal、Plan 与 Todo 是三套独立状态，还是同一任务管理流程的不同视图？
- `goal-round-driver` 如何让长期任务跨多轮持续推进？
- Plan mode 如何改变提示词、工具列表与用户交互方式？
- 为什么 `user-questions` 只提供底层能力，而模型工具由上层决定是否暴露？

## 8. Compaction

### 组件

- `token-meter`
- `tool-result-pruner`
- `compaction-basic`
- `command-compact`

### 主要 Service

| 组件 | Service |
| --- | --- |
| `token-meter` | `ctx.tokenMeter` |
| `tool-result-pruner` | `ctx.toolResultPruner` |
| `compaction-basic` | `ctx.compaction` |

### 关键关系

- `token-meter` 基于 `ctx.sessionProjections` 测量上下文规模。
- `tool-result-pruner` 使用 token 测量结果裁剪过大的工具输出。
- `compaction-basic` 结合 `ctx.tokenMeter`、`ctx.toolResultPruner`、`ctx.llm` 与 `ctx.sessions` 生成压缩后的上下文。
- `command-compact` 通过 `ctx.commands` 提供人工触发入口。

整体过程可以先理解为：

```text
测量 token
  → 裁剪过大的工具结果
  → 必要时总结上下文
  → /compact 提供人工触发入口
```

### 候选问题

- 自动 compaction 的阈值由谁决定？
- 工具结果裁剪和对话总结的执行顺序会怎样影响信息保真度？
- 压缩结果作为新事件保存，还是直接替换原有历史？
- 手动 `/compact` 与自动压缩是否走同一条实现路径？

## 9. Subagent 与 Workflow

### 组件

- `subagent`
- `subagent-spawn-in-process`
- `subagent-fork-in-process`
- `tool-subagent-control`
- `tool-subagent-list-agents`
- `tool-subagent`
- `tool-subagent-fork`
- `workflow-worker-thread`
- `tool-workflow`
- `tool-ralph`

### 主要 Service

| 组件 | Service |
| --- | --- |
| `subagent` | `ctx.subagents` |
| `workflow-worker-thread` | `ctx.workflowEngine` |

### 关键关系

- `subagent-spawn-in-process` 与 `subagent-fork-in-process` 分别向 `ctx.subagents` 注册 `spawn` 和 `fork` Provider。
- `tool-subagent-control` 提供 `send_message` 与 `interrupt_agent`。
- `tool-subagent-list-agents` 额外依赖 `ctx.agents`，用于列出 Agent。
- `tool-subagent` 使用 `spawn` Provider，`tool-subagent-fork` 使用 `fork` Provider；这些组件最终都向 `ctx.tools` 注册模型工具。
- `workflow-worker-thread` 在 `ctx.subagents` 之上提供 `ctx.workflowEngine`，再由 `tool-workflow` 和 `tool-ralph` 暴露给模型。
- `tool-ralph` 还直接依赖 `ctx.subagents`，因为它固定使用多轮子 Agent 工作流。

### 候选问题

- `spawn` 与 `fork` 创建 subagent 时，初始上下文和状态继承有什么不同？
- DSH 如何维护 Agent 树、运行状态、消息投递和完成结果？
- worker thread 是操作系统线程、JavaScript Worker，还是工作流层面的抽象？
- 普通 subagent 工具、workflow 与 Ralph 分别适合什么任务？

## 10. Web 搜索与抓取

这里的 Web 指模型使用的网络能力，不是浏览器 GUI。

### 组件

- `web`
- `web-search-deepseek`
- `web-fetch-http`
- `tool-web`

### 主要 Service 与关系

- `web` 提供 `ctx.web`。
- `web-search-deepseek` 向 `ctx.web` 注册 `searchProvider="deepseek-official"`。
- `web-fetch-http` 向 `ctx.web` 注册 `fetchProvider="http"`。
- `tool-web` 使用 `ctx.web`，向 `ctx.tools` 注册模型工具，并向 `ctx.systemPrompt` 贡献说明。

### 候选问题

- 搜索与抓取为什么被抽象成两个 Provider？
- `tool-web` 如何决定何时搜索、何时直接抓取 URL？
- 网络结果怎样进入 Session，又会受到哪些长度与安全策略约束？

## 建议的探索顺序

如果后续继续研究 Agent Runtime，可以按依赖从主干向外围推进：

1. `session`、`agent`、`agent-loop`：先走通一次 Agent 运行。
2. `llm`、`system-prompt`、`tools`：解释一次 LLM call 是怎样组装和执行的。
3. Session 持久化与投影：说明运行状态怎样保存并重建。
4. 本地执行、安全与工具策略：追踪一次真实工具调用。
5. instructions、Skills、Goal、Plan 与 Compaction：理解模型上下文如何动态变化。
6. Subagent、Workflow 与 Web：最后研究并行协作和外部信息获取。

这样的顺序能先建立 Agent Runtime 主链，再逐渐加入支撑能力，避免一开始就被 85 个组件名称淹没。
