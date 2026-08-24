---
title: "DSH 如何基于 Cordis 构建"
description: 从 Cordis 的动态组合模型出发，沿着启动、Agent Loop、Session、Service 与 Agent Preset 理清 DeepSeek Harness 的整体架构及插件化边界。
lang: zh
translationKey: dsh-cordis-architecture
date: 2026-08-24
tags:
  - Agent Harness
  - DeepSeek
featured: false
---

# DSH 如何基于 Cordis 构建

上一篇文章从论文出发解释了 Cordis 的 Revertible Effects、Reactive Coeffects、Context 与 Fiber。这一篇换一个视角：不再单独研究 Cordis，而是沿着 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 的实际代码回答五个问题：

1. Cordis 在 DSH 中到底处于哪一层？
2. DSH 如何理解 Agent？
3. 整个系统被划分成了哪些重要 Service？
4. 哪些能力可以替换，替换是如何发生的？
5. “Everything is a plugin” 的边界在哪里？

先给出一句话结论：

> Cordis 没有定义 Agent；它提供了组织动态系统的运行时规则。DSH 在其上定义 Agent、Session、LLM、Tools 等领域接口，再用插件提供默认实现，最终由配置把这些实现组合成一个可运行的 Harness。

## 1. 先回顾 Cordis 论文：它提供的是组合规则

Cordis 论文 [*A Programming Paradigm for Spatiotemporal Composability*](https://github.com/cordiverse/paper/blob/main/paper.pdf) 研究的不是 Agent，而是一个更基础的问题：当组件能在运行时加入、退出或替换时，系统怎样继续保持一致？

论文把问题拆成两个维度：

| 问题 | Cordis 的回答 |
| --- | --- |
| 一个组件退出后，如何撤销它注册的监听器、Service、后台任务等影响？ | Revertible Effects：组件产生影响时同时登记清理操作，由运行时在卸载时逆序执行。 |
| 一个组件依赖的 Service 出现、消失或换成另一份实现后，它该如何响应？ | Reactive Coeffects：组件声明依赖，运行时在 Service 变化后重新判断依赖是否满足，并驱动组件激活、卸载或重载。 |

这两个机制在 `Context` 中汇合：组件从 Context 读取 Service，也通过 Effect 修改 Context。一个组件的每次运行实例是 `Fiber`，Fiber 保存依赖快照、运行状态和清理操作。Loader 再把声明式配置变成 Fiber 树，并负责配置协调与模块热替换。

因此 Cordis 是一个 meta-framework：它不规定系统必须有模型、工具或 Session，只提供下面这套通用语法：

```text
组件声明需要哪些 Service
          ↓
依赖满足后，Cordis 激活组件 Fiber
          ↓
组件提供 Service、注册监听器或产生其他 Effect
          ↓
Service 变化触发依赖组件重新计算生命周期
          ↓
组件退出时，Cordis 撤销 Fiber 记录的 Effect
```

DSH 做的事情，是把 Agent Harness 的产品概念放进这套语法。

## 2. DSH 的整体结构：配置先于代码入口

传统应用通常有一个固定的 `main()`，由它按顺序创建数据库、模型客户端、工具和 Web Server。DSH 的启动方式不同：入口先解析一个 Profile，再把多层配置合成为一棵 Cordis 组件树。

默认组合大致如下：

```text
Profile
├── dsh-base：Session、Agent、LLM、Tools、持久化、Sandbox 等共享能力
├── dsh-web-app 或 dsh-headless：Web 界面或一次性任务入口
├── 当前 Profile 的 cordis.patch.yml
├── Harness Home 的全局 patch
└── 命令行 --patch
          ↓
最终的 Cordis 配置树
          ↓
Loader 导入组件并创建 Fiber
          ↓
依赖满足的组件自动激活
```

后应用的 patch 可以按稳定的行 `id` 替换前面的配置、禁用一行或插入新组件。行在文件中的先后顺序不是启动顺序；真正的启动顺序由组件声明的 Service 依赖决定。这正是 Reactive Coeffects 在 DSH 启动阶段的直接用途。

[`dsh-base` 的默认配置](https://github.com/deepseek-ai/deepseek-harness/blob/main/packages/bundle/base/cordis.patch.yml) 不是少量“扩展插件”，而是整个产品的默认实现：Agent、Loop、模型适配器、Session 持久化、工具、权限、Sandbox、Skill、Subagent、Compaction 和 Web Search 都是普通配置行。[Web Bundle](https://github.com/deepseek-ai/deepseek-harness/blob/main/packages/bundle/web-app/cordis.patch.yml) 再添加 Host API、HTTP Server 和浏览器插件，同时把适合单个 Agent 的工具移入 Agent Preset。

所以理解 DSH 的第一步不是寻找唯一的主函数，而是查看最终组合：

```sh
dsh --profile web --dump-config
```

它展示的才是当前机器真正运行的系统。

## 3. Component、Service 与 Event 分别是什么

这三个概念容易混在一起，但它们承担不同职责。

### Component：一段有生命周期的实现

一个 Cordis 插件就是一个 Component。它可以是一段函数、一个带 `apply(ctx)` 的对象，或者一个继承 `Service` 的类。Loader 中的一行配置会挂载一个 Component，并产生一个 Fiber。

Component 可以提供 Service，也可以只注册工具、Prompt Section 或 Event Listener，因此 Component 和 Service 不是一一对应关系。

### Service：组件之间使用能力的稳定名字

Service 是 Context 中以 `ctx.<key>` 暴露的能力。例如：

- `ctx.llm`：模型适配器注册与流式调用；
- `ctx.sessions`：内存中的 Session Store；
- `ctx.tools`：工具注册与执行管线；
- `ctx.fs`：文件系统能力；
- `ctx.agentLoop`：默认 Agent 驱动器。

一个完整的可替换能力通常包含三种角色：定义 Service 接口的组件、提供具体实现的组件、使用这个 Service 的组件。例如文件系统能力中，`dsh-fs` 定义 `ctx.fs`，`dsh-fs-local`、`dsh-fs-sandbox` 或 `dsh-fs-e2b` 提供不同实现，而文件工具只依赖 `ctx.fs`，不直接依赖某个具体实现。

### Event：不替换 Service 也能介入流程

Service 适合直接调用能力，Event 适合观察或拦截流程。DSH 的关键路径提供了多种事件：

- Session Event 记录必须持久化的事实；
- `agent/*` Event 处理正在运行的 Agent；
- `tools/*`、`llm/*`、`fs/*` Event 为策略和中间件提供扩展点。

例如一个插件不必替换整个 Agent Loop，就可以在 `agent/pre-step` 中修改即将进入模型的消息，在 `agent/request` 中调整请求配置，或者在 `tools/execute` 中加入权限、超时和审计策略。

## 4. DSH 如何理解 Agent

DSH 中的 Agent 不是 LLM，也不是“Prompt + Tools”的静态配置。代码中的 [`Agent` 接口](https://github.com/deepseek-ai/deepseek-harness/blob/main/packages/core/agent/src/runtime-types.ts) 更接近一个正在运行的会话控制器，它包含：

- 与 Session 共用的唯一 `id`；
- 当前模型路由和模型选项；
- 一个持有持久事实的 `session`；
- 一个保存待处理输入的 `inbox`；
- `idle` 或 `running` 状态；
- 只属于这个 Agent 的 `agent.ctx`；
- `followup()`、`steer()`、`inject()`、`cancel()` 等控制方法。

这里有三个关键拆分。

### Agent Registry 与 Agent Loop 是分开的

`ctx.agents` 管理当前进程中的 Agent，负责创建、查找、所有权与生命周期，但不执行模型循环。具体创建和驱动由 `ctx.agentLoop` 提供，默认实现是 `dsh-agent-loop`。因此 UI、ACP、SDK 和 Subagent 只依赖稳定的 Agent Service，不需要直接依赖默认 Loop。

换句话说，DSH 把“Agent 是什么”与“Agent 如何运行”分开了：

```text
ctx.agents       = 稳定的 Agent 管理接口
ctx.agentLoop    = 当前采用的运行算法
ReactLoopAgent   = 默认 Loop 创建出的 Agent 实例
```

### Session 是事实，Agent 是活的控制面

Session 是一个 append-only 的 `SessionEvent` 日志。消息历史不是另一份可变数组，而是每次从日志的有效 Surface 推导出来。Turn、Step、模型输出块、工具调用与结果都会写入日志。

项目坚持一条重要规则：**模型可见的内容必须被记录。** 只要某段信息进入模型请求，就必须能从 Session Log 重建。这让 Resume、Fork、Compaction、Telemetry 和 UI Replay 都基于同一份事实，而不是各自维护容易漂移的状态。

Agent 则是进程内的活动对象：它管理 Inbox、取消信号、当前运行状态和 scoped Context。进程重启后可以从持久化 Session 重建新的 Agent，但旧 Agent 本身以及它持有的进程内资源不会被序列化。

### Turn 和 Step 是默认 Loop 的运行单位

默认 Loop 的一次运行路径可以压缩为：

```text
输入进入 Agent Inbox
        ↓
打开 Turn，并领取 next-turn / next-step 输入
        ↓
agent/pre-step：允许插件拒绝或改写输入
        ↓
组装 System Prompt 与当前可见的 Tool Schema
        ↓
从 Session Log 推导模型历史，调用 ctx.llm
        ↓
把 Stream Chunk 与最终 Assistant Message 写回 Session
        ↓
通过 ctx.tools 执行 Tool Call，并记录 Tool Result
        ↓
如仍有工具结果或 Steering，开始下一个 Step；否则结束 Turn
```

因此一个 Turn 可以包含多个 Step；一个 Step 是一次模型请求及其触发的工具执行。Agent Loop 本身很薄，它把行为委托给 `sessions`、`systemPrompt`、`llm` 和 `tools`，并在这些边界上发出 Event。

## 5. DSH 的重要 Service 如何分层

仓库中有很多 Service，但可以按职责压缩成六层：

| 层 | 重要 Service | 作用 |
| --- | --- | --- |
| Agent 核心骨架 | `sessions`、`agents`、`agentLoop`、`systemPrompt`、`tools`、`llm` | 保存事实、驱动 Turn/Step、组装请求、调用模型和工具。 |
| 执行环境 | `fs`、`subprocess`、`shell`、`terminals`、`sandbox`、`sandboxPolicy`、`lsp`、`codeRuntime` | 把模型动作落到本地、受限环境或远程 Sandbox。 |
| Agent 能力 | `skills`、`web`、`subagents`、`workflowEngine`、`jobs`、`compaction`、`goals`、`planMode` | 在核心循环之外增加检索、委派、工作流、长任务和上下文管理。 |
| 数据与恢复 | `sessionPersistence`、`sessionQuery`、`sessionProjections`、`attachments`、`spillStore`、`storage` | 持久化日志、查询 Session、生成投影和保存大对象。 |
| 配置与人机协作 | `settings`、`credentials`、`approval`、`permissionPresets`、`commands`、`userQuestions` | 管理配置、凭证、权限、命令与用户确认。 |
| 交付界面 | `typert`、`typertGateway`、`apiProxy`、`webServer`、`clientModules`、浏览器端 `slots` | 把 Host 能力安全地投影到 SDK、API 和 Web UI。 |

最核心的依赖链是：

```text
Agent Loop
├── sessions：读取和追加持久事实
├── systemPrompt：收集 Prompt Section 与 Tool Schema
├── llm：选择模型适配器并产生流
└── tools：查找工具并经过受控执行管线
      ├── fs / shell / web / subagents / workflow ...
      └── approval / sandbox / timeout / spill 等策略
```

这也是 DSH 对 Agent 的核心判断：Agent 不是一个巨大的自主对象，而是一个很小的运行控制器；大部分能力位于它依赖的 Service 和 Event 扩展点中。

## 6. 哪些 Service 可以覆盖，以及如何覆盖

“可替换”在 DSH 中至少有四种不同含义。

### 6.1 替换一个单实例 Service 的实现

同一个 Context realm 中，一个 Service 名只能有一份实现。第二个组件直接提供同名 Service 会报错，而不是悄悄覆盖。因此替换 `ctx.fs`、`ctx.shell` 或 `ctx.sessionPersistence` 的正确方式，是在配置层禁用或替换原来的行，再挂载兼容实现。

典型的可替换能力包括：

- Session Persistence：JSONL 或 SQLite；
- Filesystem：Local、Sandbox 或 E2B；
- Subprocess：Local 或 E2B；
- Shell：本地 Bash、Sandbox Bash 或 PowerShell；
- Sandbox、Code Runtime、Compaction、Workflow Engine、Spill Store；
- Agent Loop 本身。

这里的“兼容”很重要：替换组件仍要提供相同的 Service 接口和生命周期语义，否则依赖者虽然能被激活，运行时行为仍会错误。

### 6.2 保留注册表 Service，替换或增加其中的条目

另一些 Service 本身就是注册表，常见扩展方式不是替换整个 Service，而是向其中注册条目：

- `ctx.llm` 按 provider route 注册模型适配器；
- `ctx.tools` 按工具名注册 Tool Definition；
- `ctx.systemPrompt` 按名称注册 Section、Variable 和 Context；
- `ctx.web` 按 id 注册 Search / Fetch 实现；
- `ctx.skills` 注册 Skill 来源；
- `ctx.subagents` 注册不同的 Subagent 实现。

同一层出现重复名称通常会失败；在 Agent Scope 中注册时，则可以对该 Agent 遮蔽同名的全局条目。例如一个 Agent 可以拥有自己的 Persona、工具版本或能力限制，而不影响其他 Agent。

### 6.3 用 `isolate` 为某个组合建立私有 Service 空间

Cordis 的 `isolate` 让同一个 Service 名在不同 realm 中解析到不同实现。DSH 的 Agent Preset 使用它承载真正属于单个组合的 Service。

例如 [`minimal` preset](https://github.com/deepseek-ai/deepseek-harness/blob/main/apps/cli/config/agent-presets/minimal/agent.cordis.yml) 在自己的 realm 中提供 `terminals`，并用一个本地 `fs` 遮蔽 Host 的 Sandbox 文件系统。其他 Agent 仍然使用 Host 原来的实现。

但不是所有 Service 都适合放入 Agent realm。Session Store、持久化、Sandbox Policy、模型路由、Subagent Registry 等被 Host 或多个 Session 共同使用，必须留在 Host Plane。Preset 中新增一个会提供 Service 的组件时，如果它不属于 Host，就必须显式放入 `isolate`；否则它会泄漏到进程级空间并与其他 Preset 冲突。

### 6.4 不替换 Service，只通过 Event 改写行为

很多需求根本不需要替换 Service：

- 模型请求重试可以包裹 `llm/stream`；
- Compaction 可以介入 `agent/pre-step`；
- Tool Timeout 可以介入工具执行管线；
- 权限与文件观察策略可以监听能力事件；
- Goal Driver 可以在 Turn 即将结束时继续 Steering。

这种扩展保留核心 Service，只替换某一段决策，更容易与其他插件组合。

## 7. Host Plane、Agent Plane 与 Client Plane

DSH 不是只有一棵平坦的插件树，而是存在三个重要组合空间。

### Host Plane：整个进程共享的基础设施

Host Plane 放置跨 Session 共享或被入口层读取的 Service，例如 Session Store、Persistence、LLM Registry、Tool Registry、Sandbox、Approval、Settings、Credentials、Subagent Registry 和 API Gateway。

### Agent Plane：一个 Agent 看见的能力组合

Web 模式通过 Agent Preset 决定每个 Agent 的 Persona、工具、Prompt Section、Compaction、Workflow 等能力。标准 Preset 的组件只挂载一次，多个 Agent 通过 scope parent chain 加入它：

```text
Agent 自己的 Scope
        ↓
所选 Preset 的 Scope
        ↓
Host 的全局 Scope
```

读取时越近的注册优先，所以 Agent 可以遮蔽 Preset，Preset 又可以遮蔽全局注册。不同 Session 的可变状态仍由 Session 或 Agent 作为 key 隔离。

Preset 并不会在运行中的任意时刻随意切换。DSH 只允许尚未产生内容的 Agent 更换 Preset；一旦 Session 已记录模型请求或工具调用，换一套工具与 Prompt 会让历史中的语义和当前能力不一致。已经加入某个 Preset 的 Agent 也会继续使用当时的 generation，文件修改只影响之后创建的 Agent。

### Client Plane：浏览器里另一套 Cordis 运行时

Web UI 也由插件组成，但它运行在浏览器自己的 Cordis Context 中。Host 负责 API 与模块清单，Client 插件通过 Slot Registry 向侧边栏、会话区、输入框和 Tool Card 等位置注册 UI。Host Service 不会因为名字相同就自动出现在 Client；它们必须通过 Typert/API Gateway 明确投影到另一侧。

这说明 “Everything is a plugin” 并不等于“所有插件都在同一个全局容器里”。Service 的可见性同时受进程、realm、Agent scope 和 Host/Client 边界限制。

## 8. “Everything is a plugin” 的真正边界

DSH 的插件化程度很高：模型适配器、Agent Loop、Session Store、工具、持久化、Sandbox 策略、API 和 UI 都能在组合中出现。但它并不意味着任何东西都可以无条件热替换。

### Cordis 自身不是插件

Context、Fiber、Effect 记录、Service 解析、Loader 以及承载它们的 JavaScript 进程是更底层的运行时。DSH 的“所有东西”指产品能力，而不是这套运行时本身。

### 接口和持久化语义不能被随意破坏

组件实现可以替换，但 `Agent`、`SessionEvent`、Tool、LLM Stream 等接口是组件合作的共同语言。替换 Agent Loop 仍要满足 Agent Service 的创建、取消、所有权与日志约束；替换 Persistence 仍要维护 append-only、序号连续和 Crash Repair 语义。

### 只有被登记的 Effect 才能自动撤销

`ctx.effect()`、`ctx.on()` 以及返回 disposer 的注册方法能随 Fiber 卸载。组件如果绕开这些机制修改全局变量、启动未登记的后台任务或改变外部系统，Cordis 无法自动恢复。数据库写入、已发送的邮件或支付请求更不在 Context 的回滚范围内。

### 插件化不是安全隔离

一个 Preset 本质上是可执行组合，权限接近 Shell。DSH 的 Cordis 创造模式允许 Agent 检查运行时并临时 `define/run/stop` 动态组件，但这些组件只存在于进程内存，默认不能自动持久化，而且 VM 只是诚实代码的隔离层，不是安全边界。

### 运行时能力不等于默认全部开启

Cordis 支持配置协调和 HMR，但当前 Web 与 Headless Bundle 默认关闭通用 HMR。DSH 更谨慎的路径是：新 Session 使用更新后的 Preset generation，或者在明确授权的 Cordis 模式中运行临时组件。这避免了“理论上可热替换”被误解为“任何生产中的 Agent 都会随文件变化立即重组”。

### 有些行为仍属于默认 Loop 的算法

插件可以通过 Service 和 Event 改变大量行为，但 Turn/Step 状态机、日志边界和工具调度仍由默认 `agent-loop` 实现。如果要改变这些根本语义，应替换整个 Loop，并继续遵守外部契约，而不是在内部随意打补丁。

所以更准确的说法是：

> DSH 尽可能把产品能力设计成有明确契约和生命周期的插件，但插件仍运行在 Cordis、进程、持久化格式、信任模型与跨端协议所划定的边界内。

## 9. 最后把整套架构串起来

从启动到一次模型请求，DSH 的完整路径可以压缩为：

```text
Profile + Bundles + Patches
        ↓
Loader 建立 Host Component / Fiber Tree
        ↓
Service 依赖决定组件何时激活
        ↓
入口通过 ctx.agents 创建 Agent 与 Session
        ↓
Agent Scope 加入所选 Preset，得到自己的工具和 Prompt 视图
        ↓
Agent Loop 从 Inbox 开启 Turn / Step
        ↓
Session + SystemPrompt + LLM + Tools 协作完成请求
        ↓
所有模型可见事实写回 Session Log
        ↓
UI / SDK / Persistence / Telemetry 从 Event 与投影读取同一份事实
```

Cordis 负责的是竖向的生命周期：组件何时存在、依赖何时满足、退出时如何清理。DSH 负责的是横向的产品语义：什么是 Agent、一次 Turn 如何运行、哪些事实必须持久化、工具和模型如何接入、不同 Session 能看到哪些能力。

这两层结合后，“Everything is a plugin” 才不只是代码目录很多，而是一条真正可执行的架构原则：默认产品本身就是一份组合，扩展与替换使用的机制和系统启动自身使用的是同一套机制。
