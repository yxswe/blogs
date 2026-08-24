---
title: "Cordis: How DSH Implements Dynamic Composition"
description: Starting from the original Cordis paper, this article explains the two problems of dynamic composition and how Revertible Effects, Reactive Coeffects, Contexts, and Fibers address them.
lang: en
translationKey: dsh-cordis
date: 2026-08-24
tags:
  - Agent Harness
  - DeepSeek
featured: true
---

# Cordis: How DSH Implements Dynamic Composition

DeepSeek Harness (DSH) organizes models, tools, Sessions, the Agent Loop, permissions, Sandboxes, and the Web UI as plugins. But “everything is a plugin” describes only the surface. The harder problem is: **how can these components change while the process keeps running and the system remains consistent?**

The original Cordis paper, [*A Programming Paradigm for Spatiotemporal Composability*](https://github.com/cordiverse/paper/blob/main/paper.pdf), addresses that problem directly.

In one sentence:

> Cordis uses Revertible Effects to manage how components modify their environment and Reactive Coeffects to manage how components depend on their environment, allowing components to be added, removed, and replaced without restarting the whole process.

## 1. Why Change Composition at Runtime?

Runtime composition lets a harness update one component without restarting the entire process. It provides three main benefits:

- **Continuity**: unrelated Sessions, connections, and background jobs keep running;
- **A smaller blast radius**: only the target component and its dependency subgraph reload;
- **In-place rollback**: if the new component fails, its effects can be reversed and the old version restored.

This matters especially for a self-evolving agent harness. For example:

```text
The agent generates and loads a log-analyzer tool
→ Evaluation finds that it performs poorly
→ The harness unloads the old plugin
→ It loads an improved version and continues the task
```

A Session checkpoint can support recovery after a process restart, but it cannot fully replace runtime composition. A Session event log can usually reconstruct persisted messages, completed Steps, tool results, and model context, but it can restore only **facts that have already been serialized**. Running shells, subagents, background jobs, streaming responses, connections, file handles, and plugin state that has not entered the log are difficult to recover losslessly from the Session alone.

The hardest case is an external operation that started but whose result was not persisted:

```text
The Session records tool/call
→ The harness invokes a payment or email API
→ The external operation succeeds
→ The process restarts before recording tool/result
```

After recovery, the log cannot prove whether the operation completed. Retrying may duplicate a payment or email; skipping it may leave the task incomplete. This requires idempotency keys, transaction logs, or verification against external state; checkpointing alone is insufficient.

A full restart also makes every Session and unrelated component share the pause, cold-start, and state-migration cost. The two mechanisms therefore solve different problems: Session checkpoints recover from process failure, while Cordis limits a local component change to the smallest affected dependency subgraph.

## 2. Dynamic Composition Has Two Orthogonal Dimensions

Traditional module relationships are usually fixed at compile time or startup. A dynamic plugin system must instead handle a continuously changing runtime environment:

- components appear, disappear, or are replaced at runtime;
- components have already registered listeners, started jobs, provided Services, or mounted children;
- other components may currently depend on those capabilities;
- the process still holds Sessions, connections, caches, and unfinished work.

If an old component cannot be completely reversed, stale tools, listeners, and service bindings contaminate later execution. If dependency changes do not propagate, Consumers continue using Services that are no longer valid.

The paper therefore studies more than how to import a plugin. It studies fine-grained **dynamic composition**: changing only the target component while correctly reversing its effects and coordinating the dependency changes that follow.

The paper separates the problem into two dimensions that cannot replace one another:

| Dimension | Core question | Cordis mechanism |
| --- | --- | --- |
| Temporal composability | When a component unloads, can its tools and listeners be unregistered, its background jobs stopped, and its Services withdrawn so the system returns to a state equivalent to before it loaded? | Revertible Effects |
| Spatial composability | When a component that provides a Service appears, disappears, or is replaced, can dependent components automatically activate, unload, or reload in the correct dependency order? | Reactive Coeffects |

Both must hold. Reversing side effects without notifying dependents leaves consumers using an invalid service. Managing dependencies without cleaning up timers, listeners, and service registrations cannot truly unload a component.

## 3. Revertible Effects: Every Modification Carries Its Inverse

An Effect is a modification a computation makes to its environment, such as:

- registering an event listener;
- starting a timer or file watcher;
- providing a Service;
- mounting a child component;
- opening a connection or acquiring another resource.

Cordis requires such a modification to provide an inverse at the same time:

```text
Apply Effect: environment A → environment B
Run inverse: environment B → environment A
```

The implementation primitive is `ctx.effect()`:

```ts
function heartbeat(ctx: Context) {
  ctx.effect(() => {
    const timer = setInterval(() => {
      ctx.logger.info('tick')
    }, 1000)

    return () => clearInterval(timer)
  })
}
```

The callback applies the modification and returns a disposer. Cordis records that disposer. When the Fiber unloads, all disposers run in LIFO order so that later resources are recovered first.

There is an important boundary: **Cordis does not prove that a disposer is correct.** The runtime records and invokes the inverse, but the component author remains responsible for ensuring that it restores the previous state. Side effects created outside the Context and left untracked cannot be reversed automatically.

Temporal composability therefore does not mean that the framework guesses how to clean up. It means:

> Every operation that mutates the shared environment goes through one controlled entry point and declares its recovery where the mutation is created.

## 4. Reactive Coeffects: Dependencies Follow a Changing Environment

Effects describe how a program changes its environment. Coeffects describe what the program requires from that environment.

In Cordis, a Service is a capability that a component exposes through the Context, such as model access, logging, or tool management. A component can provide Services and use `inject` to declare the Services it depends on. Whenever the Services available in the Context change, the runtime rechecks whether the component's dependencies are satisfied:

```ts
export const inject = ['llm']

export function apply(ctx: Context) {
  // This component activates only while llm is available.
  ctx.llm
}
```

Whenever the Context changes, Cordis re-evaluates dependency satisfaction and classifies the transition:

```text
activating    unsatisfied → satisfied   → activate the component
deactivating  satisfied → unsatisfied   → unload the component
neutral       satisfaction is unchanged → keep the lifecycle unchanged
```

This adds a reactive lifecycle beyond ordinary dependency injection. Traditional DI usually resolves objects at startup. Reactive Coeffects must also handle components that provide Services disappearing or being replaced while the process is running.

Cordis also provides two scoping mechanisms:

- `isolate()` makes the same Service key resolve to implementations provided by different components in different Contexts;
- `intercept()` leaves the component that provides the Service in place but changes how the current scope uses it, for example by attaching permission or configuration metadata.

## 5. Context: The Unified Boundary

The paper's decisive step is not merely placing Effects and Coeffects side by side. It unifies them in a single first-class Context:

```text
The LLM component registers the llm Service
                 ↓
The Agent depends on llm, so it activates and registers the agent Service
                 ↓
The Web Session depends on agent, so it activates
                 ↓
The LLM component is replaced, making llm temporarily unavailable
                 ↓
The Agent's dependency is no longer satisfied, so it unloads and removes the agent Service
                 ↓
The Web Session then loses agent and unloads as well
                 ↓
The new LLM component provides llm, reactivating the entire dependency chain
```

The `ctx` object in DSH is therefore not an ordinary configuration object or merely a Service Locator. It is simultaneously:

- Effect tracking boundary: records the listeners, timers, and Services created through the current Context so they can be reversed when the component unloads;
- Coeffect resolution space: determines which Services a component can use, allowing the same Service name to resolve to different implementations in different Contexts;
- current component scope: identifies which component instance the current code belongs to, so the runtime knows who owns its Effects and child components;
- entry point for component lifecycle and child relationships: provides one entry point for activating, unloading, or reloading components and mounting child components.

Context places “what I changed” and “what I require” inside the same observable runtime environment. That is what allows the two directions to coordinate automatically.

## 6. A Component Is a Definition; a Fiber Is a Runtime Instance

The paper distinguishes Components from Fibers:

```text
Component
├─ inject: Coeffects it requires
├─ provide: Coeffects it may provide
└─ apply: Effects performed on activation

Install a Component once
└─ Create a Fiber
   ├─ Owns a child Context
   ├─ Holds a committed dependency view
   ├─ Tracks Effects and disposers
   └─ Maintains lifecycle state
```

One Component may be installed multiple times, creating several independent Fibers. The Fiber is the runtime entity that can activate, unload, fail, and reload.

Its common states can be simplified as:

```text
INACTIVE → LOADING → ACTIVE → UNLOADING → INACTIVE
                       ↘ FAILED
```

When a component that provides a Service is removed, Cordis follows a crucial order:

1. The component enters `UNLOADING`, and its Service is no longer considered available.
2. Consumers discover that their Coeffect is no longer satisfied.
3. Consumers unload and recover their own Effects first.
4. Only after the Consumers finish does the component that provides the Service reverse its Effects.

The Consumer can therefore still read its committed dependency during teardown instead of losing the Service halfway through cleanup.

If the same Service key is provided by another component, the Consumer reloads even when the old and new values appear equal. The component identity has changed, making replacement an explicit lifecycle event rather than a silent object-reference swap.

## References

- Yifan Shi, Wei Zhang, Tianyi Cui, [*A Programming Paradigm for Spatiotemporal Composability*](https://github.com/cordiverse/paper/blob/main/paper.pdf), 2026.
