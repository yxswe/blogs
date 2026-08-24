---
title: DeepSeek Harness 学习笔记
description: 深入理解 DeepSeek Harness 的架构、插件能力、请求流程，以及 Cordis 框架的设计方式。
lang: zh
translationKey: deepseek-harness
date: 2026-08-24
tags:
  - Agent Harness
  - DeepSeek
featured: true
---

# DeepSeek Harness 学习笔记

> 本文整理对 DeepSeek Harness（DSH）的架构、插件能力、请求流程和 Cordis 框架的研究结果。内容基于 2026 年 8 月的项目源码。

## 1. DSH 是什么

DeepSeek Harness 是一个基于 Cordis 的插件化 Agent Harness。它最核心的设计是：**所有组成部分都是插件**，包括模型适配器、Session、工具注册表、Agent Loop、文件系统、Shell、权限策略和 Web UI。

因此，扩展 DSH 的首选方式通常不是修改 Agent Loop，而是：

1. 找到已有的 Service 或事件扩展点；
2. 编写一个 Cordis 插件；
3. 通过 profile、bundle、preset 或 patch 把插件加入组合；
4. 让 Cordis 管理插件的依赖和生命周期。

整体结构可以简化为：

```text
浏览器插件
    │ HTTP / SSE
    ▼
API Gateway / ApiProxy
    │
    ▼
Cordis Host 进程
├─ Session 事件日志
├─ Agent + Agent Loop
├─ 每会话 Agent Preset
├─ Tools / Skills / Sandbox
└─ LLM / FS / Shell / Web Provider
    │
    ▼
DeepSeek 等外部 API
```

## 2. Profile、Bundle 与 Agent Preset

DSH 的运行组合分成两个层次：

```text
Profile：决定整个进程加载哪些基础设施和应用界面
└─ Agent Preset：决定某个 Agent 能看到哪些提示词、工具和作用域服务
```

默认 Web profile 由两个 bundle 组成：

```text
@deepseek-ai/dsh-base
@deepseek-ai/dsh-web-app
```

其中：

- `dsh-base` 提供 LLM、Session、Agent、Tools、Sandbox、文件系统、Shell、Skills、Goal、Subagent、Workflow 等基础能力；
- `dsh-web-app` 增加 HTTP Server、API、浏览器运行时、会话 UI、Trajectory UI、设置页和 Agent preset 系统。

Web 默认 Agent preset 是 `standard`。项目随附四种 preset：

| Preset | 用途 |
| --- | --- |
| `standard` | 完整编码 Agent |
| `code` | 与 standard 相同的底层能力，但通过 `run_code` 和 TypeScript SDK 呈现工具 |
| `minimal` | 只有持久 Bash 和 `str_replace_editor` |
| `cordis` | standard 加运行时 Cordis 检查、临时插件实验和 preset 创作能力 |

Profile 的配置层按以下顺序合成，后面的层优先级更高：

```text
各 bundle 的 cordis.patch.yml
→ profile 自己的 cordis.patch.yml
→ $DSH_HOME/cordis.patch.yml
→ 命令行 --patch
```

可以通过下面的命令查看机器最终会启动的插件树：

```bash
dsh --profile web --dump-config
```

## 3. 默认工具与能力

在 macOS/Linux 的 `standard` preset 下，模型默认可以使用：

| 能力 | 工具 |
| --- | --- |
| Shell | `bash`，Windows 下为 `pwsh` |
| 文件 | `read`、`write`、`edit`、`read_image` |
| 搜索文件 | `glob`、`grep` |
| 后台任务 | `job_list`、`job_output`、`job_kill` |
| Skills | `skill` |
| Goal | `create_goal`、`get_goal`、`update_goal` |
| Plan | `exit_plan_mode` |
| 子代理 | `subagent`、`subagent_fork` |
| 子代理控制 | `list_agents`、`send_message`、`interrupt_agent` |
| 编排 | `workflow`、`ralph` |
| 人机交互 | `ask_user_question` |
| Todo | `todo_write` |
| 网络 | `web_search` |

“插件已经安装”和“工具暴露给当前模型”不是一回事。工具是否可见还取决于当前 profile、preset、作用域和配置。

默认没有启用的能力包括：

- `web_fetch`；
- LSP 工具；
- Terminal 工具组；
- Schedule 定时任务；
- Session 全文检索工具；
- Codex、Claude Code 外部子代理；
- 非 `cordis` preset 下的动态 Cordis 自修改工具；
- Telemetry，默认模式为 `DISABLED`。

### 网络搜索 Provider

仓库实现了三种搜索 Provider：

| Provider ID | API | 默认启用 |
| --- | --- | --- |
| `deepseek-official` | DeepSeek Anthropic-compatible Messages API，启用 `web_search_20250305` | 是 |
| `exa` | Exa `POST /search` | 否 |
| `perplexity` | Perplexity OpenAI-compatible `POST /chat/completions`，默认使用 `sonar` | 否 |

DeepSeek 搜索不是普通聊天请求，也不是独立搜索 endpoint。每次搜索会额外发起一次完整的 Messages 模型请求，由服务端搜索工具返回结构化结果，所以会产生额外延迟和 Token 消耗。

默认凭据和地址为：

```text
凭据：DEEPSEEK_API_KEY
搜索地址：https://api.deepseek.com/anthropic/v1/messages
地址覆盖：DEEPSEEK_SEARCH_BASE_URL
```

## 4. 编译、初次运行和一次请求

### 4.1 编译过程

根构建命令：

```bash
pnpm install
pnpm run build
```

实际顺序为：

```text
Host TypeScript 编译
→ Host 打包及 Typert API 生成
→ Client TypeScript 编译
→ Client 插件打包
→ Web 前端构建
```

对应主要命令：

```bash
tsc -b tsconfig.host.json
tsdown --env.DSH_BUILD_FACE host
tsc -b tsconfig.client.json
tsdown --env.DSH_BUILD_FACE client
pnpm --filter @deepseek-ai/dsh-web-frontend run build
```

Host 包含 Node.js 侧的 Cordis、Agent、Session、LLM、Shell、Sandbox 和 API。Client 包含浏览器中的对话、Tool 卡片、Goal、Plan、Subagent、Trajectory 和设置插件。

Typert 在 Host 构建阶段扫描 `@Remote` 和 `@RemoteScope`，生成 Host 调用描述、参数校验、Client 类型和 RPC 调用代码。

### 4.2 初次运行

执行：

```bash
pnpm dsh --profile web
```

第一次启动大致经历：

1. CLI 解析 profile 和应用参数；
2. 自动初始化 `$DSH_HOME/profiles/web`；
3. 读取 profile 中声明的 bundle；
4. 合成所有 patch 层；
5. 创建 Cordis 根 Context；
6. Loader 导入并挂载插件树；
7. 根据服务依赖激活插件；
8. 启动 Web Server、API 和浏览器插件；
9. 用户创建会话时，才创建 Session、Agent 并挂载对应 preset。

配置里的行顺序不是可靠的插件启动顺序。插件通过 `inject` 声明依赖，Cordis 会等服务可用后再激活。

### 4.3 每次发送请求

需要区分：

- Turn：用户发起的一轮工作；
- Step：一次模型请求加上它产生的工具调用；
- 一个 Turn 可以有多个 Step。

典型过程：

```text
浏览器提交消息
→ API 校验 Session、Agent、附件和请求模式
→ 消息进入 Agent inbox
→ turn/start
→ agent/pre-step
→ step/start + user/message
→ 从 Session 日志派生模型历史
→ 组装 System Prompt 和工具 Schema
→ agent/request
→ ctx.llm 调用具体模型 Provider
→ assistant/chunk* + assistant/message
→ 若有工具调用，进入工具执行管线
→ tool/result 写入 Session
→ 如仍需模型决策，继续下一个 Step
→ step/end
→ turn/end
```

工具执行管线是：

```text
tool/call
→ tools/pre-execute
→ 权限、审批、Sandbox、Guard
→ tools/execute
→ 具体工具 execute()
→ tools/post-execute
→ 结果裁剪或超长结果落盘
→ tool/result
```

Session 事件日志是系统的权威状态。模型历史、恢复、Fork、Trajectory、Telemetry 和持久化都从这份事件流派生。

## 5. Trajectory、Eval 与自进化

### Trajectory

Trajectory 是 Agent 执行轨迹：用户输入、模型输出、工具调用、工具结果、步骤和状态变化组成的事件序列。DSH 的 Trajectory UI 本质上是 Session 日志的可视化投影。

### Eval

当前默认运行时没有独立 evaluator。Goal 和 Ralph 的完成主要由 Agent 或 worker 自己声明。Snapshot、E2E 和真实 API 测试属于开发验证体系，不等同于运行时独立评测器。

### 自进化

`cordis` preset 支持 Agent 检查当前插件树，并临时定义、运行和停止模型编写的插件。但这种动态插件在进程重启后消失。要把实验变成稳定能力，仍应写成正式插件或 preset，放进独立项目并通过 profile 安装。

## 6. Cordis 的核心模型

Cordis 可以理解为一个支持动态装配、依赖注入、作用域隔离、事件中间件和自动资源回收的 TypeScript 插件运行时。

```text
Plugin：可安装的功能定义
Fiber：Plugin 某一次安装产生的运行实例
Context：这个实例看到的服务、作用域和生命周期入口
Service：插件向其他插件提供的具名能力
Effect：与 Fiber 生命周期绑定的资源
Event：插件之间的通知或中间件
Loader：把配置文件转换为 ctx.plugin() 调用
```

关系如下：

```text
Context
├─ 解析 Service
├─ 分发 Event
└─ 挂载 Plugin
   └─ 创建 Fiber
      ├─ 拥有自己的子 Context
      ├─ 记录 Effects
      ├─ 记录子插件
      └─ 负责卸载和清理
```

## 7. `ctx` 包含什么

`ctx` 是一个 Proxy，不是普通配置对象。它同时承担：

1. Cordis 框架 API 入口；
2. 当前 Fiber 的生命周期上下文；
3. 当前作用域的服务解析器；
4. 插件间事件总线入口。

主要内容：

```text
ctx
├─ 固定状态
│  ├─ root
│  ├─ baseUrl
│  ├─ fiber
│  ├─ registry
│  ├─ reflect
│  ├─ events
│  └─ logger
├─ 生命周期方法
│  ├─ plugin()
│  ├─ inject()
│  └─ effect()
├─ 服务方法
│  ├─ get()
│  ├─ provide()
│  ├─ set()
│  ├─ accessor()
│  └─ mixin()
├─ 事件方法
│  ├─ on()
│  ├─ once()
│  ├─ emit()
│  ├─ parallel()
│  ├─ serial()
│  ├─ bail()
│  └─ waterfall()
├─ 作用域方法
│  ├─ extend()
│  ├─ isolate()
│  └─ intercept()
└─ 动态服务
   ├─ ctx.tools
   ├─ ctx.llm
   ├─ ctx.sessions
   ├─ ctx.shell
   └─ 其他插件注册的服务
```

核心快捷方法实际转发给内部服务：

```text
ctx.plugin    → ctx.registry.plugin
ctx.inject    → ctx.registry.inject
ctx.effect    → ctx.fiber.effect
ctx.get       → ctx.reflect.get
ctx.provide   → ctx.reflect.provide
ctx.on        → ctx.events.on
ctx.emit      → ctx.events.emit
```

### `ctx.fiber`

每次 `ctx.plugin()` 都创建一个 Fiber。常见状态：

```text
PENDING → LOADING → ACTIVE → UNLOADING → DISPOSED
                 ↘ FAILED
```

- `PENDING`：声明的服务依赖尚未满足；
- `LOADING`：正在校验配置和执行插件入口；
- `ACTIVE`：插件已经激活；
- `FAILED`：配置或启动失败；
- `UNLOADING`：正在执行清理；
- `DISPOSED`：完全卸载。

### `ctx.get()` 与直接读取

直接读取表示插件认为服务应该存在：

```ts
ctx.clock.now()
```

可选依赖使用：

```ts
const clock = ctx.get('clock')
clock?.now()
```

### `extend()`、`isolate()` 与 `intercept()`

三者都创建子 Context，不修改父 Context：

```text
extend     → 附加普通上下文元数据
isolate    → 为某个服务切换到独立解析空间
intercept  → 为某个服务附加作用域配置
```

## 8. Cordis 如何识别插件

Cordis 支持三种插件形式。

### 函数插件

```ts
function plugin(ctx: Context, config: Config) {
  // 安装功能
}

ctx.plugin(plugin, config)
```

Registry 发现参数是函数，直接将它作为入口。

### 对象插件

```ts
const plugin = {
  name: 'demo',
  inject: ['clock'],
  apply(ctx: Context, config: Config) {
    // 安装功能
  },
}
```

Registry 发现对象包含 `apply()`，使用 `plugin.apply` 作为入口。

### Class 插件

```ts
class ClockService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'clock')
  }
}
```

Class 在 JavaScript 中也是函数，但 Fiber 会识别它是构造函数并执行：

```ts
new ClockService(pluginCtx, config)
```

模块通过 Loader 加载时：

```yaml
- id: heartbeat
  name: './heartbeat.ts'
  config:
    interval: 1000
```

Loader 大致执行：

```ts
const moduleObject = await import('./heartbeat.ts')
const fiber = ctx.plugin(moduleObject, yamlConfig)
await fiber
```

模块的命名导出会组成对象：

```ts
{
  name: 'heartbeat',
  inject: ['logger'],
  Config: schema,
  apply: function apply() {},
}
```

所以 Loader 能把模块对象交给对象插件识别逻辑。

## 9. Plugin 从声明到调用的例子

### 9.1 函数插件与 Effect

```ts
import type { Context } from '@deepseek-ai/cordis'

function heartbeat(ctx: Context) {
  ctx.effect(() => {
    const timer = setInterval(() => {
      ctx.logger.info('tick')
    }, 1000)

    return () => clearInterval(timer)
  })
}

export function apply(ctx: Context) {
  const fiber = ctx.plugin(heartbeat)
  void fiber
}
```

流程：

```text
Loader 挂载模块
→ 创建外层模块 Fiber
→ 调用 apply(ctx)
→ apply 调用 ctx.plugin(heartbeat)
→ 创建 heartbeat 子 Fiber
→ Cordis 直接调用 heartbeat(childCtx)
→ 注册 interval effect
```

这里 Loader 不会扫描或发现局部函数 `heartbeat`。是外层 `apply()` 主动将它挂载成子插件。

`ctx.effect()` 立即执行 setup，并保存它返回的 disposer：

```text
插件激活 → setInterval
插件卸载 → clearInterval
```

父插件卸载时，子 Fiber 也会递归卸载。

### 9.2 Service Provider 与 Consumer

Provider：

```ts
import { Service, type Context } from '@deepseek-ai/cordis'

declare module '@deepseek-ai/cordis' {
  interface Context {
    clock: ClockService
  }
}

export class ClockService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'clock')
  }

  now() {
    return Date.now()
  }
}

export function apply(ctx: Context) {
  ctx.plugin(ClockService)
}
```

Consumer：

```ts
import type { Context } from '@deepseek-ai/cordis'
import type {} from './clock-provider.ts'

export const inject = ['clock']

export function apply(ctx: Context) {
  ctx.logger.info('time: %d', ctx.clock.now())
}
```

YAML 即使把 Consumer 写在前面也能正确工作：

```yaml
- id: consumer
  name: './clock-consumer.ts'
- id: provider
  name: './clock-provider.ts'
```

实际流程：

```text
Consumer Fiber 创建
→ inject 要求 clock
→ clock 不存在
→ Consumer 保持 PENDING

Provider Fiber 创建
→ provider.apply()
→ ctx.plugin(ClockService)
→ new ClockService()
→ super(ctx, 'clock') 注册服务
→ Cordis 通知依赖 clock 的 Fiber
→ Consumer 进入 LOADING
→ consumer.apply()
→ ctx.clock 解析到 ClockService
→ 调用 now()
```

`declare module` 只提供 TypeScript 类型；真正的运行时服务注册来自 `super(ctx, 'clock')`。

Provider 卸载时：

```text
clock 服务注销
→ Consumer 依赖不再满足
→ Consumer 自动卸载并清理自己的 effects
→ Consumer 回到 PENDING
```

Provider 恢复后，Consumer 会重新加载。

### 9.3 Event 中间件

```ts
declare module '@deepseek-ai/cordis' {
  interface Events {
    'text/format'(
      text: string,
      next: () => Promise<string>,
    ): Promise<string>
  }
}

export function apply(ctx: Context) {
  ctx.on('text/format', async (text, next) => {
    const result = await next()
    return result.toUpperCase()
  })
}
```

调用：

```ts
const result = await ctx.waterfall(
  'text/format',
  'hello',
  async () => 'hello',
)
```

结果为 `HELLO`。如果监听器不调用 `next()`，它会短路剩余监听器和默认实现。

`ctx.on()` 本身是 effect，插件卸载时监听器自动移除。

### 9.4 DSH Tool 插件

```ts
import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'

export const inject = ['tools']

export function apply(ctx: Context) {
  ctx.tools.register(defineTool({
    name: 'hello',
    description: 'Return a greeting.',
    parameters: {
      name: { type: 'string', required: true },
    },
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [
        { type: 'text', text: value },
      ],
    },
    async execute(args) {
      return `Hello, ${args.name}!`
    },
  }))
}
```

流程：

```text
插件 Fiber 创建
→ 等待 tools 服务
→ 调用 apply()
→ hello 注册进 ctx.tools
→ System Prompt 组装时暴露 hello Schema
→ 模型产生 hello 调用
→ Agent Loop 调用 ctx.tools.execute()
→ 工具管线调用 hello.execute()
→ 结果写入 tool/result
```

这里要区分：

```text
apply()         插件激活时执行，用来注册工具
hello.execute() 每次模型调用工具时执行
```

插件卸载后，`hello` 会从工具注册表撤销，后续模型请求不再看到它。

## 10. Service、Event 与 Effect 如何选择

| 需求 | 使用方式 |
| --- | --- |
| 调用一个明确能力并获得返回值 | Service 方法 |
| 广播某件事已经发生 | Event `emit` |
| 多个异步观察者并发处理 | Event `parallel` |
| 按顺序寻找一个处理结果 | Event `serial` / `bail` |
| 包装、转换或短路默认行为 | Event `waterfall` |
| 管理定时器、连接、watcher | `ctx.effect()` |
| 安装一个子功能 | `ctx.plugin()` |
| 声明必须存在的能力 | `inject` |
| 使用可能不存在的能力 | `ctx.get()` |

## 11. 常见混淆

```text
Plugin ≠ Fiber
Plugin 是定义，Fiber 是一次运行实例。

Context ≠ 全局对象
每个 Fiber 都有自己的子 Context。

apply ≠ 每次请求执行
apply 负责安装贡献，真正业务调用通常进入服务方法或 execute()。

inject ≠ import
inject 是运行时服务依赖，import 是代码模块依赖。

declare module ≠ 注册服务
它只提供 TypeScript 类型。

ctx.effect ≠ 定时器 API
它将外部资源和清理函数绑定到 Fiber 生命周期。

Cordis Event ≠ DSH SessionEvent
Cordis Event 是进程内通信；SessionEvent 是可持久化、回放的 Agent 事实。
```

## 12. 二次开发建议

多数 DSH 二次开发可以从独立插件项目开始，而不需要 fork 全部 DSH 源码：

1. 建立自己的 Git 仓库和 npm package；
2. 将 `@deepseek-ai/cordis` 以及所需 DSH Service Definition 包设为依赖或 peer dependency；
3. 编写 Cordis 插件；
4. 让插件的 `register()` 返回 disposer，所有资源进入 effect；
5. 创建 bundle 或 profile patch；
6. 使用 `dsh plugin --profile <name> add <package>` 安装；
7. 用 `dsh --profile <name> --dump-config` 检查最终组合。

需要修改 DSH 核心的情况通常包括：

- 现有扩展点无法表达需求；
- 需要修改 Session 持久格式或 Agent Loop 基本语义；
- 需要改变跨 package 的公共 Service Definition；
- 需要修改构建、发布或 Host/Client RPC 生成机制。

其余情况下，插件、provider、consumer、preset 或 bundle 通常已经足够。
