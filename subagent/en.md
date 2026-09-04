---
title: "How Codex Subagents Work: Creation, Communication, and Results"
description: "A concrete example of why Codex creates a subagent, how parent and child agents work concurrently, how messages are delivered, and how results return."
lang: en
translationKey: codex-subagent-runtime
date: 2026-09-05
tags:
  - Codex
  - Agent Harness
featured: false
---

# How Codex Subagents Work: Creation, Communication, and Results

This article explains the complete life of a Codex subagent, from creation to completion. It covers why the main agent delegates work, how a subagent runs independently, how the two continue to communicate, and how the result returns. The central idea is simple: **the model decides who should do what, while the Codex program handles creation, delivery, and scheduling.**

The implementation analysis is pinned to commit [`8e6a44b`](https://github.com/openai/codex/tree/8e6a44b428e31f91b21edc97904fcdf4f0931ade) of the OpenAI Codex repository, dated September 4, 2026.

## A Simple Mental Model

Suppose a user asks Codex to investigate a cross-platform test failure. The main agent decides to inspect Linux itself while assigning a subagent to Windows. For now, think of the three participants like this:

- **Main agent**: receives the user's request directly and produces the final combined answer;
- **Subagent**: an agent created by another agent to handle one well-defined piece of work;
- **Runtime**: the Codex program that creates agents, stores state, and delivers messages.

The overall process looks like this:

```text
user → main agent → create Windows subagent
                   ├─ main agent checks Linux
                   └─ subagent checks Windows
                                  ↓
                           result returns → user
```

The user still talks only to the main agent. A subagent is not another chat window; it is an independent line of work that Codex creates inside the same task.

The main agent operates that line of work through a set of collaboration tools. It can create a subagent, inspect its status, send messages, assign follow-up work, wait, or interrupt the current task.

| Tool | Purpose |
| --- | --- |
| `spawn_agent` | Create a subagent and give it its first task |
| `list_agents` | Show the current agents and their statuses |
| `send_message` | Add information for an existing agent |
| `followup_task` | Start follow-up work on an existing subagent |
| `wait_agent` | Wait for messages or completion notices |
| `interrupt_agent` | Stop an agent's current work without deleting the agent |

Together, these six tools cover subagent creation, communication, and lifecycle management. They are not necessarily exclusive to the main agent: a subagent with the same collaboration capability can communicate with other agents in the tree and even create another level of subagents, subject to each tool's restrictions.

## 1. When the Main Agent Calls `spawn_agent`

Codex has two built-in multi-agent modes:

- **Non-Proactive (`ExplicitRequestOnly`)**: the main agent does not create a subagent proactively unless the user, the project's `AGENTS.md`, or a Skill explicitly requests one;
- **Proactive**: the main agent may look for work that can run in parallel.

In the version analyzed here, setting reasoning effort to `Ultra` selects Proactive mode by default. Other effort levels default to `ExplicitRequestOnly`. Configuration or the model catalog can still provide custom guidance that overrides this default selection.

Proactive does not mean that every complex task creates a subagent. The model may call `spawn_agent` only when both conditions below hold:

1. The task contains a concrete, bounded piece of work that can run independently;
2. The main agent still has other useful work to do, and parallel execution could save time or improve quality.

The final choice still belongs to the model. The runtime creates nothing until the model actually emits a `spawn_agent` call.

### How Many Subagents Can Run at Once?

The current default is four active-agent slots, with the main agent occupying one. The entire agent tree can therefore run at most three subagents at the same time. All levels share this limit; each subagent does not receive three additional slots of its own. Configuration can change the limit.

This limits concurrently active subagents, not the total number created over a conversation. The runtime can unload an idle subagent to free a slot for a new task, so more than three distinct subagents may exist over time. If no slot can be freed, new work receives a capacity error.

## 2. What `spawn_agent` Actually Does

In the Windows example, the model might produce this tool call:

```json
{
  "task_name": "windows_tests",
  "message": "Investigate the Windows test failures and return the relevant files and conclusion.",
  "fork_turns": "all"
}
```

The three arguments name the work, describe the assignment, and choose how much of the main agent's conversation to copy. After receiving the call, the runtime does the following:

```text
validate arguments
  → allocate an address for the subagent
  → create an independent agent conversation
  → copy the requested background
  → deliver message as the first task
  → return a launch result to the main agent
```

### Addresses Make Later Communication Possible

Codex combines `task_name` with the creator's address:

```text
/root + windows_tests → /root/windows_tests
```

The resulting address must be unique within the current agent tree. A successful launch immediately returns something like:

```json
{
  "task_name": "/root/windows_tests",
  "nickname": "Maxwell"
}
```

This is a “started successfully” receipt, not the Windows investigation result. `spawn_agent` does not wait for completion, so the main agent can continue checking Linux immediately.

### What Background the Subagent Receives

The new subagent starts from the main agent's active model, working directory, permissions, and instructions. Codex then applies any settings specific to the subagent. `fork_turns` controls how much existing conversation it sees:

| `fork_turns` | Effect |
| --- | --- |
| Omitted or `all` | Copy the complete sanitized history |
| `none` | Start without parent history |
| A value such as `3` | Copy the last three turns, then sanitize them |

Copying does not mean cloning every internal action. Old reasoning, tool calls, and dynamic guidance specific to the parent are removed so the subagent does not inherit the wrong identity.

The first `message` is not a new system prompt either. It is a task message marked `NEW_TASK`; the subagent's base instructions and project rules still come from the normal prompt-assembly process.

### Why Work Can Begin Concurrently Right After Creation

When `spawn_agent` returns, the subagent's task has been submitted, but it does not have to finish first. Creating the new conversation uses `tokio::spawn` to start its own command-receiving loop. When the first `NEW_TASK` arrives, that loop starts an independent agent turn. Meanwhile, the main agent receives only the launch receipt and can continue its own model-and-tool loop.

The key mechanism is not “one operating-system thread per agent,” but asynchronous tasks scheduled by Tokio. Rust compiles an `async` block into a `Future` that can pause and resume. Tokio's worker threads repeatedly advance these futures. At an `.await`, if a model response, subprocess output, or other result is not ready, the future returns `Pending` and preserves its progress. The worker can then run another ready task. When the awaited data arrives, the task is woken and placed back on the ready queue.

Tokio can therefore advance the subagent while the main agent waits for a model response, and advance the main agent while the subagent waits for I/O. Codex's normal entry point uses Tokio's multi-thread runtime, so two ready tasks may also run at the same time on different operating-system threads. A Tokio task is still a lightweight task rather than an OS thread: creating a subagent does not create a new process or a dedicated thread for it.

```text
main agent turn  ── spawn_agent ── launch receipt ── continue inspecting Linux
                         │
subagent turn            └── receive NEW_TASK ── inspect Windows

Tokio: advance ready tasks; when one waits for I/O, advance another
```

## 3. How to Send a Message to an Existing Subagent

Suppose the main agent has asked `windows_tests` to investigate the Windows tests and later learns that the failure occurs only when a path contains spaces. It can pass along this clue with `send_message`:

```json
{
  "target": "windows_tests",
  "message": "Additional log: the failure occurs only when the path contains spaces."
}
```

### How the Model Finds Active Subagents

Before sending a message, the model must answer two different questions: what is the target subagent's address, and what is it responsible for? Codex provides explicit ways to answer the first question, but it does not maintain a separate, queryable task-description table.

When the main agent creates a subagent, its own conversation history records the `task_name` and `message` from the `spawn_agent` call. The tool result returns the canonical task path and an optional nickname. From that call, for example, the model can tell that `/root/windows_tests` received the assignment “investigate the Windows tests.” As long as those items remain in the current context, the model can associate the address with the responsibility.

Codex also attaches a short subagent list during the information pre-injection stage before an LLM call:

```text
<subagents>
  - windows_tests: Maxwell
</subagents>
```

This list contains only task names and optional nicknames. To inspect the whole agent tree, the model can also call `list_agents` for addresses and statuses, but that tool likewise omits the initial assignments. In other words, `<subagents>` and `list_agents` answer “which agents can be addressed?” They cannot, by themselves, answer “what is each agent responsible for?”

The model must still infer responsibilities from the original `spawn_agent` call in the main agent's current context, later communication, and meaningful task names. If the original assignment is no longer in the current context, the runtime cannot reconstruct the full division of work from the registry or `list_agents` alone. A name such as `windows_tests` is therefore more useful than `worker_1`, but semantic naming only reduces the effect of lost context; it is not a second task record.

### How to Send a Message to a Subagent

Codex offers two similar tools:

| Tool | When to use it | If the subagent is idle |
| --- | --- | --- |
| `send_message` | Add information to work already in progress | Queue the message without starting a turn |
| `followup_task` | Give an existing subagent another assignment | Start a new turn automatically |

After the call, the runtime resolves `windows_tests` to a complete address, finds the corresponding agent conversation, and packages the author, recipient, body, and whether the message should start a turn. The simplified delivery path is:

```text
tool call by the main agent
  → runtime finds the target agent
  → message enters the target Session
  → message is placed in the mailbox
  → message joins the target model's next input at an appropriate time
```

When the message becomes model input, it includes the sender and task address so the subagent knows where it came from:

```text
Message Type: MESSAGE
Task name: /root/windows_tests
Sender: /root
Payload:
Additional log: the failure occurs only when the path contains spaces.
```

## 4. How a Message Safely Reaches a Subagent's Next LLM Call

The previous section showed that `send_message` eventually delivers a message to a target subagent. An LLM call, however, has a fixed input once it has been sent. The runtime cannot insert a later message into a request already in progress. Codex must therefore receive the message safely first, then add it when the next LLM call can be built.

Two new terms are useful here. A Session is the in-memory runtime for one agent conversation. A turn is one round of work currently being handled by that agent. A message passes through three storage layers on its way from the sender to the LLM:

```text
user interface, other agents, and Codex internals
  → Session entry queue
  → submission loop classifies the operation
      └─ agent message → mailbox
                            → current turn's pending input
                            → conversation history
                            → next LLM call
```

The three layers are not redundant queues:

| Layer | What it stores | How read/write conflicts are prevented | Capacity |
| --- | --- | --- | --- |
| Session entry queue | All inbound operations waiting for classification | A concurrency-safe asynchronous channel | 512 items |
| Mailbox | Agent messages waiting to reach the LLM | A first-in, first-out queue protected by a `Mutex` | No explicit limit |
| Current turn's pending input | Input assigned to this turn but not yet recorded in history | The current turn's state lock | No explicit limit |

### Why Can't the Entry Queue Replace the Mailbox?

The entry queue is the common command entrance for the entire Session. In addition to agent messages, it receives these operations:

| Input category | Common examples | What happens after classification |
| --- | --- | --- |
| New or additional work | A new user instruction, input added while work is running, recovery of interrupted work | Start a new turn or join the current turn |
| Agent-to-agent messages | `NEW_TASK`, `MESSAGE`, `FINAL_ANSWER` | Move into the mailbox |
| Replies to pending requests | Command or patch approvals, answers to user questions, permission and external-tool replies | Go to the code waiting for the result |
| Control and maintenance operations | Interrupt, shutdown, context compaction or rollback, code review, settings and configuration updates | Go to their respective handlers |
| Realtime interaction and user commands | Realtime audio or text control, a one-off shell command initiated by the user | Go to the corresponding execution subsystem |

If an agent message remained in the entry queue until the LLM was ready to read it, later interrupts, approvals, and configuration changes would be blocked behind it. The `submission loop` therefore removes and classifies operations promptly. Only agent messages move into the mailbox; all other operations go to their own handlers. The mailbox can preserve unread messages across LLM calls and turns while the entry queue continues accepting new operations.

Model output and tool-execution events use a separate outbound channel. They do not travel backward through this entry queue.

### How Does the Session Entry Queue Handle Concurrent Reads and Writes?

When Codex creates a Session, it uses `async_channel` to create an asynchronous channel with a capacity of 512. The following source is abridged:

```rust
const SUBMISSION_CHANNEL_CAPACITY: usize = 512;

let (tx_sub, rx_sub) =
    async_channel::bounded(SUBMISSION_CHANNEL_CAPACITY);

// Multiple callers can submit operations through the sender.
self.tx_sub.send(sub).await?;

// Only one submission loop owns the receiver and classifies each operation.
while let Ok(sub) = rx_sub.recv().await {
    match sub.op {
        // ...
    }
}
```

Multiple Tokio tasks can call the sender concurrently, and the channel synchronizes those writes internally. They do not mutate a shared ordinary `Vec`. Only one `submission loop` receives from the other end, so operations that have entered the channel are classified in one place rather than being raced over by two dispatch loops. If two sends happen concurrently, the channel establishes the order in which they actually enter the queue; the receiver then reads them in that order.

The 512-item limit applies to operations that have not yet been classified. When the queue is full, the 513th send waits at `.await` until the receiver frees a slot; it does not discard or overwrite an older operation. Once an agent message is removed and transferred to the mailbox, it no longer uses capacity in the entry queue.

### How Does the Mailbox Handle Concurrent Reads and Writes?

The `submission loop` writes messages into the mailbox while a running turn may read them at the same time. A single dispatch loop is not enough to make this safe because the writer and reader are independent Tokio tasks. Codex protects its `VecDeque` with an asynchronous `Mutex`. The abridged code below uses `PendingMailboxCommunication` for an agent message and its turn-start settings:

```rust
struct InputQueue {
    mailbox_pending_mails:
        Mutex<VecDeque<PendingMailboxCommunication>>, // pending messages
}

// The writer acquires the lock and appends at the back.
self.mailbox_pending_mails
    .lock()
    .await
    .push_back(mail);

// The reader acquires the same lock and removes the current batch.
let pending_mails = self.mailbox_pending_mails
    .lock()
    .await
    .drain(..)
    .collect::<Vec<_>>();
```

Only the task holding the lock can modify the queue; another task waits asynchronously without blocking a Tokio operating-system worker thread. Both `push_back` and `drain(..)` finish while the lock is held, so a message cannot be half-read or removed twice by competing readers. `VecDeque` preserves the order in which messages entered the mailbox. If a message arrives just after a drain, it remains queued for the next read rather than being lost.

Messages removed from the mailbox enter the current turn's pending input. That shorter-lived list is also accessed under the turn's state lock: each read obtains one complete batch, while input that arrives afterward remains for the next read.

### Does an Idle Subagent Start Working Immediately After `send_message`?

Normally, no. A message created by `send_message` has `trigger_turn=false`, meaning “add this to the mailbox without starting a turn.” An ordinarily idle subagent has no active turn, so it does not call the LLM again.

The source makes the wake-up condition explicit:

```rust
if trigger_turn || sess.has_outstanding_durable_sleep() {
    sess.maybe_start_turn_for_pending_work_with_sub_id(sub_id)
        .await;
}
```

The second condition is a narrow internal exception. An extension can register a wait that survives across turns even though the agent has no active turn; the source calls this a `durable sleep`. An ordinary message may resume that wait. A normally idle subagent has no such state, so only `trigger_turn=true` starts a new turn.

An idle subagent normally becomes active when it later receives `followup_task`. That message has `trigger_turn=true`. The runtime first uses the active-turn lock to ensure that another turn is not being started concurrently, then drains the whole mailbox and creates a new turn. An earlier message left by `send_message` therefore joins the follow-up task in the new LLM input:

```text
send_message("additional log")      → remains in the mailbox
followup_task("continue the work") → starts a new turn
new turn input                      → additional log + continue the work
```

If the target is already idle and the main agent wants it to begin immediately, it should use `followup_task`. `send_message` is intended to add information to work that is still in progress.

### When Does a Working Subagent Read the Mailbox?

A working subagent does not need another turn to start. Before constructing the next LLM call, the current turn calls `get_pending_input()`, removes the current batch of mailbox messages, records them in conversation history, and builds model input from the updated history.

If a message arrives while the LLM is streaming output, Codex checks the mailbox after a reasoning or commentary item completes. It may end that sample and schedule another LLM call. It does not alter a request that has already been sent, nor does it forcibly cancel a running tool for the new message.

Once the subagent has emitted its final answer for the turn, that turn stops accepting ordinary mailbox messages. A late `send_message` remains queued for a later turn. A follow-up with `trigger_turn=true` starts a new turn after the old one has fully finished. This boundary prevents a completed answer from unexpectedly continuing because a message arrived late.

## 5. How a Completed Subagent Returns Its Result

A subagent does not need to call `send_message` once more before it finishes. When its turn completes or fails, the Session runtime observes the terminal event, collects the final answer or error, and automatically delivers a `FINAL_ANSWER` message to the direct parent:

```text
subagent completes or aborts
  → runtime obtains the final answer or error
  → construct FINAL_ANSWER
  → place it in the parent's mailbox
  → parent reads and combines it
```

For example:

```text
Message Type: FINAL_ANSWER
Task name: /root
Sender: /root/windows_tests
Payload:
The Windows test fails because a temporary-directory path is not quoted. The relevant code is at ...
```

The completion message follows the same delivery path as an ordinary agent message, but it does not unconditionally start a new parent turn. If the parent is still working, the result enters at a safe point. If it is inside `wait_agent`, the activity signal ends the wait promptly. If the parent is already idle, the result remains in the mailbox so a late subagent cannot unexpectedly extend an answer the user has already seen.

## 6. The Whole Process, End to End

Returning to the Windows example:

1. The user's request first enters the main agent, not a subagent.
2. The main model confirms that delegation is allowed and that the Windows investigation can run independently.
3. The model calls `spawn_agent`; the runtime creates `/root/windows_tests`, copies the necessary background, and delivers the first task.
4. The main agent and Windows subagent work concurrently.
5. The main model finds the target through the task name, conversation history, or `list_agents`, then uses `send_message` to add the new log.
6. The submission loop removes the message from the shared entry queue and puts it in the mailbox; before the next LLM call, the subagent records it in conversation history.
7. When the subagent finishes, the runtime automatically returns `FINAL_ANSWER`; the main model combines the findings into an answer for the user.

The most important boundary is now visible. The model understands the work, chooses recipients, and writes instructions. The runtime does not decide who is “best” for a task; it creates conversations by address, schedules them, stores state, and delivers messages reliably.

Seen this way, `spawn_agent` is not mysterious. It simply turns a model's delegation decision into an agent conversation that can work independently, receive more messages, and return its result.

## 7. Source Map

The main text intentionally omits types and functions that do not help explain the mechanism. To verify the implementation in more detail, start with these files pinned to the analyzed commit:

- Mode selection and concurrency limits: [`session/multi_agents.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/session/multi_agents.rs), [`multi_agent_mode_instructions.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/context/multi_agent_mode_instructions.rs), and [`config/mod.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/config/mod.rs);
- Collaboration tool definitions: [`multi_agents_spec.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/tools/handlers/multi_agents_spec.rs);
- Subagent creation and registration: [`multi_agents_v2/spawn.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/tools/handlers/multi_agents_v2/spawn.rs), [`agent/control/spawn.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/agent/control/spawn.rs), and [`agent/registry.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/agent/registry.rs);
- Tokio runtime and agent-turn scheduling: [`arg0/src/lib.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/arg0/src/lib.rs), [`session/mod.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/session/mod.rs), and [`tasks/mod.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/tasks/mod.rs);
- Agent discovery and message handling: [`agent/control.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/agent/control.rs) and [`multi_agents_v2/message_tool.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/tools/handlers/multi_agents_v2/message_tool.rs);
- Message entry, mailbox handling, consumption, and completion delivery: [`session/mod.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/session/mod.rs), [`session/handlers.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/session/handlers.rs), [`session/input_queue.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/session/input_queue.rs), [`state/turn.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/state/turn.rs), [`session/turn.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/session/turn.rs), [`tasks/mod.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/tasks/mod.rs), and [`session_prefix.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/session_prefix.rs).
