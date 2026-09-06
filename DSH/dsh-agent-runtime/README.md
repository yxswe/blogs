---
title: "Loader 启动之后：DSH Agent 如何运行"
description: 沿着 Agent 的入口与一次完整运行链路，分析 Loader 建立组件运行时后，DSH Agent 如何由各个基础组件协同驱动。
lang: zh
translationKey: dsh-agent-runtime
date: 2026-08-30
tags:
  - DeepSeek Harness
  - Cordis
featured: false
---

上一篇讲清了 DSH 如何从 Profile 组合组件树，以及 Loader 如何把这棵树变成由 Context 与 Fiber 组成的运行时。接下来要回答的是：运行时建立以后，一个 DSH Agent 究竟从哪里启动，又是怎样运行起来的？

先给出最重要的结论：在 Web Profile 中，Loader 启动完成只代表 Agent 所需的基础 Service 已经就绪，并不代表 Agent 实例已经存在。创建 Agent 与驱动 Agent 运行是两个不同的入口。

## 1. Loader 启动完成后，Web Agent 还没有创建

`dsh-base` 会先把 Agent 运行所需的核心组件放进宿主组件树：

| 组件 | 提供的 Service | 作用 |
| --- | --- | --- |
| `@deepseek-ai/dsh-agent` | `ctx.agents` | 定义 Agent 接口，保存当前进程中的 Agent，并提供创建入口 |
| `@deepseek-ai/dsh-session` | `ctx.sessions` | 保存实时 Session；Session 内的事件日志是对话历史的事实来源 |
| `@deepseek-ai/dsh-llm` | `ctx.llm` | 注册模型 Adapter，并提供流式模型调用入口 |
| `@deepseek-ai/dsh-system-prompt` | `ctx.systemPrompt` | 组合系统提示词、运行时上下文和工具 Schema |
| `@deepseek-ai/dsh-tools` | `ctx.tools` | 注册工具，并执行权限检查、调用和结果处理 |
| `@deepseek-ai/dsh-agent-loop` | `ctx.agentLoop` | 创建具体 Agent，并驱动 Turn、Step、模型调用和工具调用 |

其中，`dsh-agent-loop` 明确依赖前五个 Service：

```ts
static inject = ['agents', 'sessions', 'llm', 'tools', 'systemPrompt']
```

不过 Web Profile 中的 `agent-loop` 初始配置是：

```yaml
- id: agent-loop
  name: '@deepseek-ai/dsh-agent-loop'
  config:
    agents: []
```

空的 `agents` 表示启动时不自动创建 Agent。此时 `ctx.agents`、`ctx.sessions`、`ctx.llm` 等基础 Service 已经可用，Web Server 也已经开始监听，但真正的 Agent 要等浏览器创建或恢复 Session 时才产生。

## 2. Agent 有两个入口：创建与运行

### 2.1 `session.create` 创建 Agent

浏览器新建对话时，请求最终进入 Host 侧 `api-proxy` 的 `session.create`。它先通过 `ensureSession()` 判断目标 Session 的状态：

- 已经有同 id 的实时 Agent，直接复用；
- 磁盘中已有 Session，通过 `ctx.agents.resume()` 恢复；
- 否则通过 `ctx.agents.create()` 新建。

`ctx.agents` 是 `dsh-agent` 提供的 Agent Registry。它只定义创建接口和保存实时 Agent，并不实现对话循环。`dsh-agent-loop` 启动时会把自己注册成 Registry 的工厂：

```ts
ctx.agents.setFactory(this)
```

因此，`ctx.agents.create()` 最终会委托给 `AgentLoop.createAgent()`。创建过程可以简化为：

```text
session.create
    ↓
api-proxy.ensureSession()
    ↓
ctx.agents.create()
    ↓
AgentLoop.createAgent()
    ├── 准备 Session
    ├── 创建 ReactLoopAgent
    ├── 创建 Agent Context 与 Inbox
    ├── 应用 Agent Preset
    └── 发布 Session 和 Agent
```

具体的 Agent 实例是 `ReactLoopAgent`。它不是 Loader 直接创建的组件 Fiber，而是 `AgentLoop` 在运行时构造的普通对象。它持有自己的 Session、Inbox 和一个带 Agent 作用域的 Context：

```ts
this.scope = createScope(loopCtx, this)
this.ctx = this.scope.ctx.extend({ agent: this })
```

发布前，`api-proxy` 还会通过 `setup(agentCtx)` 应用选中的 Agent Preset。以默认的 `standard` 为例，Preset 决定这个 Agent 能看到哪些 persona、指令和工具；任何一项加载失败，整个 Agent 创建都会回滚，不会留下只加载了一半的 Session。

创建成功后，Agent 已经登记在 `ctx.agents`，Session 也已经登记在 `ctx.sessions`，但 Agent 的状态仍是 `idle`，还没有请求模型。

### 2.2 `session.prompt` 唤醒 Agent

用户发送消息时，请求进入 `api-proxy` 的 `session.prompt`。Host 完成模型可用性、时区和附件检查后，把输入整理成 `UserMessage`，再根据请求模式调用：

```ts
if (mode === 'steer') agent.steer(message)
else agent.followup(message)
```

两者都会把消息写入 Agent 的 Inbox 并唤醒驱动器：

- `followup()` 把消息放入 `next-turn`，用于开始一个普通的新 Turn；
- `steer()` 把消息放入 `next-step`，空闲时会启动 Turn，运行中则在下一个 Step 接收；
- `inject()` 也写入 `next-step`，但不会主动唤醒 Agent，通常用于给下一次模型请求补充上下文。

真正让 Agent 从 `idle` 进入 `running` 的入口是 `ReactLoopAgent.wakeDriver()`。它启动 `kick()`，随后循环处理 Turn 和 Step。

## 3. Agent 实例里有什么

`dsh-agent` 定义的 `Agent` 接口只包含运行一个 Agent 所需的状态和操作：

| 成员 | 作用 |
| --- | --- |
| `id` | Agent 与 Session 共用的唯一 id |
| `options` | 当前模型的 provider、model 和输出 token 上限 |
| `session` | 当前对话及其追加式事件日志 |
| `inbox` | 尚未进入模型请求的 follow-up、steering 和注入消息 |
| `status` | `idle` 或 `running` |
| `ctx` | 带有当前 Agent 作用域的 Context |
| `followup()` | 排队一个普通的新 Turn，并唤醒 Agent |
| `steer()` | 把消息送到最近的下一个 Step，并唤醒 Agent |
| `inject()` | 给下一个 Step 增加上下文，但不唤醒 Agent |
| `cancel()` | 中止当前活动，可选择是否保留 Inbox |
| `whenIdle()` | 等待 Agent 完全回到空闲状态 |

`Agent` 接口与 `ReactLoopAgent` 实现分开放置：其他组件只依赖 `ctx.agents` 和 `Agent` 接口，不需要知道默认循环类的存在。以后替换循环实现时，入口组件不需要改成直接构造另一个类。

## 4. 一次 Agent 运行如何完成

DSH 把一次对话分成 Turn 和 Step：

- **Turn** 从一条唤醒消息开始，到当前工作全部完成为止；
- **Step** 是一次模型请求，以及这次请求产生的工具调用。

一个 Turn 可以包含多个 Step。例如，模型先要求读取文件，工具返回结果后，Agent 还要再次请求模型，才能生成最终回答。

```text
session.prompt
    ↓
followup() / steer()
    ↓
Inbox 写入消息，wakeDriver() 唤醒 Agent
    ↓
turn/start
    ↓
领取 Inbox 消息，组装提示词与工具 Schema
    ↓
step/start → user/message
    ↓
从 Session 日志生成消息历史
    ↓
agent/request → ctx.llm → 模型流
    ↓
assistant/chunk → assistant/message
    ↓
有工具调用？── 否 ──→ step/end → turn/end
    │
    是
    ↓
tool/call → ctx.tools 执行 → tool/result
    ↓
进入下一个 Step
```

### 4.1 请求模型之前

每个 Step 开始时，Agent 先从 Inbox 领取本轮消息，然后调用 `ctx.systemPrompt.assemble()`。这里会收集当前 Agent 作用域内的 persona、指令、动态上下文和工具 Schema，再经过 `agent/pre-step` 扩展点决定是否进入这一步。

通过准入后，消息会作为 `user/message` 写入 Session。随后 Agent 从 Session 日志调用 `deriveMessages()` 重建模型历史，而不是维护另一份独立的聊天数组。`agent/request` 扩展点确定 provider、model 等请求配置，最后由 `ctx.llm` 找到对应 Adapter 并开始流式调用。

### 4.2 模型返回以后

模型产生的每个分片都会记录成 `assistant/chunk`，流结束后再写入完整的 `assistant/message`。如果消息中没有工具调用，这个 Step 完成，Turn 也可以结束。

如果消息中包含工具调用，AgentLoop 会把它们交给 `ctx.tools`。每次调用都会依次经过权限检查、工具执行和结果处理，并在 Session 中记录 `tool/call` 与 `tool/result`。工具结果随后成为下一 Step 的上下文，Agent 再次请求模型。这个过程持续到模型不再调用工具、工具明确结束 Turn、发生错误或用户取消。

结束时，Session 写入 `step/end` 和 `turn/end`，Agent 回到 `idle`。Web UI 主要通过 Session 事件显示流式文本、工具调用和结果，通过 `agent/status` 显示 Agent 当前是否正在运行。

## 5. 基础运行时与 Agent Preset 的分工

Web Profile 不会为每个 Agent 复制整套宿主服务。Session Registry、Agent Registry、LLM Adapter、Tool Registry、持久化、Sandbox 和 API Gateway 等能力留在宿主运行时中；Agent Preset 只决定某类 Agent 能使用哪些面向模型的组件。

默认 `standard` Preset 会加入 persona、项目指令、Shell、文件操作、搜索、Skills、目标、计划模式、上下文压缩、子 Agent、工作流、用户提问和 Todo 等组件。`minimal` Preset 则只保留固定 persona、持久 Bash 与文件编辑器。

因此，同一套 `AgentLoop` 可以驱动能力完全不同的 Agent：循环仍然只负责“读取消息、请求模型、执行工具、继续下一步”，具体提示词、工具、策略和外围能力都由组件组合决定。

## 参考资料

- [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)
- [`dsh-base` 组件树](https://github.com/deepseek-ai/deepseek-harness/blob/main/packages/bundle/base/cordis.patch.yml)
- [`dsh-agent`](https://github.com/deepseek-ai/deepseek-harness/tree/main/packages/core/agent)
- [`dsh-agent-loop`](https://github.com/deepseek-ai/deepseek-harness/tree/main/packages/core/agent-loop)
- [`dsh-host-apiproxy`](https://github.com/deepseek-ai/deepseek-harness/tree/main/packages/host/apiproxy)
- [默认 Standard Agent Preset](https://github.com/deepseek-ai/deepseek-harness/tree/main/apps/cli/config/agent-presets/standard)
