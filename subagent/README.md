---
title: "Codex Subagent 如何工作：创建、通信与结果回传"
description: "从一个具体例子出发，解释 Codex 为什么创建 subagent、主 agent 与子代理如何同时工作、消息怎样送达，以及结果如何返回。"
lang: zh
translationKey: codex-subagent-runtime
date: 2026-09-05
tags:
  - Codex
  - Agent Harness
featured: false
---

# Codex Subagent 如何工作：创建、通信与结果回传

这篇文章解释一个 Codex subagent 从创建到结束的完整过程。你会看到主 agent 为什么决定把工作交出去、子代理如何独立执行、双方怎样继续通信，以及结果如何回到主 agent。核心结论很简单：**模型决定“让谁做什么”，Codex 程序负责创建、传递和调度。**

本文的实现分析固定在 OpenAI Codex 仓库的 commit [`8e6a44b`](https://github.com/openai/codex/tree/8e6a44b428e31f91b21edc97904fcdf4f0931ade)（2026-09-04）。

## 先建立一个简单的认识

假设用户让 Codex 调查一个跨平台测试问题。主 agent 决定自己查看 Linux 部分，同时让一个 subagent 专门检查 Windows。这里可以先把三个角色理解成：

- **主 agent**：直接接收用户请求，并负责最后汇总答案；
- **subagent**：由另一个代理创建，负责一项边界明确的工作；
- **runtime**：运行 Codex 的程序，负责真正创建代理、保存状态和传递消息。

整个过程大致是：

```text
用户 → 主 agent → 创建 Windows subagent
              ├─ 主 agent 检查 Linux
              └─ subagent 检查 Windows
                         ↓
                  结果返回主 agent → 用户
```

用户仍然只与主 agent 对话。subagent 并不是另一个聊天窗口，而是 Codex 在同一次任务中创建的独立工作分支。

主 agent 通过一组协作工具来操作这条工作分支：创建 subagent、查看它的状态、发送消息、安排后续任务，以及等待或中断工作。

| 工具 | 用途 |
| --- | --- |
| `spawn_agent` | 创建一个 subagent，并交给它第一项任务 |
| `list_agents` | 查看当前有哪些代理以及它们的状态 |
| `send_message` | 给已有代理补充信息 |
| `followup_task` | 让已有 subagent 开始一项后续任务 |
| `wait_agent` | 等待消息或完成通知 |
| `interrupt_agent` | 停止某个代理当前正在做的事情，但保留该代理 |

这六个工具共同覆盖了 subagent 的创建、通信和生命周期管理。它们也不只属于主 agent：具备相同协作能力的 subagent 可以与树中的其他代理通信，也可以继续创建下一层 subagent；每个工具仍会检查自己的使用限制。

## 1. 主 agent 何时调用 `spawn_agent`

Codex 内置两种 multi-agent 模式：

- **非 Proactive（`ExplicitRequestOnly`）**：除非用户、项目的 `AGENTS.md` 或 Skill 明确要求使用 subagent，否则主 agent 不会主动创建；
- **Proactive**：允许主 agent 主动寻找可以并行处理的工作。

在本文分析的版本中，reasoning effort 设为 `Ultra` 时，默认进入 Proactive 模式；其他 effort 默认使用 `ExplicitRequestOnly`。配置或 model catalog 仍可提供自定义提示，覆盖这个默认选择。

Proactive 并不意味着看到复杂任务就一定创建 subagent。只有同时满足下面两个条件，模型才可能调用 `spawn_agent`：

1. 任务能够拆出一块具体、边界清楚并且可以独立执行的工作；
2. subagent 工作时，主 agent 仍有其他有价值的事情可做，并行处理能够节省时间或提高质量。

最后是否调用仍由模型决定。只有模型真正输出 `spawn_agent` 调用，runtime 才开始创建 subagent。

### 最多能同时运行几个 subagent？

当前默认总共有 4 个同时运行的名额，而且主 agent 也占一个，因此整棵 agent 树同时最多运行 3 个 subagent。这个上限由所有层级共享，不是每个 subagent 都能再创建 3 个；配置可以修改它。

这里限制的是“同时活跃”的数量。runtime 可以卸载已经空闲的 subagent，为新任务腾出槽位，所以一次对话先后创建的 subagent 总数可以超过 3；没有可释放的槽位时，新任务会收到容量错误。

## 2. `spawn_agent` 实际做了什么

沿用 Windows 测试的例子，模型可能生成这样的工具调用：

```json
{
  "task_name": "windows_tests",
  "message": "调查 Windows 测试失败的原因，并返回相关文件和结论。",
  "fork_turns": "all"
}
```

三个参数分别表示：给这项工作起什么名字、交代什么任务，以及复制多少主 agent 的既有对话。runtime 接到调用后会依次完成下面几件事：

```text
检查参数
  → 为 subagent 分配地址
  → 创建一条独立的代理对话
  → 按 fork_turns 复制必要背景
  → 把 message 作为第一项任务送进去
  → 把启动结果返回主 agent
```

### 地址让后续通信找到正确的人

`task_name` 会和创建者的地址拼在一起：

```text
/root + windows_tests → /root/windows_tests
```

这个完整地址在当前代理树中必须唯一。创建成功后，主 agent 会立即得到类似下面的结果：

```json
{
  "task_name": "/root/windows_tests",
  "nickname": "Maxwell"
}
```

这只是“已经启动”的回执，不是 Windows 调查的答案。`spawn_agent` 不等待任务完成，所以主 agent 可以立刻继续检查 Linux。

### subagent 会获得哪些背景

新 subagent 会以主 agent 当前生效的模型、工作目录、权限和指令为基础，再应用专门给 subagent 的设置。`fork_turns` 决定它还能看到多少既有对话：

| `fork_turns` | 效果 |
| --- | --- |
| 省略或 `all` | 复制经过清理的完整历史 |
| `none` | 不复制历史，从空白上下文开始 |
| 例如 `3` | 复制最近三轮，再清理不应继承的内部内容 |

这里的“复制”不是把主 agent 的一切内部过程原样搬过去。旧的推理、工具调用和只属于主 agent 的动态提示会被移除，避免 subagent 混淆自己的身份。

第一项 `message` 也不是新的 system prompt。它是一封标记为 `NEW_TASK` 的任务消息；subagent 自己的基础指令和项目规则仍由正常的提示组装流程提供。

### 创建后为什么可以立刻并行工作

`spawn_agent` 返回时，subagent 的任务已经提交，但不必等它完成。新对话在创建时会通过 `tokio::spawn` 启动自己的指令接收循环；第一封 `NEW_TASK` 到达后，这个循环又会启动一项独立的 agent turn。与此同时，主 agent 只收到“启动成功”的回执，可以继续自己的模型与工具循环。

这背后的关键不是“一个 agent 占用一个操作系统线程”，而是 Tokio 调度的异步任务。Rust 会把一段 `async` 代码编译成可以暂停和恢复的 `Future`。Tokio 的工作线程不断推进这些 Future：运行到 `.await` 时，如果模型响应、子进程输出等结果还没准备好，Future 会返回 `Pending` 并保存当前进度，工作线程便去运行其他已经就绪的任务；等待的数据到达后，任务会被唤醒并重新加入就绪队列。

因此，主 agent 等待一次模型响应时，Tokio 可以推进 subagent；subagent 等待 I/O 时，又可以继续推进主 agent。Codex 的正常入口使用 Tokio 的多线程 runtime，所以两个已经就绪的任务也可能在不同的操作系统线程上真正同时运行。不过 Tokio task 是轻量任务，不等于操作系统线程，也不是每创建一个 subagent 就创建一个新进程或专属线程。

```text
主 agent turn  ── spawn_agent ── 收到启动回执 ── 继续检查 Linux
                         │
subagent turn            └── 接收 NEW_TASK ── 检查 Windows

Tokio：推进就绪的任务；某个任务等待 I/O 时，改去推进另一个任务
```

## 3. 如何给已有 subagent 发消息

假设主 agent 已让 `windows_tests` 调查 Windows 测试，后来发现“失败只发生在路径包含空格时”，便可以调用 `send_message` 补充这条线索：

```json
{
  "target": "windows_tests",
  "message": "补充日志：失败只发生在路径包含空格时。"
}
```

### 模型如何发现活跃的 subagent

发消息前，模型其实要解决两个不同的问题：目标 subagent 的地址是什么，以及它负责什么。Codex 对第一个问题有明确的查询方式，却没有另外维护一份可供查询的“任务说明表”。

主 agent 创建 subagent 时，自己的对话历史会记录 `spawn_agent` 调用中的 `task_name` 和 `message`，工具结果则返回完整任务路径和可选昵称。例如，模型可以从这次调用知道 `/root/windows_tests` 收到的初始任务是“调查 Windows 测试”。只要这些内容仍在当前上下文中，模型就能把地址与职责对应起来。

Codex 还会在 LLM call 之前的信息预注入阶段附上 subagent 简短名单：

```text
<subagents>
  - windows_tests: Maxwell
</subagents>
```

这份列表只包含任务名和可选昵称。需要了解整棵 agent 树时，模型还可以调用 `list_agents` 查看地址和状态，但它同样不会返回初始任务。也就是说，`<subagents>` 和 `list_agents` 解决的是“有哪些可寻址的 agent”，不能单独回答“它们分别负责什么”。

职责仍要从主 agent 当前上下文中的原始 `spawn_agent` 调用、后续通信以及有意义的任务名中判断。如果原始任务已经不在当前上下文中，runtime 不能仅凭注册表或 `list_agents` 恢复完整分工。因此，`windows_tests` 比 `worker_1` 更有用，但语义化命名只是降低信息丢失的影响，并不是另一份任务记录。

### 如何发送消息给 subagent

Codex 提供两个容易混淆的工具：

| 工具 | 适合什么时候用 | subagent 已经空闲时 |
| --- | --- | --- |
| `send_message` | 给正在进行的工作补充信息 | 只把消息排队，不自动开始新一轮 |
| `followup_task` | 让已有 subagent 开始一项后续工作 | 自动开始新一轮 |

调用后，runtime 会把 `windows_tests` 解析成完整地址，找到对应的 agent 对话，再将作者、接收者、正文和“是否启动新一轮”包装成一条内部消息。简化后的传输路径是：

```text
主 agent 的工具调用
  → runtime 找到目标代理
  → 消息进入目标 Session
  → 消息放入 mailbox
  → 在合适的时机加入目标模型的下一次输入
```

进入模型上下文后，消息会带上发送者和任务地址，避免 subagent 不知道它来自哪里：

```text
Message Type: MESSAGE
Task name: /root/windows_tests
Sender: /root
Payload:
补充日志：失败只发生在路径包含空格时。
```

## 4. 一条消息怎样安全地进入 subagent 的下一次 LLM call

上一节讲到，`send_message` 最终会把一条消息投给目标 subagent。但 LLM call 一旦发出，输入就已经确定，runtime 不能把后来到达的消息塞进正在进行的请求。因此 Codex 需要先安全接收消息，再等到合适的时机把它加入下一次 LLM call。

这里会用到两个新概念：Session 是一条 agent 对话在内存中的运行实例；turn 是这个 agent 正在处理的一轮工作。消息从发送者到 LLM 实际经过三层存储：

```text
用户界面、其他 agent、Codex 内部模块
  → Session 入口队列
  → submission loop 分类
      └─ agent 消息 → mailbox
                           → 当前 turn 的待处理输入
                           → 对话历史
                           → 下一次 LLM call
```

这三层并不是重复排队：

| 层次 | 保存什么 | 如何避免读写冲突 | 容量 |
| --- | --- | --- | --- |
| Session 入口队列 | 等待分类的所有入站操作 | 并发安全的异步 channel | 512 项 |
| mailbox | 等待交给 LLM 的 agent 消息 | `Mutex` 保护的先进先出队列 | 没有显式上限 |
| 当前 turn 的待处理输入 | 已经归入本轮、等待写入对话历史的输入 | 当前 turn 的状态锁 | 没有显式上限 |

### 为什么入口队列不能直接替代 mailbox

入口队列是整条 Session 的统一命令入口。除了 agent 消息，它还接收下面这些操作：

| 输入类别 | 常见例子 | 分类后的处理方式 |
| --- | --- | --- |
| 新工作或追加输入 | 用户的新指令、工作中途追加的内容、恢复被中断的工作 | 启动新 turn，或加入当前 turn |
| agent 之间的消息 | `NEW_TASK`、`MESSAGE`、`FINAL_ANSWER` | 转入 mailbox |
| 对等待请求的回复 | 命令或补丁审批、用户问题的答案、权限及外部工具回复 | 交给正在等待结果的代码 |
| 控制和维护操作 | 中断、关闭、压缩或回滚上下文、代码审查、设置与配置更新 | 交给各自的处理逻辑 |
| 实时交互和用户命令 | 实时音频或文本控制、用户发起的一次性 shell 命令 | 交给对应的执行模块 |

如果一条 agent 消息一直占着入口队列，直到 LLM 准备好读取它，后面的中断、审批和配置更新也会被堵住。`submission loop` 因此会先取出并分类操作：只有 agent 消息转入 mailbox，其他操作立即交给各自的处理逻辑。mailbox 负责跨越 LLM call 和 turn 保存未读消息，入口队列则可以继续处理新操作。

模型输出和工具执行事件走另一条输出通道，并不反向进入这条入口队列。

### Session 入口队列怎样处理并发读写

Session 创建时通过 `async_channel` 建立一个容量为 512 的异步 channel。下面是经过删减的代码：

```rust
const SUBMISSION_CHANNEL_CAPACITY: usize = 512;

let (tx_sub, rx_sub) =
    async_channel::bounded(SUBMISSION_CHANNEL_CAPACITY);

// 多个调用者可以通过发送端提交操作。
self.tx_sub.send(sub).await?;

// 只有一个 submission loop 持有接收端并逐条分类。
while let Ok(sub) = rx_sub.recv().await {
    match sub.op {
        // ...
    }
}
```

多个 Tokio task 可以同时调用发送端，channel 自己负责同步写入；它们不需要共同修改一个普通的 `Vec`。接收端则只交给一个 `submission loop`，所以进入 channel 后的操作会由同一个地方依次分类，不会有两个分发循环同时处理同一项。若两个发送恰好同时发生，channel 会确定它们实际进入队列的先后；一旦入队，接收端就按这个顺序读取。

512 限制的是“尚未被分类的操作数”。队列满后，第 513 次发送会在 `.await` 处等待，直到接收端腾出位置，而不是丢弃或覆盖旧操作。一条 agent 消息被取出并转入 mailbox 后，也就不再占用入口队列的容量。

### mailbox 怎样处理并发读写

`submission loop` 负责向 mailbox 写入消息，正在运行的 turn 则可能同时读取消息。这里不能只依赖“单一分发循环”，因为写入和读取发生在两个独立的 Tokio task 中。Codex 因此用异步 `Mutex` 保护 `VecDeque`。下面仍是删减后的核心代码，其中 `PendingMailboxCommunication` 表示一条待处理的 agent 消息及其启动设置：

```rust
struct InputQueue {
    mailbox_pending_mails:
        Mutex<VecDeque<PendingMailboxCommunication>>, // 待处理消息
}

// 写入者取得锁后，把消息放到队尾。
self.mailbox_pending_mails
    .lock()
    .await
    .push_back(mail);

// 读取者取得同一把锁后，一次取走当时的全部消息。
let pending_mails = self.mailbox_pending_mails
    .lock()
    .await
    .drain(..)
    .collect::<Vec<_>>();
```

同一时刻只有拿到锁的一方能够修改队列；另一方会异步等待，不会阻塞 Tokio 的操作系统工作线程。`push_back` 和 `drain(..)` 都在持锁期间完成，所以消息不会被读到一半，也不会被两个读取者重复取走。`VecDeque` 保留进入 mailbox 后的先后顺序；如果新消息恰好在一次 `drain` 之后到达，它会留在队列中，等待下一次读取，而不会丢失。

已经从 mailbox 取出的消息会进入当前 turn 的待处理输入。这个短期列表也受 turn 状态锁保护：读取者每次取得一批完整输入；在此之后才到达的新输入留给下一次读取。

### 空闲的 subagent 收到 `send_message` 后会立刻工作吗

通常不会。`send_message` 创建的消息带有 `trigger_turn=false`，意思是“只加入 mailbox，不启动新的 turn”。一个普通的空闲 subagent 没有 active turn，因此不会重新调用 LLM。

源码中的启动判断如下：

```rust
if trigger_turn || sess.has_outstanding_durable_sleep() {
    sess.maybe_start_turn_for_pending_work_with_sub_id(sub_id)
        .await;
}
```

第二个条件是一个很窄的内部例外：扩展可以让 agent 在没有 active turn 时仍登记一个跨 turn 的等待状态，源码称为 `durable sleep`；普通消息可以恢复这种等待。常规的空闲 subagent 没有这个状态，因此仍然只有 `trigger_turn=true` 才会启动新 turn。

空闲的 subagent 通常会在后来收到 `followup_task` 时重新忙碌。该工具发送的消息带有 `trigger_turn=true`，runtime 会先用 active-turn 锁确认没有另一轮工作正在启动，然后一次取出 mailbox 中的全部消息并创建新 turn。这样，之前由 `send_message` 留下的补充信息也会和新的后续任务一起进入 LLM：

```text
send_message("补充日志")       → 留在 mailbox
followup_task("继续调查")     → 启动新 turn
新 turn 的输入                 → 补充日志 + 继续调查
```

因此，如果目标已经空闲，而主 agent 希望它立即开始工作，应调用 `followup_task`；`send_message` 适合补充一项仍在进行的工作。

### 正在工作的 subagent 何时读取 mailbox

正在工作的 subagent 不需要启动新 turn。当前 turn 会在构建下一次 LLM call 前调用 `get_pending_input()`：先批量取出 mailbox 中的消息，再把它们写入对话历史，随后从更新后的历史构建模型输入。

如果消息在 LLM 流式输出期间到达，Codex 会在一段 reasoning 或 commentary 完成后检查 mailbox，并可结束当前采样、安排下一次 LLM call。它不会修改已经发出的请求，也不会为了新消息强行取消正在运行的工具。

如果 subagent 已经给出本轮最终答案，当前 turn 会停止接收普通 mailbox 消息。迟到的 `send_message` 会留给之后的 turn；带有 `trigger_turn=true` 的后续任务则会在旧 turn 完全结束后启动新 turn。这个边界避免已经完成的答案因为迟到消息突然继续生成。

## 5. subagent 完成后，结果怎样返回

subagent 不需要在结束前再调用一次 `send_message`。当它的一轮工作正常完成或出错时，Session runtime 会观察到结束事件，自动整理状态和最终答案，然后把一封 `FINAL_ANSWER` 消息投递给直接创建它的父代理：

```text
subagent 完成或中止
  → runtime 取得最终答案或错误
  → 构造 FINAL_ANSWER
  → 放入父代理 mailbox
  → 父代理读取并汇总
```

例如：

```text
Message Type: FINAL_ANSWER
Task name: /root
Sender: /root/windows_tests
Payload:
Windows 测试失败是因为临时目录路径没有加引号，相关代码位于……
```

完成消息与普通 agent 消息走同一条传输路径，但不会无条件启动父代理的新一轮。如果父代理仍在工作，结果会在安全位置进入后续输入；如果它正在调用 `wait_agent`，新活动会让等待尽快返回；如果它已经空闲，结果会留在 mailbox，避免在用户已经看到最终回答后又突然续写。

## 6. 把完整过程串起来

现在回到最初的 Windows 例子：

1. 用户的请求先进入主 agent，而不是直接进入某个 subagent。
2. 主模型确认当前规则允许分工，并判断 Windows 调查可以独立进行。
3. 模型调用 `spawn_agent`；runtime 创建 `/root/windows_tests`，复制必要背景并送入第一项任务。
4. 主 agent 与 Windows subagent 并发工作。
5. 主模型从任务名、对话历史或 `list_agents` 找到目标，并用 `send_message` 补充新日志。
6. 入口循环从通用队列取出消息并转入 mailbox；subagent 在下一次 LLM call 前把它写入对话历史。
7. subagent 完成后，runtime 自动把 `FINAL_ANSWER` 送回主 agent；主模型再把各项结论整理成给用户的答案。

这条链路最重要的分界是：模型负责理解任务、选择接收者和撰写指令；runtime 不判断“谁更适合做这件事”，而是负责按地址创建对话、调度执行、保存状态和可靠传递消息。

理解这个分界后，`spawn_agent` 就不再神秘。它只是把模型的一次分工决定，变成一条可以独立工作、继续接收消息并把结果送回来的代理对话。

## 7. 源码索引

正文有意省略了不影响理解的类型和函数细节。想进一步核对实现，可以从这些固定在本文 commit 的文件开始：

- 模式选择与并发上限：[`session/multi_agents.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/session/multi_agents.rs)、[`multi_agent_mode_instructions.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/context/multi_agent_mode_instructions.rs)、[`config/mod.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/config/mod.rs)；
- 协作工具定义：[`multi_agents_spec.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/tools/handlers/multi_agents_spec.rs)；
- subagent 创建与注册：[`multi_agents_v2/spawn.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/tools/handlers/multi_agents_v2/spawn.rs)、[`agent/control/spawn.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/agent/control/spawn.rs)、[`agent/registry.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/agent/registry.rs)；
- Tokio runtime 与 agent turn 调度：[`arg0/src/lib.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/arg0/src/lib.rs)、[`session/mod.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/session/mod.rs)、[`tasks/mod.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/tasks/mod.rs)；
- agent 发现与消息处理：[`agent/control.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/agent/control.rs)、[`multi_agents_v2/message_tool.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/tools/handlers/multi_agents_v2/message_tool.rs)；
- 消息入口、mailbox、消费与完成回传：[`session/mod.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/session/mod.rs)、[`session/handlers.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/session/handlers.rs)、[`session/input_queue.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/session/input_queue.rs)、[`state/turn.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/state/turn.rs)、[`session/turn.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/session/turn.rs)、[`tasks/mod.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/tasks/mod.rs) 和 [`session_prefix.rs`](https://github.com/openai/codex/blob/8e6a44b428e31f91b21edc97904fcdf4f0931ade/codex-rs/core/src/session_prefix.rs)。
