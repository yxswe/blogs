---
title: "How DSH Is Built on Cordis"
description: Starting from Cordis's dynamic-composition model, this article follows boot, the Agent Loop, Sessions, Services, and Agent Presets to explain the architecture and plugin boundaries of DeepSeek Harness.
lang: en
translationKey: dsh-cordis-architecture
date: 2026-08-24
tags:
  - Agent Harness
  - DeepSeek
featured: false
---

# How DSH Is Built on Cordis

The previous article explained Cordis's Revertible Effects, Reactive Coeffects, Contexts, and Fibers from the paper. This article takes a different view. Instead of studying Cordis in isolation, it follows the actual [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) code to answer five questions:

1. Where does Cordis sit inside DSH?
2. What does DSH mean by an Agent?
3. Which major Services make up the system?
4. Which capabilities can be replaced, and how does replacement work?
5. Where does “everything is a plugin” stop?

The short answer is:

> Cordis does not define an Agent. It provides the runtime rules for organizing a dynamic system. DSH defines domain contracts such as Agent, Session, LLM, and Tools on top, supplies their default implementations as plugins, and uses configuration to compose those implementations into a working harness.

## 1. A Brief Return to the Cordis Paper: It Defines Composition Rules

The Cordis paper, [*A Programming Paradigm for Spatiotemporal Composability*](https://github.com/cordiverse/paper/blob/main/paper.pdf), is not about agents. It studies a more fundamental problem: when components can join, leave, or be replaced at runtime, how can the system remain consistent?

The paper separates the problem into two dimensions:

| Problem | Cordis's answer |
| --- | --- |
| When a component leaves, how are its listeners, Services, background tasks, and other modifications reversed? | Revertible Effects: when a component creates an effect, it also registers cleanup; the runtime executes cleanup in reverse order during unload. |
| When a Service appears, disappears, or changes implementation, how should dependent components respond? | Reactive Coeffects: components declare dependencies, and the runtime re-evaluates them after Service changes, activating, unloading, or reloading components as needed. |

The two mechanisms meet in `Context`: components read Services from a Context and modify the Context through Effects. Each running component instance is a `Fiber`, which stores its dependency snapshot, lifecycle state, and cleanup operations. The Loader turns declarative configuration into a Fiber tree and reconciles configuration or hot-module changes.

Cordis is therefore a meta-framework. It does not require models, tools, or Sessions; it supplies this general grammar:

```text
A component declares the Services it needs
          ↓
Cordis activates its Fiber when those dependencies are available
          ↓
The component provides Services, registers listeners, or creates other Effects
          ↓
Service changes cause dependent lifecycles to be re-evaluated
          ↓
When the component leaves, Cordis reverses the Effects recorded by its Fiber
```

DSH puts the product concepts of an agent harness into that grammar.

## 2. The DSH System: Configuration Comes Before the Code Entry Point

A conventional application often has a fixed `main()` that creates a database, model client, tools, and Web server in order. DSH starts differently: the entry point first resolves a Profile, then combines several configuration layers into a Cordis component tree.

The default composition looks roughly like this:

```text
Profile
├── dsh-base: shared Session, Agent, LLM, Tools, persistence, Sandbox, and more
├── dsh-web-app or dsh-headless: browser surface or one-shot task entry
├── the Profile's cordis.patch.yml
├── the Harness Home patch
└── command-line --patch overlays
          ↓
Final Cordis configuration tree
          ↓
Loader imports components and creates Fibers
          ↓
Components activate when their dependencies are satisfied
```

A later patch can address an earlier row by stable `id`, replace its configuration, disable it, or insert another component. Row order is not boot order; declared Service dependencies determine activation. This is Reactive Coeffects applied directly to DSH startup.

The [`dsh-base` configuration](https://github.com/deepseek-ai/deepseek-harness/blob/main/packages/bundle/base/cordis.patch.yml) is not a small set of optional extensions. It is the product's default implementation: the Agent, Loop, model adapters, Session persistence, tools, permissions, Sandbox, Skills, Subagents, Compaction, and Web Search are all ordinary rows. The [Web Bundle](https://github.com/deepseek-ai/deepseek-harness/blob/main/packages/bundle/web-app/cordis.patch.yml) adds the Host API, HTTP server, and browser plugins, while moving per-Agent tools into Agent Presets.

The first step in understanding a running DSH system is therefore not finding one privileged main function, but inspecting the final composition:

```sh
dsh --profile web --dump-config
```

That output is the system the machine actually boots.

## 3. Component, Service, and Event Have Different Jobs

These concepts are easy to conflate, but they play distinct roles.

### Component: an implementation with a lifecycle

A Cordis plugin is a Component. It may be a function, an object with `apply(ctx)`, or a class extending `Service`. One Loader configuration row mounts one Component and creates a Fiber.

A Component may provide a Service, but it may instead only register a tool, prompt section, or event listener. Components and Services are therefore not one-to-one.

### Service: a stable name through which components use a capability

A Service exposes a capability from Context as `ctx.<key>`. For example:

- `ctx.llm`: model-adapter registration and streaming calls;
- `ctx.sessions`: the in-memory Session Store;
- `ctx.tools`: tool registration and the execution pipeline;
- `ctx.fs`: filesystem access;
- `ctx.agentLoop`: the default Agent driver.

A complete replaceable capability usually has three roles: a component defining the Service interface, a component providing an implementation, and a component consuming it. For the filesystem capability, `dsh-fs` defines `ctx.fs`; `dsh-fs-local`, `dsh-fs-sandbox`, and `dsh-fs-e2b` provide different implementations; filesystem tools depend only on `ctx.fs`, not on any concrete implementation.

### Event: intervene in a flow without replacing its Service

Services support direct capability calls; Events support observation and interception. DSH has several important event domains:

- Session Events record durable facts;
- `agent/*` Events coordinate a live Agent;
- `tools/*`, `llm/*`, and `fs/*` Events expose policy and middleware points.

A plugin need not replace the entire Agent Loop to rewrite messages in `agent/pre-step`, adjust request configuration in `agent/request`, or add authorization, deadlines, and auditing around `tools/execute`.

## 4. What DSH Means by an Agent

In DSH, an Agent is neither an LLM nor a static “prompt plus tools” configuration. The [`Agent` interface](https://github.com/deepseek-ai/deepseek-harness/blob/main/packages/core/agent/src/runtime-types.ts) is closer to a controller for one live conversation. It contains:

- one `id` shared with its Session;
- the current provider route and model options;
- a `session` containing durable facts;
- an `inbox` of pending input;
- an `idle` or `running` status;
- an Agent-specific `agent.ctx`;
- control methods such as `followup()`, `steer()`, `inject()`, and `cancel()`.

Three separations are central to this design.

### Agent Registry and Agent Loop are separate

`ctx.agents` owns the live Agent registry, creation, lookup, ownership, and lifecycle, but it does not run the model loop. `ctx.agentLoop` supplies creation and driving, with `dsh-agent-loop` as the default implementation. UI, ACP, SDK, and Subagent code can therefore depend on the stable Agent Service without importing the concrete Loop.

DSH separates what an Agent is from how it runs:

```text
ctx.agents       = stable Agent management interface
ctx.agentLoop    = the selected execution algorithm
ReactLoopAgent   = Agent instance created by the default Loop
```

### Session is fact; Agent is live control

A Session is an append-only log of typed `SessionEvent`s. Model history is not maintained as a second mutable array; it is derived from the effective Surface of that log. Turns, Steps, streamed model output, tool calls, and tool results all become events.

The repository enforces a crucial rule: **model-visible means logged**. Anything entering a model request must be reconstructable from the Session Log. Resume, Fork, Compaction, Telemetry, and UI replay can therefore share one source of truth instead of maintaining divergent state.

The Agent is the process-local live object. It owns its Inbox, cancellation signals, current activity, and scoped Context. A restart can construct a new Agent from a persisted Session, but the old Agent object and its process-local resources are not serialized.

### Turn and Step are the default Loop's units of execution

The default Loop can be summarized as follows:

```text
Input enters the Agent Inbox
        ↓
Open a Turn and claim next-turn / next-step input
        ↓
agent/pre-step may reject or rewrite the input
        ↓
Assemble the System Prompt and currently visible Tool Schemas
        ↓
Derive model history from the Session Log and call ctx.llm
        ↓
Append Stream Chunks and the final Assistant Message to the Session
        ↓
Execute Tool Calls through ctx.tools and record Tool Results
        ↓
If tools or steering require more work, open another Step; otherwise end the Turn
```

A Turn may contain several Steps. One Step is one model request plus the tool executions it causes. The Agent Loop stays relatively small by delegating to `sessions`, `systemPrompt`, `llm`, and `tools`, with Events at each boundary.

## 5. The Major DSH Services by Layer

The repository contains many Services, but the architecture becomes manageable when they are grouped into six layers:

| Layer | Major Services | Responsibility |
| --- | --- | --- |
| Agent spine | `sessions`, `agents`, `agentLoop`, `systemPrompt`, `tools`, `llm` | Store facts, drive Turns and Steps, assemble requests, and invoke models and tools. |
| Execution environment | `fs`, `subprocess`, `shell`, `terminals`, `sandbox`, `sandboxPolicy`, `lsp`, `codeRuntime` | Turn model actions into local, confined, or remote execution. |
| Agent capabilities | `skills`, `web`, `subagents`, `workflowEngine`, `jobs`, `compaction`, `goals`, `planMode` | Add retrieval, delegation, workflows, long-running work, and context management around the core loop. |
| Data and recovery | `sessionPersistence`, `sessionQuery`, `sessionProjections`, `attachments`, `spillStore`, `storage` | Persist and query logs, build projections, and store large objects. |
| Configuration and collaboration | `settings`, `credentials`, `approval`, `permissionPresets`, `commands`, `userQuestions` | Manage configuration, secrets, authorization, commands, and human decisions. |
| Delivery surfaces | `typert`, `typertGateway`, `apiProxy`, `webServer`, `clientModules`, and browser `slots` | Project Host capabilities into SDK, API, and Web UI surfaces. |

The central dependency chain is:

```text
Agent Loop
├── sessions: read and append durable facts
├── systemPrompt: collect Prompt Sections and Tool Schemas
├── llm: select a model adapter and produce a stream
└── tools: resolve tools and run the guarded execution pipeline
      ├── fs / shell / web / subagents / workflow ...
      └── approval / sandbox / timeout / spill policies
```

This reveals DSH's central view of an Agent: the Agent itself is a small runtime controller. Most capabilities live in the Services it depends on and the Event extension points around them.

## 6. Which Services Can Be Overridden, and How?

“Replaceable” has at least four different meanings in DSH.

### 6.1 Replace a single-instance Service implementation

Within one Context realm, a Service name can have only one implementation. A second component providing the same name fails instead of silently overriding it. To replace `ctx.fs`, `ctx.shell`, or `ctx.sessionPersistence`, a composition disables or replaces the original row and mounts a compatible implementation.

Typical replaceable capabilities include:

- Session Persistence: JSONL or SQLite;
- Filesystem: Local, Sandbox, or E2B;
- Subprocess: Local or E2B;
- Shell: local Bash, sandboxed Bash, or PowerShell;
- Sandbox, Code Runtime, Compaction, Workflow Engine, and Spill Store;
- the Agent Loop itself.

Compatibility matters: the new component must preserve the same Service interface and lifecycle semantics. Otherwise dependencies may activate successfully while runtime behavior is still incorrect.

### 6.2 Keep a registry Service and add or replace entries within it

Some Services are registries. The usual extension is not replacing the registry object, but registering entries in it:

- `ctx.llm` registers model adapters by provider route;
- `ctx.tools` registers Tool Definitions by tool name;
- `ctx.systemPrompt` registers Sections, Variables, and Context providers by name;
- `ctx.web` registers Search and Fetch implementations by id;
- `ctx.skills` registers Skill sources;
- `ctx.subagents` registers Subagent implementations.

Duplicate names at one layer generally fail. A registration in an Agent Scope can instead shadow a global entry for that Agent. One Agent can therefore have its own Persona, tool version, or restrictions without changing any other Agent.

### 6.3 Use `isolate` to create a private Service realm

Cordis `isolate` allows the same Service name to resolve to different implementations in different realms. DSH Agent Presets use this for Services genuinely owned by one composition.

For example, the [`minimal` preset](https://github.com/deepseek-ai/deepseek-harness/blob/main/apps/cli/config/agent-presets/minimal/agent.cordis.yml) provides `terminals` in its own realm and shadows the Host's sandboxed `fs` with a local filesystem. Other Agents continue using the Host implementations.

Not every Service belongs in an Agent realm. The Session Store, persistence, Sandbox Policy, model route, and Subagent Registry are shared by the Host or across Sessions and must stay in the Host Plane. A preset component that provides a Service must place it in an explicit `isolate` realm unless the Service belongs on the Host; otherwise it leaks into the process-level realm and conflicts with other Presets.

### 6.4 Keep the Service and rewrite one decision through Events

Many extensions require no Service replacement:

- model-request retry can wrap `llm/stream`;
- Compaction can intercept `agent/pre-step`;
- Tool Timeout can wrap the tool execution pipeline;
- permission and filesystem-observation policies can listen to capability events;
- the Goal Driver can steer at the Turn stopping boundary.

This form preserves the core Service and replaces one decision, making it easier to compose with other plugins.

## 7. Host Plane, Agent Plane, and Client Plane

DSH does not have one flat plugin tree. It has three important composition spaces.

### Host Plane: infrastructure shared by the process

The Host Plane contains Services shared across Sessions or read by entry points: the Session Store, persistence, LLM Registry, Tool Registry, Sandbox, Approval, Settings, Credentials, Subagent Registry, and API Gateway.

### Agent Plane: the capability view of one Agent

In Web mode, an Agent Preset determines an Agent's Persona, tools, Prompt Sections, Compaction, Workflow, and other capabilities. The standard Preset is mounted once, and Agents join it through a scope parent chain:

```text
The Agent's own Scope
        ↓
The selected Preset Scope
        ↓
The Host's global Scope
```

The nearest registration wins, so an Agent may shadow its Preset, and a Preset may shadow the global layer. Mutable state remains separated by using the Session or Agent as a key inside shared plugin instances.

Presets do not switch arbitrarily during a running conversation. DSH only allows a content-free Agent to change Preset. Once the Session contains model requests or tool calls, a different tool and prompt composition would make recorded history inconsistent with current capabilities. An Agent also keeps the Preset generation it joined; file changes affect Agents created later.

### Client Plane: another Cordis runtime in the browser

The Web UI is plugin-based too, but it runs in its own browser-side Cordis Context. The Host supplies the API and module manifest, while Client plugins register UI into sidebar, conversation, composer, and Tool Card slots. A Host Service does not automatically appear in the Client just because it has the same name; it must be explicitly projected through Typert and the API Gateway.

“Everything is a plugin” therefore does not mean every plugin shares one global container. Visibility is constrained by process, realm, Agent scope, and the Host/Client boundary.

## 8. The Real Boundary of “Everything Is a Plugin”

DSH is deeply plugin-based: model adapters, the Agent Loop, Session Store, tools, persistence, Sandbox policy, APIs, and UI all appear in composition. But this does not mean everything can be hot-swapped without conditions.

### Cordis itself is not a plugin

Context, Fiber, Effect tracking, Service resolution, the Loader, and the JavaScript process hosting them are the substrate. “Everything” refers to DSH product capabilities, not to the composition runtime itself.

### Interfaces and persistence semantics cannot be broken casually

Implementations can be replaced, but Agent, SessionEvent, Tool, and LLM Stream contracts are the shared language between components. A replacement Agent Loop must still honor Agent creation, cancellation, ownership, and logging rules. A replacement persistence backend must still preserve append-only ordering, contiguous sequence numbers, and crash repair.

### Only registered Effects are automatically reversible

`ctx.effect()`, `ctx.on()`, and registration methods returning disposers unwind with a Fiber. If a component bypasses these mechanisms to mutate globals, start an untracked task, or change an external system, Cordis cannot restore the previous state. Database writes, sent email, and payment requests are outside Context rollback entirely.

### Plugin composition is not a security boundary

A Preset is executable composition and has trust comparable to shell access. DSH's Cordis authoring mode lets an Agent inspect the runtime and temporarily `define/run/stop` dynamic components, but those components live only in process memory, are not automatically persisted, and run in a VM that is containment for cooperative code rather than a security boundary.

### Runtime capability is not the same as enabling everything by default

Cordis supports configuration reconciliation and HMR, but the current Web and Headless Bundles disable general HMR by default. DSH takes a more controlled path: new Sessions use a new Preset generation, or an explicitly authorized Cordis session runs temporary components. “The runtime can replace components” should not be read as “every production Agent immediately recomposes whenever a file changes.”

### Some behavior still belongs to the default Loop algorithm

Plugins can change a great deal through Services and Events, but the Turn/Step state machine, logging boundaries, and tool scheduler still belong to the default `agent-loop`. Changing those foundational semantics means replacing the Loop while continuing to honor its external contracts, not patching arbitrary internals.

A more precise statement is:

> DSH makes product capabilities plugins with explicit contracts and lifecycles wherever possible, but those plugins still operate within boundaries defined by Cordis, the process, durable formats, the trust model, and cross-surface protocols.

## 9. Putting the Architecture Together

From boot to one model request, the complete DSH path can be compressed into this sequence:

```text
Profile + Bundles + Patches
        ↓
Loader builds the Host Component / Fiber Tree
        ↓
Service dependencies determine when components activate
        ↓
An entry point creates an Agent and Session through ctx.agents
        ↓
The Agent Scope joins a Preset and receives its own tool and prompt view
        ↓
The Agent Loop opens Turns and Steps from the Inbox
        ↓
Session + SystemPrompt + LLM + Tools cooperate to execute the request
        ↓
Every model-visible fact is appended to the Session Log
        ↓
UI / SDK / Persistence / Telemetry read the same facts through Events and projections
```

Cordis owns the vertical lifecycle: when components exist, when dependencies are satisfied, and how their effects unwind. DSH owns the horizontal product semantics: what an Agent is, how a Turn runs, which facts are durable, how tools and models connect, and which capabilities each Session can see.

Together, these layers make “everything is a plugin” an executable architecture principle rather than a statement about directory layout. The default product is itself a composition, and extensions use the same mechanism that boots the system in the first place.
