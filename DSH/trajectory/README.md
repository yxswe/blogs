---
title: DeepSeek Harness：Trajectory、评测与自进化
description: 从 Session 事件流理解 Agent 轨迹，并讨论 DSH 如何从可观察执行走向可靠评测与受控自进化。
lang: zh
translationKey: dsh-trajectory-evolution
date: 2026-08-24
tags:
  - Agent Harness
  - DeepSeek
featured: false
---

# DeepSeek Harness：Trajectory、评测与自进化

> Trajectory 记录 Agent 做了什么，Eval 判断它做得怎么样，自进化则根据判断改变下一次的行为或系统。三者连起来，才是一条完整的改进闭环。

## 1. 三个概念不是同一件事

在 DSH 中，可以先用三个问题区分它们：

| 概念 | 回答的问题 | 主要产物 |
| --- | --- | --- |
| Trajectory | Agent 实际经历了什么？ | 可回放的事件序列 |
| Eval | 这段执行有多好？ | 分数、判定与诊断 |
| 自进化 | 下一次应该改变什么？ | Prompt、工具、策略、插件或模型更新 |

它们理想中的关系是：

```text
执行任务
→ 记录 Trajectory
→ Eval 读取任务、轨迹与结果
→ 定位失败模式
→ 生成候选改动
→ 在隔离环境中重新执行与评测
→ 晋升有效改动，回滚无效改动
```

Trajectory 只是事实，不天然等于质量；Eval 只是判断，不天然会带来改进；修改系统也不天然等于“进化”，只有经过可重复评测和准入控制的改动才构成可靠闭环。

## 2. DSH 一次执行的基本粒度

理解轨迹前，需要区分三个层次：

- **Session**：可持续、可恢复的交互容器，也是事件日志的边界；
- **Turn**：用户发起的一轮工作；
- **Step**：一次模型请求，以及由该次请求产生的工具调用。

一个 Turn 可以包含多个 Step。例如模型先搜索文件，读取结果后再发起下一次模型请求，直到给出答案或停止。

典型过程是：

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
→ ctx.llm 调用模型 Provider
→ assistant/chunk* + assistant/message
→ 执行工具并写入 tool/result
→ 必要时进入下一个 Step
→ step/end
→ turn/end
```

工具执行本身还有一条管线：

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

因此，“模型说了什么”只是轨迹的一部分。真正有诊断价值的轨迹还要包含模型看到了哪些上下文、选择了什么工具、权限是否放行、工具返回了什么，以及状态如何变化。

## 3. Trajectory 是 Session 日志的投影

DSH 的 Session 事件日志是执行事实的权威来源。模型历史、恢复、Fork、Trajectory UI、Telemetry 和持久化都从它派生。

可以把两者理解为：

```text
Session Event Log（事实层）
├─ 对话视图
├─ 模型上下文
├─ Trajectory UI
├─ 恢复与 Fork
└─ Eval 输入
```

这意味着 Trajectory UI 不是独立记录系统，而是对事件流的选择、关联和可视化。若要增加新的诊断信息，首先应判断它是否需要成为可持久化的 Session 事实，而不只是给 UI 临时增加一个字段。

还要避免混淆两类事件：

- **Cordis Event** 用于进程内插件通信和中间件组合；
- **DSH SessionEvent** 用于持久化、回放和重建 Agent 执行。

前者解决运行时解耦，后者解决事实记录。只有进入 Session 日志的信息，才能稳定参与跨进程恢复和离线评测。

## 4. 轨迹必须带上“可行动空间”

同一个模型在不同 preset 下会产生完全不同的轨迹，因为它能看到的工具与服务不同。`standard` preset 通常包含 Shell、文件操作、搜索、后台任务、Skills、Goal、子代理、Workflow 和网络搜索；`minimal`、`code`、`cordis` 则暴露不同的操作界面。

“插件已安装”也不等于“工具已暴露给当前模型”。工具可见性仍取决于 profile、preset、作用域和配置。因此评测一段轨迹时，至少要保留：

| 上下文 | 为什么重要 |
| --- | --- |
| 模型与参数 | 区分能力差异与随机性 |
| System Prompt | 解释行为约束和策略来源 |
| 工具 Schema | 确认模型当时有哪些选择 |
| Profile / Preset | 还原服务和工具组合 |
| 权限与 Sandbox | 区分不会做与不允许做 |
| Token、延迟与外部请求 | 衡量效率和成本 |

例如 DeepSeek 官方搜索会额外发起一次完整的 Messages 模型请求。只统计主 Agent 的 Step，就会低估真实延迟和 Token 成本。

## 5. 当前 Eval 的缺口

DSH 默认运行时目前没有独立 evaluator。Goal 和 Ralph 的完成主要由 Agent 或 worker 自己声明。Snapshot、E2E 与真实 API 测试属于开发验证体系，不等同于对每次 Agent 运行进行独立判断。

这会形成一个关键风险：**执行者同时充当裁判**。Agent 可以认为任务已经完成，但它未必验证了用户真正关心的结果。

更完整的评测至少应包含四层：

1. **结果评测**：最终文件、测试、页面或外部状态是否满足任务；
2. **过程评测**：轨迹是否绕路、重复调用、忽略证据或过早停止；
3. **安全与约束评测**：是否越权、泄露信息或违反审批和 Sandbox 规则；
4. **效率评测**：Token、时间、工具调用和外部 API 成本是否合理。

评测器也不应只输出一个总分。更有用的结果是：

```text
任务是否成功
+ 失败发生在哪个 Step
+ 支撑判断的事件证据
+ 失败类型
+ 建议修改的层次
```

这样才能区分应该改 Prompt、工具描述、权限策略、上下文构造、Agent Loop，还是底层模型。

## 6. 自进化不等于运行时自修改

`cordis` preset 已允许 Agent 检查当前插件树，并临时定义、运行和停止模型编写的插件。这提供了很好的实验面，但动态插件会在进程重启后消失。

因此它更接近“运行时原型实验”，还不是完整的自进化系统。可靠的自进化需要额外的控制面：

```text
观察失败轨迹
→ 提出一个可解释的改动假设
→ 生成候选插件 / Prompt / 配置
→ 在隔离 profile 中运行
→ 对固定任务集与回归集进行评测
→ 比较质量、安全与成本
→ 人工审批或策略准入
→ 发布为正式插件、preset 或 patch
→ 保留版本和回滚能力
```

“写出一个能运行的插件”只完成了生成阶段。没有基线、对照评测、回归集、版本化和回滚，就无法知道系统是在进化，还是只是在漂移。

## 7. 接下来值得追的研究问题

这条线可以继续拆成几个更具体的问题：

1. SessionEvent 的完整 schema 是什么，哪些事件可以稳定重放？
2. Trajectory UI 如何把流式 chunk、tool call 和 step 关联起来？
3. Fork 后哪些事件复用，哪些运行状态会重新生成？
4. 如何定义不依赖 Agent 自我声明的 task-level evaluator？
5. Eval 的证据怎样回指到具体事件，而不是只给一个分数？
6. 动态 Cordis 插件如何进入隔离、评测、晋升和回滚流程？

这六个问题分别对应数据模型、可观测性、实验设计、评测可信度与发布治理。它们比“Agent 能否修改自己”更接近一个可落地的自进化系统。

## 8. 小结

DSH 已经具备构建闭环的两块重要基础：以 Session 事件日志为核心的可回放轨迹，以及通过 Cordis 动态组合能力的机制。当前最明显的缺口位于中间：一个独立、证据驱动、可重复的 Eval 层。

所以合理的演进顺序不是先让 Agent 永久修改自己，而是先让每次执行可还原、可比较、可归因；再用评测结果驱动受控改动。
