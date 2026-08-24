---
title: DeepSeek Harness Study Notes
description: A detailed look at DeepSeek Harness architecture, plugin capabilities, request flow, and the design of the Cordis framework.
lang: en
translationKey: deepseek-harness
date: 2026-08-24
tags:
  - Agent Harness
  - DeepSeek
featured: true
---

# DeepSeek Harness Study Notes

> This article summarizes research into the architecture, plugin capabilities, request flow, and Cordis framework behind DeepSeek Harness (DSH). It is based on the project source code as of August 2026.

## 1. What Is DSH?

DeepSeek Harness is a plugin-based agent harness built on Cordis. Its central design principle is that **every component is a plugin**, including model adapters, sessions, the tool registry, the agent loop, file systems, shells, permission policies, and the web UI.

As a result, the preferred way to extend DSH is usually not to modify the agent loop. Instead:

1. Find an existing service or event extension point.
2. Write a Cordis plugin.
3. Add the plugin to the composition through a profile, bundle, preset, or patch.
4. Let Cordis manage the plugin's dependencies and lifecycle.

The overall architecture can be simplified as follows:

```text
Browser plugin
    │ HTTP / SSE
    ▼
API Gateway / ApiProxy
    │
    ▼
Cordis host process
├─ Session event log
├─ Agent + Agent Loop
├─ Per-session Agent Preset
├─ Tools / Skills / Sandbox
└─ LLM / FS / Shell / Web Provider
    │
    ▼
External APIs such as DeepSeek
```

## 2. Profiles, Bundles, and Agent Presets

DSH composes its runtime at two levels:

```text
Profile: determines which infrastructure and application interfaces the process loads
└─ Agent Preset: determines which prompts, tools, and scoped services an agent can see
```

The default web profile consists of two bundles:

```text
@deepseek-ai/dsh-base
@deepseek-ai/dsh-web-app
```

Their responsibilities are:

- `dsh-base` provides the foundational LLM, Session, Agent, Tools, Sandbox, file system, Shell, Skills, Goal, Subagent, and Workflow capabilities.
- `dsh-web-app` adds the HTTP server, API, browser runtime, session UI, Trajectory UI, settings pages, and the agent preset system.

The default agent preset for the web profile is `standard`. The project includes four presets:

| Preset | Purpose |
| --- | --- |
| `standard` | Full coding agent |
| `code` | The same underlying capabilities as standard, with tools exposed through `run_code` and a TypeScript SDK |
| `minimal` | Only persistent Bash and `str_replace_editor` |
| `cordis` | Standard plus runtime Cordis inspection, temporary plugin experiments, and preset authoring capabilities |

Profile configuration layers are merged in the following order, with later layers taking precedence:

```text
cordis.patch.yml from each bundle
→ the profile's own cordis.patch.yml
→ $DSH_HOME/cordis.patch.yml
→ command-line --patch
```

The following command shows the final plugin tree that will start on the current machine:

```bash
dsh --profile web --dump-config
```

## 3. Default Tools and Capabilities

Under the `standard` preset on macOS or Linux, the model can use the following tools by default:

| Capability | Tools |
| --- | --- |
| Shell | `bash`; `pwsh` on Windows |
| Files | `read`, `write`, `edit`, `read_image` |
| File search | `glob`, `grep` |
| Background jobs | `job_list`, `job_output`, `job_kill` |
| Skills | `skill` |
| Goal | `create_goal`, `get_goal`, `update_goal` |
| Plan | `exit_plan_mode` |
| Subagents | `subagent`, `subagent_fork` |
| Subagent control | `list_agents`, `send_message`, `interrupt_agent` |
| Orchestration | `workflow`, `ralph` |
| Human interaction | `ask_user_question` |
| Todo | `todo_write` |
| Network | `web_search` |

A plugin being installed is not the same as its tools being exposed to the current model. Tool visibility also depends on the active profile, preset, scope, and configuration.

Capabilities that are not enabled by default include:

- `web_fetch`;
- LSP tools;
- the Terminal tool group;
- scheduled tasks;
- full-text Session search tools;
- external Codex and Claude Code subagents;
- dynamic Cordis self-modification outside the `cordis` preset;
- Telemetry, whose default mode is `DISABLED`.

### Web Search Providers

The repository implements three search providers:

| Provider ID | API | Enabled by default |
| --- | --- | --- |
| `deepseek-official` | DeepSeek's Anthropic-compatible Messages API with `web_search_20250305` enabled | Yes |
| `exa` | Exa `POST /search` | No |
| `perplexity` | Perplexity's OpenAI-compatible `POST /chat/completions`, using `sonar` by default | No |

DeepSeek search is neither a normal chat request nor a separate search endpoint. Each search initiates an additional full Messages model request, and the server-side search tool returns structured results. It therefore adds both latency and token usage.

The default credential and endpoint are:

```text
Credential: DEEPSEEK_API_KEY
Search endpoint: https://api.deepseek.com/anthropic/v1/messages
Endpoint override: DEEPSEEK_SEARCH_BASE_URL
```

## 4. Building, First Run, and a Single Request

### 4.1 Build Process

The root build commands are:

```bash
pnpm install
pnpm run build
```

The actual sequence is:

```text
Host TypeScript compilation
→ Host bundling and Typert API generation
→ Client TypeScript compilation
→ Client plugin bundling
→ Web frontend build
```

The primary commands involved are:

```bash
tsc -b tsconfig.host.json
tsdown --env.DSH_BUILD_FACE host
tsc -b tsconfig.client.json
tsdown --env.DSH_BUILD_FACE client
pnpm --filter @deepseek-ai/dsh-web-frontend run build
```

The Host contains the Node.js-side Cordis, Agent, Session, LLM, Shell, Sandbox, and API components. The Client contains browser plugins for conversations, Tool cards, Goal, Plan, Subagent, Trajectory, and settings.

During the Host build, Typert scans `@Remote` and `@RemoteScope` to generate Host call descriptions, parameter validation, Client types, and RPC call code.

### 4.2 First Run

Run:

```bash
pnpm dsh --profile web
```

The first startup roughly follows these steps:

1. The CLI parses the profile and application arguments.
2. It automatically initializes `$DSH_HOME/profiles/web`.
3. It reads the bundles declared by the profile.
4. It merges all patch layers.
5. It creates the root Cordis Context.
6. The Loader imports and mounts the plugin tree.
7. Plugins activate when their service dependencies are satisfied.
8. The web server, API, and browser plugins start.
9. A Session and Agent are created, and the selected preset is mounted, only when the user creates a session.

Line order in the configuration is not a reliable indication of plugin startup order. Plugins declare dependencies with `inject`, and Cordis waits for those services to become available before activating them.

### 4.3 Each Request

It is important to distinguish between:

- Turn: one unit of work initiated by the user.
- Step: one model request together with the tool calls it produces.
- A single Turn can contain multiple Steps.

A typical request proceeds as follows:

```text
Browser submits a message
→ API validates the Session, Agent, attachments, and request mode
→ Message enters the Agent inbox
→ turn/start
→ agent/pre-step
→ step/start + user/message
→ Model history is derived from the Session log
→ System Prompt and tool schemas are assembled
→ agent/request
→ ctx.llm calls the selected model Provider
→ assistant/chunk* + assistant/message
→ If tools are requested, enter the tool execution pipeline
→ tool/result is written to the Session
→ If another model decision is required, continue with the next Step
→ step/end
→ turn/end
```

The tool execution pipeline is:

```text
tool/call
→ tools/pre-execute
→ Permission, approval, Sandbox, and Guard checks
→ tools/execute
→ The concrete tool's execute()
→ tools/post-execute
→ Result truncation or spill-to-disk for oversized output
→ tool/result
```

The Session event log is the system's authoritative state. Model history, recovery, forks, Trajectory, Telemetry, and persistence are all derived from this event stream.

## 5. Trajectory, Evaluation, and Self-Evolution

### Trajectory

A Trajectory is the agent's execution trace: the sequence of user input, model output, tool calls, tool results, steps, and state changes. DSH's Trajectory UI is essentially a visual projection of the Session log.

### Evaluation

The default runtime currently has no independent evaluator. Goal and Ralph completion is primarily declared by the agent or worker itself. Snapshot tests, end-to-end tests, and tests against real APIs belong to the development verification system; they are not equivalent to an independent runtime evaluator.

### Self-Evolution

The `cordis` preset allows an agent to inspect the current plugin tree and temporarily define, run, and stop model-authored plugins. These dynamic plugins disappear after the process restarts. To turn an experiment into a stable capability, it must still be implemented as a formal plugin or preset, placed in an independent project, and installed through a profile.

## 6. Cordis's Core Model

Cordis can be understood as a TypeScript plugin runtime that supports dynamic composition, dependency injection, scope isolation, event middleware, and automatic resource cleanup.

```text
Plugin: an installable feature definition
Fiber: a runtime instance created by one installation of a Plugin
Context: the services, scope, and lifecycle entry point visible to that instance
Service: a named capability provided by one plugin to others
Effect: a resource bound to a Fiber's lifecycle
Event: a notification or middleware mechanism between plugins
Loader: converts configuration files into ctx.plugin() calls
```

Their relationships are:

```text
Context
├─ Resolves Services
├─ Dispatches Events
└─ Mounts Plugins
   └─ Creates a Fiber
      ├─ Owns a child Context
      ├─ Records Effects
      ├─ Records child plugins
      └─ Handles unloading and cleanup
```

## 7. What Does `ctx` Contain?

`ctx` is a Proxy, not a plain configuration object. It serves four roles at once:

1. Entry point to the Cordis framework API.
2. Lifecycle context for the current Fiber.
3. Service resolver for the current scope.
4. Event bus entry point for communication between plugins.

Its main contents are:

```text
ctx
├─ Fixed state
│  ├─ root
│  ├─ baseUrl
│  ├─ fiber
│  ├─ registry
│  ├─ reflect
│  ├─ events
│  └─ logger
├─ Lifecycle methods
│  ├─ plugin()
│  ├─ inject()
│  └─ effect()
├─ Service methods
│  ├─ get()
│  ├─ provide()
│  ├─ set()
│  ├─ accessor()
│  └─ mixin()
├─ Event methods
│  ├─ on()
│  ├─ once()
│  ├─ emit()
│  ├─ parallel()
│  ├─ serial()
│  ├─ bail()
│  └─ waterfall()
├─ Scope methods
│  ├─ extend()
│  ├─ isolate()
│  └─ intercept()
└─ Dynamic services
   ├─ ctx.tools
   ├─ ctx.llm
   ├─ ctx.sessions
   ├─ ctx.shell
   └─ Services registered by other plugins
```

The main convenience methods delegate to internal services:

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

Every call to `ctx.plugin()` creates a Fiber. Common states are:

```text
PENDING → LOADING → ACTIVE → UNLOADING → DISPOSED
                 ↘ FAILED
```

- `PENDING`: declared service dependencies have not yet been satisfied.
- `LOADING`: configuration is being validated and the plugin entry point is running.
- `ACTIVE`: the plugin has activated.
- `FAILED`: configuration or startup failed.
- `UNLOADING`: cleanup is in progress.
- `DISPOSED`: the plugin has been completely unloaded.

### `ctx.get()` Versus Direct Access

Direct access means the plugin expects the service to exist:

```ts
ctx.clock.now()
```

Use `ctx.get()` for optional dependencies:

```ts
const clock = ctx.get('clock')
clock?.now()
```

### `extend()`, `isolate()`, and `intercept()`

All three create a child Context without modifying the parent Context:

```text
extend     → attaches ordinary context metadata
isolate    → switches a service into an independent resolution space
intercept  → attaches scoped configuration to a service
```

## 8. How Cordis Recognizes Plugins

Cordis supports three plugin forms.

### Function Plugins

```ts
function plugin(ctx: Context, config: Config) {
  // Install functionality
}

ctx.plugin(plugin, config)
```

The Registry sees that the argument is a function and uses it directly as the entry point.

### Object Plugins

```ts
const plugin = {
  name: 'demo',
  inject: ['clock'],
  apply(ctx: Context, config: Config) {
    // Install functionality
  },
}
```

The Registry sees an object with an `apply()` method and uses `plugin.apply` as the entry point.

### Class Plugins

```ts
class ClockService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'clock')
  }
}
```

A class is also a function in JavaScript, but Fiber recognizes it as a constructor and executes:

```ts
new ClockService(pluginCtx, config)
```

When the Loader loads a module:

```yaml
- id: heartbeat
  name: './heartbeat.ts'
  config:
    interval: 1000
```

It roughly performs:

```ts
const moduleObject = await import('./heartbeat.ts')
const fiber = ctx.plugin(moduleObject, yamlConfig)
await fiber
```

The module's named exports form an object:

```ts
{
  name: 'heartbeat',
  inject: ['logger'],
  Config: schema,
  apply: function apply() {},
}
```

This is why the Loader can pass the module object to the object-plugin recognition path.

## 9. Examples: From Plugin Declaration to Invocation

### 9.1 Function Plugin and Effect

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

The flow is:

```text
Loader mounts the module
→ Creates the outer module Fiber
→ Calls apply(ctx)
→ apply calls ctx.plugin(heartbeat)
→ Creates a child heartbeat Fiber
→ Cordis directly calls heartbeat(childCtx)
→ Registers the interval effect
```

The Loader does not scan for or discover the local `heartbeat` function. The outer `apply()` explicitly mounts it as a child plugin.

`ctx.effect()` immediately runs its setup function and stores the disposer it returns:

```text
Plugin activation → setInterval
Plugin unload → clearInterval
```

When the parent plugin unloads, child Fibers unload recursively as well.

### 9.2 Service Provider and Consumer

Provider:

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

Consumer:

```ts
import type { Context } from '@deepseek-ai/cordis'
import type {} from './clock-provider.ts'

export const inject = ['clock']

export function apply(ctx: Context) {
  ctx.logger.info('time: %d', ctx.clock.now())
}
```

The YAML works correctly even if the Consumer appears before the Provider:

```yaml
- id: consumer
  name: './clock-consumer.ts'
- id: provider
  name: './clock-provider.ts'
```

The actual flow is:

```text
Consumer Fiber is created
→ inject requires clock
→ clock does not exist
→ Consumer remains PENDING

Provider Fiber is created
→ provider.apply()
→ ctx.plugin(ClockService)
→ new ClockService()
→ super(ctx, 'clock') registers the service
→ Cordis notifies Fibers that depend on clock
→ Consumer enters LOADING
→ consumer.apply()
→ ctx.clock resolves to ClockService
→ now() is called
```

`declare module` only provides TypeScript types. The actual runtime service registration comes from `super(ctx, 'clock')`.

When the Provider unloads:

```text
clock service is unregistered
→ Consumer's dependency is no longer satisfied
→ Consumer automatically unloads and cleans up its effects
→ Consumer returns to PENDING
```

When the Provider returns, the Consumer loads again.

### 9.3 Event Middleware

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

Invocation:

```ts
const result = await ctx.waterfall(
  'text/format',
  'hello',
  async () => 'hello',
)
```

The result is `HELLO`. If a listener does not call `next()`, it short-circuits the remaining listeners and the default implementation.

`ctx.on()` is itself an effect, so the listener is automatically removed when the plugin unloads.

### 9.4 DSH Tool Plugin

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

The flow is:

```text
Plugin Fiber is created
→ Waits for the tools service
→ Calls apply()
→ hello is registered with ctx.tools
→ The hello schema is exposed when the System Prompt is assembled
→ The model produces a hello call
→ Agent Loop calls ctx.tools.execute()
→ The tool pipeline calls hello.execute()
→ The result is written to tool/result
```

It is important to distinguish between:

```text
apply()         runs when the plugin activates and registers the tool
hello.execute() runs each time the model calls the tool
```

After the plugin unloads, `hello` is removed from the tool registry and is no longer visible to subsequent model requests.

## 10. Choosing Between Service, Event, and Effect

| Requirement | Mechanism |
| --- | --- |
| Call a specific capability and receive a result | Service method |
| Broadcast that something has happened | Event `emit` |
| Let multiple asynchronous observers process concurrently | Event `parallel` |
| Search sequentially for a handling result | Event `serial` / `bail` |
| Wrap, transform, or short-circuit a default behavior | Event `waterfall` |
| Manage timers, connections, or watchers | `ctx.effect()` |
| Install a child capability | `ctx.plugin()` |
| Declare a required capability | `inject` |
| Use a capability that may not exist | `ctx.get()` |

## 11. Common Sources of Confusion

```text
Plugin ≠ Fiber
A Plugin is a definition; a Fiber is one runtime instance.

Context ≠ global object
Each Fiber has its own child Context.

apply ≠ run on every request
apply installs contributions; actual business calls usually enter service methods or execute().

inject ≠ import
inject is a runtime service dependency; import is a code-module dependency.

declare module ≠ register a service
It only provides TypeScript types.

ctx.effect ≠ timer API
It binds an external resource and its cleanup function to a Fiber's lifecycle.

Cordis Event ≠ DSH SessionEvent
A Cordis Event is in-process communication; a SessionEvent is a durable, replayable agent fact.
```

## 12. Recommendations for Extension Development

Most DSH extensions can begin as an independent plugin project without forking all of DSH:

1. Create a separate Git repository and npm package.
2. Add `@deepseek-ai/cordis` and the required DSH Service Definition packages as dependencies or peer dependencies.
3. Write a Cordis plugin.
4. Make the plugin's `register()` return a disposer, and put every resource inside an effect.
5. Create a bundle or profile patch.
6. Install it with `dsh plugin --profile <name> add <package>`.
7. Inspect the final composition with `dsh --profile <name> --dump-config`.

Changes to DSH core are usually necessary only when:

- existing extension points cannot express the requirement;
- the Session persistence format or the fundamental semantics of the Agent Loop must change;
- a shared Service Definition spanning multiple packages must change;
- the build, release, or Host/Client RPC generation mechanism must change.

In most other cases, a plugin, provider, consumer, preset, or bundle is sufficient.
