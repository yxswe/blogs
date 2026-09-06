---
title: "After Loader Startup: How a DSH Agent Runs"
description: Following the Agent entry point and a complete execution path, this article explains how DSH's foundational components work together after Loader builds the component runtime.
lang: en
translationKey: dsh-agent-runtime
date: 2026-08-30
tags:
  - DeepSeek Harness
  - Cordis
featured: false
---

The previous article explained how DSH composes a component tree from a Profile and how Loader turns that tree into a runtime made of Contexts and Fibers. The next question is what happens afterward: where does a DSH Agent start, and how does it run?

The key point is that, in the Web Profile, Loader completing startup only means that the foundational Services required by Agents are ready. It does not mean an Agent instance already exists. Creating an Agent and driving it are two different entry points.

## 1. No Web Agent Exists When Loader Finishes

`dsh-base` first places the core components required by Agents into the host component tree:

| Component | Service | Role |
| --- | --- | --- |
| `@deepseek-ai/dsh-agent` | `ctx.agents` | Defines the Agent interface, tracks live Agents, and exposes the creation entry point |
| `@deepseek-ai/dsh-session` | `ctx.sessions` | Tracks live Sessions; each Session event log is the source of truth for conversation history |
| `@deepseek-ai/dsh-llm` | `ctx.llm` | Registers model adapters and provides the streaming model-call entry point |
| `@deepseek-ai/dsh-system-prompt` | `ctx.systemPrompt` | Assembles system prompts, runtime context, and tool schemas |
| `@deepseek-ai/dsh-tools` | `ctx.tools` | Registers tools and handles policy checks, execution, and result processing |
| `@deepseek-ai/dsh-agent-loop` | `ctx.agentLoop` | Creates concrete Agents and drives turns, steps, model calls, and tool calls |

`dsh-agent-loop` explicitly depends on the first five Services:

```ts
static inject = ['agents', 'sessions', 'llm', 'tools', 'systemPrompt']
```

The Web Profile starts `agent-loop` with this configuration:

```yaml
- id: agent-loop
  name: '@deepseek-ai/dsh-agent-loop'
  config:
    agents: []
```

An empty `agents` array means that no Agent is created during startup. At this point, foundational Services such as `ctx.agents`, `ctx.sessions`, and `ctx.llm` are available and the Web server is listening, but a concrete Agent is created only when the browser creates or resumes a Session.

## 2. An Agent Has Two Entry Points: Creation and Execution

### 2.1 `session.create` Creates the Agent

When the browser starts a conversation, the request eventually reaches `session.create` in the host-side `api-proxy`. Its `ensureSession()` function checks the target Session:

- reuse a live Agent with the same id;
- restore a persisted Session through `ctx.agents.resume()`;
- otherwise create one through `ctx.agents.create()`.

`ctx.agents` is the Agent Registry provided by `dsh-agent`. It defines the creation API and tracks live Agents, but it does not implement the conversation loop. When `dsh-agent-loop` starts, it registers itself as the Registry's factory:

```ts
ctx.agents.setFactory(this)
```

`ctx.agents.create()` therefore delegates to `AgentLoop.createAgent()`. The creation path can be reduced to:

```text
session.create
    ↓
api-proxy.ensureSession()
    ↓
ctx.agents.create()
    ↓
AgentLoop.createAgent()
    ├── prepare a Session
    ├── create a ReactLoopAgent
    ├── create the Agent Context and Inbox
    ├── apply the Agent Preset
    └── publish the Session and Agent
```

The concrete Agent instance is a `ReactLoopAgent`. It is not a component Fiber created directly by Loader; it is an ordinary object constructed by `AgentLoop` at runtime. It owns a Session, an Inbox, and a Context carrying its Agent scope:

```ts
this.scope = createScope(loopCtx, this)
this.ctx = this.scope.ctx.extend({ agent: this })
```

Before publication, `api-proxy` applies the selected Agent Preset through `setup(agentCtx)`. The default `standard` Preset determines the persona, instructions, and tools visible to this Agent. If any part fails to load, the entire Agent creation rolls back instead of leaving a partially composed Session.

After creation succeeds, the Agent is registered in `ctx.agents` and its Session is registered in `ctx.sessions`, but the Agent remains `idle` and has not called a model.

### 2.2 `session.prompt` Wakes the Agent

When the user sends a message, the request enters `session.prompt` in `api-proxy`. After checking model availability, time zone, and attachments, the host converts the input to a `UserMessage` and calls one of these methods based on the requested mode:

```ts
if (mode === 'steer') agent.steer(message)
else agent.followup(message)
```

Both methods write the message into the Agent's Inbox and wake its driver:

- `followup()` places a message in `next-turn` to start an ordinary new Turn;
- `steer()` places it in `next-step`; it starts a Turn when idle or enters the next Step while running;
- `inject()` also writes to `next-step`, but does not wake the Agent and is normally used to add context to the next model request.

The method that actually moves the Agent from `idle` to `running` is `ReactLoopAgent.wakeDriver()`. It starts `kick()`, which then processes Turns and Steps.

## 3. What an Agent Instance Contains

The `Agent` interface defined by `dsh-agent` contains only the state and operations needed to run one Agent:

| Member | Role |
| --- | --- |
| `id` | The unique id shared by the Agent and Session |
| `options` | The current provider, model, and output-token limit |
| `session` | The current conversation and its append-only event log |
| `inbox` | Follow-ups, steering, and injected messages not yet admitted to a model request |
| `status` | Either `idle` or `running` |
| `ctx` | A Context carrying the current Agent scope |
| `followup()` | Queue an ordinary new Turn and wake the Agent |
| `steer()` | Send a message to the nearest next Step and wake the Agent |
| `inject()` | Add context to the next Step without waking the Agent |
| `cancel()` | Abort the active work, optionally preserving the Inbox |
| `whenIdle()` | Wait until the Agent is fully idle |

The `Agent` interface and the `ReactLoopAgent` implementation live separately. Other components depend on `ctx.agents` and the Agent interface rather than knowing about the default loop class. A different loop implementation can therefore preserve the same entry points.

## 4. How One Agent Run Completes

DSH divides a conversation into Turns and Steps:

- A **Turn** begins with a waking message and ends when all current work is complete.
- A **Step** is one model request plus the tool calls produced by that request.

One Turn may contain several Steps. For example, the model may first request a file read, then make another model request after the tool result arrives to produce the final response.

```text
session.prompt
    ↓
followup() / steer()
    ↓
write to Inbox and wake the Agent with wakeDriver()
    ↓
turn/start
    ↓
claim Inbox messages and assemble the prompt and tool schemas
    ↓
step/start → user/message
    ↓
derive message history from the Session log
    ↓
agent/request → ctx.llm → model stream
    ↓
assistant/chunk → assistant/message
    ↓
Tool calls? ── no ──→ step/end → turn/end
    │
    yes
    ↓
tool/call → execute through ctx.tools → tool/result
    ↓
enter the next Step
```

### 4.1 Before the Model Request

At the start of each Step, the Agent claims messages from its Inbox and calls `ctx.systemPrompt.assemble()`. This gathers the persona, instructions, dynamic context, and tool schemas visible in the current Agent scope. The `agent/pre-step` extension point then decides whether the Step should proceed.

After admission, each message is appended to the Session as `user/message`. The Agent then calls `deriveMessages()` on the Session log to reconstruct model history instead of maintaining a separate chat array. The `agent/request` extension point resolves request configuration such as provider and model, after which `ctx.llm` selects the corresponding Adapter and starts the stream.

### 4.2 After the Model Responds

Each model chunk is recorded as `assistant/chunk`, followed by the complete `assistant/message` when the stream ends. If the message contains no tool calls, the Step completes and the Turn may end.

If the message contains tool calls, AgentLoop passes them to `ctx.tools`. Every call moves through policy checks, tool dispatch, and result processing, while `tool/call` and `tool/result` are recorded in the Session. Those results become context for the next Step, and the Agent calls the model again. This continues until the model stops calling tools, a tool explicitly concludes the Turn, an error occurs, or the user cancels.

At the end, the Session records `step/end` and `turn/end`, and the Agent returns to `idle`. The Web UI primarily renders streaming text, tool calls, and results from Session events, while `agent/status` reports whether the Agent is running.

## 5. The Split Between the Base Runtime and Agent Presets

The Web Profile does not duplicate the whole host runtime for every Agent. The Session Registry, Agent Registry, LLM adapters, Tool Registry, persistence, Sandbox, and API Gateway remain in the host runtime. An Agent Preset selects the model-facing components available to a category of Agents.

The default `standard` Preset adds a persona, project instructions, Shell and filesystem operations, search, Skills, goals, plan mode, context compaction, subagents, workflows, user questions, and Todo. The `minimal` Preset keeps only a fixed persona, persistent Bash, and a file editor.

The same `AgentLoop` can therefore drive Agents with very different capabilities. The loop remains responsible only for reading messages, calling the model, executing tools, and continuing to the next Step; the component composition supplies the actual prompts, tools, policies, and surrounding capabilities.

## References

- [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)
- [`dsh-base` component tree](https://github.com/deepseek-ai/deepseek-harness/blob/main/packages/bundle/base/cordis.patch.yml)
- [`dsh-agent`](https://github.com/deepseek-ai/deepseek-harness/tree/main/packages/core/agent)
- [`dsh-agent-loop`](https://github.com/deepseek-ai/deepseek-harness/tree/main/packages/core/agent-loop)
- [`dsh-host-apiproxy`](https://github.com/deepseek-ai/deepseek-harness/tree/main/packages/host/apiproxy)
- [Default Standard Agent Preset](https://github.com/deepseek-ai/deepseek-harness/tree/main/apps/cli/config/agent-presets/standard)
