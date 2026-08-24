---
title: "DeepSeek Harness: Trajectories, Evaluation, and Self-Evolution"
description: Understanding agent trajectories through the Session event stream, and how DSH can move from observable execution to reliable evaluation and controlled self-evolution.
lang: en
translationKey: dsh-trajectory-evolution
date: 2026-08-24
tags:
  - Agent Harness
  - DeepSeek
featured: false
---

# DeepSeek Harness: Trajectories, Evaluation, and Self-Evolution

> A trajectory records what an agent did, evaluation judges how well it did, and self-evolution changes future behavior or the system based on that judgment. Only together do they form a complete improvement loop.

## 1. The Three Concepts Are Not the Same

In DSH, they can first be separated with three questions:

| Concept | Question | Primary output |
| --- | --- | --- |
| Trajectory | What did the agent actually experience? | A replayable event sequence |
| Evaluation | How good was that execution? | Scores, decisions, and diagnoses |
| Self-evolution | What should change next time? | Prompt, tool, policy, plugin, or model updates |

Their ideal relationship is:

```text
Execute a task
→ Record the trajectory
→ Let an evaluator read the task, trajectory, and outcome
→ Locate failure modes
→ Generate candidate changes
→ Re-run and evaluate them in isolation
→ Promote effective changes and roll back ineffective ones
```

A trajectory is evidence, not quality by itself. Evaluation is judgment, but it does not automatically cause improvement. Modifying a system is not automatically “evolution” either; only changes that pass repeatable evaluation and admission controls form a reliable loop.

## 2. The Basic Units of a DSH Execution

Three levels must be distinguished before discussing trajectories:

- **Session**: a persistent, recoverable interaction container and the boundary of the event log;
- **Turn**: one unit of work initiated by the user;
- **Step**: one model request and the tool calls produced by that request.

One Turn can contain multiple Steps. A model may search for files, read the results in another model request, and continue until it answers or stops.

A typical flow is:

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
→ ctx.llm calls the model Provider
→ assistant/chunk* + assistant/message
→ Tools execute and tool/result is recorded
→ Continue to the next Step when necessary
→ step/end
→ turn/end
```

Tool execution has its own pipeline:

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

What the model said is therefore only one part of the trajectory. A diagnostically useful trace must also capture the context it saw, the tools it selected, whether permission was granted, what the tools returned, and how state changed.

## 3. A Trajectory Is a Projection of the Session Log

The DSH Session event log is the authoritative source of execution facts. Model history, recovery, forks, the Trajectory UI, Telemetry, and persistence are all derived from it.

The relationship can be viewed as:

```text
Session Event Log (fact layer)
├─ Conversation view
├─ Model context
├─ Trajectory UI
├─ Recovery and forks
└─ Evaluation input
```

The Trajectory UI is therefore not an independent recording system. It selects, correlates, and visualizes the event stream. When adding diagnostic information, the first question is whether it should become a durable Session fact rather than a temporary UI field.

Two types of events must also remain distinct:

- **Cordis Events** support in-process plugin communication and middleware composition;
- **DSH SessionEvents** support persistence, replay, and reconstruction of agent execution.

The former decouple runtime components; the latter record facts. Only information stored in the Session log can reliably participate in cross-process recovery and offline evaluation.

## 4. A Trajectory Must Include the Available Action Space

The same model can produce very different trajectories under different presets because it sees different tools and services. The `standard` preset typically includes shell access, file operations, search, background jobs, Skills, Goals, subagents, Workflows, and web search. The `minimal`, `code`, and `cordis` presets expose different action interfaces.

A plugin being installed does not mean its tool is exposed to the current model. Visibility still depends on the profile, preset, scope, and configuration. Evaluating a trajectory therefore requires at least:

| Context | Why it matters |
| --- | --- |
| Model and parameters | Separates capability differences from randomness |
| System Prompt | Explains behavioral constraints and policy sources |
| Tool schemas | Establishes which choices the model had |
| Profile / Preset | Reconstructs the service and tool composition |
| Permissions and Sandbox | Distinguishes inability from denial |
| Tokens, latency, and external requests | Measures efficiency and cost |

For example, DeepSeek's official search initiates an additional full Messages model request. Counting only the main agent's Steps underestimates actual latency and token cost.

## 5. The Current Evaluation Gap

The default DSH runtime currently has no independent evaluator. Goal and Ralph completion is primarily declared by the agent or worker itself. Snapshot tests, end-to-end tests, and tests against real APIs belong to the development verification system; they are not independent judgments of each agent run.

This creates a central risk: **the executor also acts as the judge**. An agent may declare the task complete without verifying the outcome that matters to the user.

A fuller evaluation should cover at least four layers:

1. **Outcome evaluation**: do the final files, tests, pages, or external state satisfy the task?
2. **Process evaluation**: did the trajectory detour, repeat calls, ignore evidence, or stop too early?
3. **Safety and constraint evaluation**: did it overreach, expose information, or violate approval and Sandbox rules?
4. **Efficiency evaluation**: were tokens, time, tool calls, and external API costs reasonable?

An evaluator should not return only a total score. A more useful result is:

```text
Whether the task succeeded
+ The Step where failure occurred
+ Event evidence supporting the judgment
+ Failure category
+ The layer that should change
```

This makes it possible to distinguish changes to the Prompt, tool descriptions, permission policy, context construction, Agent Loop, or underlying model.

## 6. Self-Evolution Is Not Runtime Self-Modification

The `cordis` preset already allows an agent to inspect the current plugin tree and temporarily define, run, and stop model-authored plugins. This is a useful experimental surface, but those dynamic plugins disappear after the process restarts.

It is therefore closer to runtime prototyping than a complete self-evolving system. Reliable self-evolution requires an additional control plane:

```text
Observe a failed trajectory
→ Propose an explainable change hypothesis
→ Generate a candidate plugin / Prompt / configuration
→ Run it in an isolated profile
→ Evaluate it against fixed tasks and a regression set
→ Compare quality, safety, and cost
→ Apply human approval or policy admission
→ Publish it as a formal plugin, preset, or patch
→ Preserve versions and rollback capability
```

Writing a plugin that runs completes only the generation stage. Without a baseline, comparative evaluation, regression set, versioning, and rollback, there is no way to tell whether the system is evolving or merely drifting.

## 7. Research Questions Worth Pursuing Next

This topic can be divided into more concrete questions:

1. What is the complete SessionEvent schema, and which events can be replayed reliably?
2. How does the Trajectory UI correlate streaming chunks, tool calls, and Steps?
3. Which events are reused after a fork, and which runtime state is regenerated?
4. How can a task-level evaluator avoid relying on the agent's self-declaration?
5. How can evaluation evidence point back to specific events instead of only producing a score?
6. How can dynamic Cordis plugins enter an isolation, evaluation, promotion, and rollback pipeline?

These questions cover the data model, observability, experimental design, evaluation trustworthiness, and release governance. They are closer to a practical self-evolving system than simply asking whether an agent can modify itself.

## 8. Conclusion

DSH already has two important foundations for an improvement loop: replayable trajectories centered on the Session event log, and the ability to compose capabilities dynamically through Cordis. The clearest missing layer lies between them: independent, evidence-driven, repeatable evaluation.

The sensible progression is therefore not to let an agent permanently modify itself first. It is to make every execution reproducible, comparable, and attributable, then use evaluation results to drive controlled changes.
