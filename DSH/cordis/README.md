---
title: "Cordis：DSH 如何实现动态组合"
description: 从 Cordis 原始论文出发，理解动态组合的两个核心问题，以及 Revertible Effects、Reactive Coeffects、Context 与 Fiber 如何解决它们。
lang: zh
translationKey: dsh-cordis
date: 2026-08-24
tags:
  - Agent Harness
  - DeepSeek
featured: true
---

# Cordis：DSH 如何实现动态组合

DeepSeek Harness（DSH）把模型、工具、Session、Agent Loop、权限、Sandbox 和 Web UI 都组织成插件。但“所有东西都是插件”只描述了表面结构，真正困难的是：**如何在进程持续运行时改变这些组件，同时让系统仍然保持一致。**

Cordis 的原始论文 [*A Programming Paradigm for Spatiotemporal Composability*](https://github.com/cordiverse/paper/blob/main/paper.pdf) 正面回答了这个问题。

一句话概括：

> Cordis 用可撤销 Effect 管理组件对环境的修改，用响应式 Coeffect 管理组件对环境的依赖，从而让组件可以在不重启整个进程的情况下被添加、移除和替换。

## 1. 为什么要在运行时改变组合


运行时组合让 Harness 不必为了更新一个组件而重启整个进程。它主要带来三个好处：

- **保持连续性**：无关的 Session、连接和后台任务继续运行；
- **缩小影响范围**：只重载目标组件及其依赖子图；
- **支持原地回滚**：新组件失败时撤销其影响并恢复旧版本。

这对自进化 Agent Harness 尤其重要。例如：

```text
Agent 生成并加载 log-analyzer 工具
→ Eval 发现效果不佳
→ Harness 卸载旧插件
→ 加载改进版本并继续当前任务
```

Session checkpoint 可以用于进程重启后的恢复，但不能完全替代运行时组合。Session 事件日志通常能够重建已持久化的消息、已完成的 Step、工具结果和模型上下文，却只能恢复**已经序列化的事实**。正在运行的 Shell、子代理、后台任务、流式响应、连接、文件句柄以及尚未进入日志的插件状态，很难仅靠 Session 无损恢复。

最棘手的是已经开始、结果尚未落盘的外部操作：

```text
Session 写入 tool/call
→ Harness 调用支付或邮件 API
→ 外部操作成功
→ 进程在写入 tool/result 前重启
```

恢复后，日志无法证明外部操作是否完成。重试可能造成重复支付或邮件，跳过又可能漏掉任务；这需要幂等键、事务日志或外部状态核验，单纯 checkpoint 无法解决。

全量重启还会让所有 Session 和无关组件共同承担暂停、冷启动和状态迁移成本。因此两者解决不同问题：Session checkpoint 用于进程失败后的恢复；Cordis 则在局部组件变化时，把重载范围限制在受影响的最小依赖子图内。

## 2. 动态组合有两个正交维度
传统模块关系通常在编译或启动时确定。动态插件系统则必须处理持续变化的运行环境：

- 组件会在运行中出现、消失或被替换；
- 组件已经注册监听器、启动任务、提供 Service 或挂载子组件；
- 其他组件可能正在依赖这些能力；
- 进程还保存着 Session、连接、缓存和未完成任务。

如果旧组件不能完整撤销，残留的工具、监听器和服务绑定会污染后续运行；如果依赖变化不能传播，Consumer 又会继续使用已经失效的 Service。

因此论文研究的不是“怎样导入一个插件”，而是更细粒度的**动态组合**：只改变目标组件，同时正确撤销它的影响，并协调随之变化的依赖关系。
论文把问题拆成两个互不替代的维度：

| 维度 | 核心问题 | Cordis 机制 |
| --- | --- | --- |
| 时间可组合性 | 组件卸载时，能否注销它注册的工具和监听器、停止后台任务并撤销 Service，使系统恢复到加载前的等价状态？ | Revertible Effects |
| 空间可组合性 | 提供 Service 的组件出现、消失或被替换时，依赖它的组件能否按正确顺序自动激活、卸载或重载？ | Reactive Coeffects |

两者必须同时成立。只撤销副作用，却不通知依赖者，会留下正在使用失效服务的组件；只管理依赖，却不能清理定时器、监听器和服务注册，也无法真正卸载组件。

## 3. Revertible Effects：让修改带着逆操作

Effect 表示计算对环境产生的修改，例如：

- 注册事件监听器；
- 启动定时器或文件 watcher；
- 提供一个 Service；
- 挂载子组件；
- 打开连接或占用其他资源。

Cordis 要求这类修改同时给出逆操作：

```text
应用 Effect：环境 A → 环境 B
执行 inverse：环境 B → 环境 A
```

在实现中，这个原语是 `ctx.effect()`：

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

回调执行修改，并返回 disposer。Cordis 记录 disposer；Fiber 卸载时按 LIFO 顺序执行所有 disposer，使后创建的资源先被回收。

这里有一个重要边界：**Cordis 不会证明 disposer 一定正确。** Runtime 负责记录和调用逆操作，但“逆操作能否真的恢复原状态”仍是组件作者的责任。绕过 Context 产生且未被记录的副作用，也不会被自动撤销。

所以时间可组合性的实质不是“框架可以猜出如何清理”，而是：

> 所有会改变共享环境的操作都通过统一入口发生，并在产生修改的位置同时声明恢复方式。

## 4. Reactive Coeffects：让依赖随环境变化

Effect 描述程序如何改变环境；Coeffect 描述程序要求环境提供什么。

在 Cordis 中，Service 是组件通过 Context 对外提供的能力，例如模型调用、日志记录或工具管理。一个组件可以提供 Service，也可以通过 `inject` 声明自己依赖哪些 Service。每当 Context 中可用的 Service 发生变化，运行时都会重新检查组件的依赖是否得到满足：

```ts
export const inject = ['llm']

export function apply(ctx: Context) {
  // 只有 llm 可用时，这个组件才会激活。
  ctx.llm
}
```

每次 Context 变化，Cordis 都会重新判断依赖满足状态，并把变化分为三种：

```text
activating    依赖从不满足变为满足 → 激活组件
deactivating  依赖从满足变为不满足 → 卸载组件
neutral       满足状态没有变化     → 不改变生命周期
```

这比普通依赖注入多了一层“响应式生命周期”。普通 DI 通常在启动时解析对象；Reactive Coeffects 还要处理提供 Service 的组件在运行时消失或被替换。

Cordis 还提供两个作用域机制：

- `isolate()`：让同一个 Service key 在不同 Context 中解析到不同组件提供的实现；
- `intercept()`：不替换提供 Service 的组件，而是改变当前作用域使用它的方式，例如附加权限或配置。

## 5. Context：两个方向的统一边界

论文最关键的一步不是把 Effect 和 Coeffect 并排放置，而是把它们统一进同一个一等 Context：

```text
LLM 组件注册 llm Service
          ↓
Agent 依赖 llm，因此被激活，并注册 agent Service
          ↓
Web Session 依赖 agent，因此被激活
          ↓
LLM 组件被替换，llm 暂时不可用
          ↓
Agent 的依赖不再满足，先卸载并撤销 agent Service
          ↓
Web Session 随之失去 agent，也被卸载
          ↓
新的 LLM 组件提供 llm 后，整条依赖链重新激活
```

因此 DSH 中的 `ctx` 不是普通配置对象，也不只是 Service Locator。它同时承担：

- Effect 的记录边界：记录组件通过当前 Context 创建的监听器、定时器和 Service，组件卸载时统一撤销；
- Coeffect 的解析空间：决定组件能够使用哪些 Service，不同 Context 可以让同名 Service 指向不同实现；
- 当前组件的作用域：标记当前代码属于哪个组件实例，使运行时知道 Effects 和子组件应由谁管理；
- 组件生命周期和子组件关系的入口：提供激活、卸载或重载组件，以及挂载子组件的统一入口。

Context 把“我改变了什么”和“我依赖什么”放在同一个可观察的运行时环境里，这才让两类变化能够自动协调。

## 6. Component 是定义，Fiber 是运行实例

论文区分 Component 和 Fiber：

```text
Component
├─ inject：需要哪些 Coeffects
├─ provide：可能提供哪些 Coeffects
└─ apply：激活时执行哪些 Effects

Component 被安装一次
└─ 产生一个 Fiber
   ├─ 拥有自己的子 Context
   ├─ 保存已解析的依赖视图
   ├─ 记录 Effects 与 disposer
   └─ 维护当前生命周期状态
```

同一个 Component 可以被安装多次，因此可以产生多个互相独立的 Fiber。Fiber 才是能够被激活、卸载、失败和重新加载的运行实体。

常见状态可以简化为：

```text
INACTIVE → LOADING → ACTIVE → UNLOADING → INACTIVE
                       ↘ FAILED
```

提供 Service 的组件被移除时，Cordis 的处理顺序非常关键：

1. 该组件先进入 `UNLOADING`，其 Service 不再被视为可用；
2. 依赖它的 Consumer 发现 Coeffect 不再满足；
3. Consumer 先执行自己的卸载和 Effect 回收；
4. Consumer 卸载完成后，提供 Service 的组件才撤销自己的 Effects。

这样 Consumer 在清理阶段仍能读取原来提交的依赖，不会在 teardown 进行到一半时突然失去 Service。

如果同一个 Service key 改由另一个组件提供，即使新旧值看起来相同，组件身份已经变化，Consumer 也会重新加载。这让“替换组件”成为明确的生命周期事件，而不是悄悄换掉对象引用。

## 参考资料

- Yifan Shi, Wei Zhang, Tianyi Cui, [*A Programming Paradigm for Spatiotemporal Composability*](https://github.com/cordiverse/paper/blob/main/paper.pdf), 2026.
