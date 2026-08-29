---
title: "DSH 如何基于 Cordis 构建组件化运行时"
description: 以 Web Profile 为例，讲清 DSH 如何通过 bundle 与 patch 组合组件树，以及 Boot 如何借助 Context、Registry、Fiber、Reflect 和 Loader 构建并动态更新运行时。
lang: zh
translationKey: dsh-cordis-architecture
date: 2026-08-24
tags:
  - DeepSeek Harness
  - Cordis
featured: false
---

## 1. DSH 的真正入口：Profile 如何构建组件树

传统应用通常在一个固定的 `main()` 中依次创建数据库、模型客户端、工具和 Web Server。DSH 的命令行入口只做更少、也更关键的一件事：找到用户选择的 **Profile**，把它声明的配置层合并成一棵 Cordis 组件树，再交给 Loader 启动。

以自带的 Web 版本为例，下面两条命令是同一个意思：

```sh
dsh web
dsh --profile web
```

第一次运行时，DSH 会自动初始化 `$DSH_HOME/profiles/web`。实际目录一开始很小：

```text
$DSH_HOME/profiles/web/
├── package.json          # Profile 清单：依赖与有序的 bundle 列表
├── cordis.patch.yml      # 这个 Profile 自己的组件树补丁
├── pnpm-workspace.yaml   # 外部组件的 pnpm 安装规则
└── cordis.yml            # 启动时生成的空根节点，不要手工编辑
```

### 1.1 `package.json`：决定“有哪些代码可用”和“加载哪些 bundle”

要读懂这份文件，先区分普通组件与 bundle：

- **普通组件**是组件树中的一个可运行单元，通常以独立的 npm 包交付。
- **Bundle** 是多个组件的组合包，通过**组合包自身的** `cordis.patch.yml` 描述这组组件如何加入组件树，`@deepseek-ai/dsh-web-app` 就是一个例子。Bundle 本身不是运行时组件，最终运行的仍是它贡献的各个组件行。

在 Profile 层，`dependencies` 记录安装的外部包，`dsh.profile.bundles` 则按顺序列出要应用的 bundle。自带 Web Profile 的初始清单如下：

```json
{
  "name": "dsh-profile-web",
  "private": true,
  "dependencies": {},
  "dsh": {
    "profile": {
      "bundles": [
        "@deepseek-ai/dsh-base",
        "@deepseek-ai/dsh-web-app"
      ]
    }
  }
}
```

这两个 bundle 随 DSH 发布，因此 `dependencies` 初始为空。DSH 先应用 `dsh-base`，提供 Agent、Session、LLM、Tools、持久化与 Sandbox 等共享能力；再应用 `dsh-web-app`，加入 Host API、HTTP Server 和浏览器端组件。后面的 bundle 可以使用相同的行 `id` 覆盖前面的配置。

以 `dsh-web-app` 为例，一个 bundle 的核心目录结构如下：

```text
packages/bundle/web-app/
├── package.json          # 声明 dsh.bundle.patch 和组件依赖
├── cordis.patch.yml      # bundle 自身的组件树 patch
└── src/                  # bundle 自带的组件源码
```

`package.json` 中的 `dsh.bundle.patch` 指向同包内的 `cordis.patch.yml`。这个文件定义 bundle 默认带来的组件，与用户用于添加或覆盖内容的 `$DSH_HOME/profiles/web/cordis.patch.yml` 不是同一个文件。

### 1.2 `cordis.patch.yml`：组合 `cordis.yml` 下的组件树

`cordis.yml` 是一个空根节点，`cordis.patch.yml` 则描述要挂在这个根节点下的组件子树。Web Profile 会依次应用这些 patch：

```text
dsh-base 的 cordis.patch.yml
          ↓
dsh-web-app 的 cordis.patch.yml
          ↓
$DSH_HOME/profiles/web/cordis.patch.yml
          ↓
$DSH_HOME/cordis.patch.yml
          ↓
命令行中的 --patch（如果有）
          ↓
cordis.yml 下的最终组件树
```

每个 patch 都可以插入新组件行，也可以用相同的 `id` 修改或禁用已有行。越靠后的 patch 优先级越高，因此 `dsh-web-app` 可以覆盖 `dsh-base`，Profile patch 又可以覆盖所有 bundle。覆盖 `config` 时会替换整块配置，而不是深度合并字段。

可以在不启动 Web 服务的情况下查看最终结果：

```sh
dsh --profile web --dump-config
```

### 1.3 引入组件的两种方式

一个组件真正运行要经过三个阶段：

| 阶段 | 含义 |
| --- | --- |
| 安装 | 组件包已经可被解析。外部包会进入 Profile `package.json` 的 `dependencies`；内置包则随 DSH 提供。 |
| 注册 | 某个 patch 让组件成为最终组件树中的一行。Patch 只负责决定“树里有没有它”。 |
| 激活 | Loader 导入组件并创建 Fiber；Cordis 等它依赖的 Service 就绪后再激活 Fiber。 |

因此，已经安装但没有注册的组件不会运行；已经注册但依赖尚未满足的组件也只会等待。

#### 方式一：直接引入一个组件

单个组件对应组件树中的一个实例。以 DSH 自带但默认不激活的 MCP Client 为例，它已经能从 DSH 安装中解析，因此不需要先执行安装命令。要连接一个 MCP Server，只需编辑 `$DSH_HOME/profiles/web/cordis.patch.yml`：

```yaml
- insert:
    - id: mcp-docs
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: docs
        transport: streamable-http
        url: https://example.com/mcp
```

`id` 是这个实例在组件树中的稳定身份，`name` 是要导入的组件包，`config` 是传给该实例的配置。MCP Client 依赖 `ctx.tools`；Loader 会等 `dsh-base` 提供 Tools Service 后再激活它，然后它才把远端工具注册到 `ctx.tools`。

一个外部组件包的典型目录结构很简单：

```text
my-dsh-component/
├── package.json          # 包名、运行入口和依赖
├── src/index.ts          # 组件源码
└── lib/index.js          # 构建后供 DSH 加载的入口
```

要把这样的外部组件加入 Web Profile，先安装它：

```sh
dsh plugin --profile web add <component-package>
```

这一步只负责把包加入 `dependencies` 并安装到 Profile。若该包不是 bundle，CLI 会提醒它目前只是普通依赖；随后仍要像上面的 MCP 示例一样，在 `cordis.patch.yml` 中用 `insert` 注册一个实例。也就是说：**安装解决模块解析，patch 解决进入组件树。**

#### 方式二：通过 bundle 引入一组组件

Bundle 不是另一种运行时组件，而是“预先写好的一组组件树 patch”的 npm 包。它适合一次带来多个相互配合的组件、默认配置和覆盖项。一个 bundle 在自己的 `package.json` 中声明：

```json
{
  "dsh": {
    "bundle": {
      "patch": "./cordis.patch.yml"
    }
  }
}
```

其中的 `cordis.patch.yml` 可以插入许多组件行，也可以覆盖更早 bundle 提供的行。安装外部 bundle 仍使用同一个命令：

```sh
dsh plugin --profile web add <bundle-package>
```

不同之处在于，CLI 安装后会识别 `dsh.bundle` 声明，并自动把真实包名追加到 Web Profile 的 `dsh.profile.bundles`。于是一次操作同时完成两件事：包进入 `dependencies`，它的 patch 也成为组件树的一个配置层。以后运行 `dsh web` 时，该层会在 `dsh-web-app` 之后、用户自己的 `cordis.patch.yml` 之前应用。

### 1.4 一个组件单元怎么写

第一种是 DSH 中最常见的具名导出写法，元数据和入口函数放在同一个模块中：

```ts
export const name = 'greeter-consumer'
export const inject = ['greeter']
export const Config = z.object({ who: z.string().required() })

export function apply(ctx: Context, config: { who: string }) {
  ctx.logger.info(ctx.greeter.greet(config.who))
}
```

`name` 是组件名，`inject` 声明依赖的 Service，`Config` 定义配置 Schema，`apply(ctx, config)` 是入口执行函数。这个模块没有默认导出，Loader 会把它整体作为一个带 `apply` 的对象组件。

这些元数据并非对象组件专属。第二种写法默认导出函数，可以通过 `Object.assign()` 把 `inject` 和 `Config` 挂到函数对象上：

```ts
const greetingPrinter = Object.assign(
  async function greetingPrinter(ctx: Context, config: { who: string }) {
    ctx.logger.info(ctx.greeter.greet(config.who))
  },
  {
    inject: ['greeter'],
    Config: z.object({ who: z.string().required() }),
  },
)

export default greetingPrinter
```

函数本身是入口，函数名 `greetingPrinter` 是默认的组件名；Registry 还能直接从这个函数对象读取 `inject` 和 `Config`。

第三种写法默认导出类，元数据写成静态字段：

```ts
export default class Heartbeat {
  static inject = ['timer']
  static Config = z.object({ interval: z.number().min(100).required() })

  constructor(ctx: Context, config: { interval: number }) {
    ctx.interval(() => ctx.logger.info('tick'), config.interval)
  }
}
```

类本身是入口，类名 `Heartbeat` 是默认的组件名；Registry 从类的静态属性读取 `inject` 和 `Config`，Fiber 则通过 `new Heartbeat(ctx, config)` 创建实例。`name`、`inject` 和 `Config` 都是可选元数据：没有 `inject` 表示不等待额外 Service，没有 `Config` 表示不使用 Schema 处理配置。无论采用哪种写法，Loader 最终交给 Registry 的都必须是函数、类或带 `apply` 函数的对象。

## 2. Boot 如何从 Profile 构建运行时 Context

第 1 章得到的只是最终组件行；Boot 还要把这些静态描述变成真正运行的组件实例。理解这一步，关键是先弄清楚所有组件都会收到的 `ctx`。

### 2.1 Context（`ctx`）到底是什么

`ctx` 的本质是 Cordis 的运行时容器。它以 `Proxy` 为统一入口，负责解析 Service、管理组件注册、分发事件并记录 Effect，让这些能力都可以通过同一个对象访问。

`new Context()` 首先创建 Root Context。之后每注册一个组件实例，Cordis 都会为它创建一个 Fiber，并从父 Context 派生出绑定该 Fiber 的子 Context。子 Context 继承父 Context 的基础能力，组件通过它访问当前作用域内的 Service；组件注册的 Effect 则归对应 Fiber 管理。

#### 基础成员与 Context 自身方法

Root Context 直接保存基础成员；子 Context 通过原型链继承它们，并用自己的 `fiber`、`baseUrl` 或作用域信息覆盖父级值。

| 成员 | 含义 |
| --- | --- |
| `ctx.root` | 始终指向 Root Context；只有根节点满足 `ctx.root === ctx`。 |
| `ctx.baseUrl` | 相对模块与文件路径的解析基准。Root Context 初始为 `undefined`，子 Context 默认继承父级。 |
| `ctx.fiber` | 拥有当前 Context 的 Fiber。Root Context 对应 `uid` 为 `0` 的 Root Fiber；组件的子 Context 对应该组件实例的 Fiber。 |
| `ctx.reflect` | `Proxy` 背后的 Service 注册与解析层。 |
| `ctx.registry` | 组件注册表，保存组件 Runtime，并负责创建 Fiber。 |
| `ctx.events` | 事件总线。 |
| `ctx.logger` | 日志服务。`ctx.logger('name')` 创建具名 Logger，`ctx.logger.info()` 直接记录日志。 |
| `ctx[Context.isolate]`、`ctx[Context.intercept]` | 两个以 Symbol 为键的底层映射，分别记录 Service 隔离作用域与拦截配置。 |

这些成员都出现在 `Context` 的类型声明中。`Context` 自己还定义了三个公开方法：

| 方法 | 含义 |
| --- | --- |
| `extend(meta)` | 创建一个继承当前 Context 的子 Context，并添加局部信息。 |
| `isolate(name, label?)` | 派生一个子 Context，为指定 Service 建立独立作用域。 |
| `intercept(name, config)` | 派生一个子 Context，为指定 Service 添加只影响后代的配置。 |

#### 快捷属性与方法

为了避免每次都写 `ctx.reflect.get()`、`ctx.registry.plugin()`，Cordis 在初始化时调用 `mixin()`，把几个基础对象的成员映射到 `ctx` 顶层。它们不是复制出来的新实现；`Proxy` 会把调用转发给当前 Context 对应的基础对象。

| 基础成员 | 映射到 `ctx` 的快捷入口 |
| --- | --- |
| `ctx.reflect` | `get()`、`set()`、`provide()`、`accessor()`、`mixin()` |
| `ctx.fiber` | `runtime`、`effect()` |
| `ctx.registry` | `inject()`、`plugin()` |
| `ctx.events` | `on()`、`once()`、`parallel()`、`emit()`、`serial()`、`bail()`、`waterfall()` |

### 2.2 Registry：把组件代码变成 Fiber

Registry 可以分成两层理解：Runtime 记录“这是什么组件”，Fiber 代表“这个组件的一次运行实例”。

`new Context()` 创建的 Registry 起初没有任何记录。每次调用 `ctx.plugin(component, config)`，Registry 都会依次完成三件事：

1. 从 `component` 中取出入口执行函数，内部称为 `callback`。函数组件和类组件以自身作为 `callback`，对象组件则使用它的 `apply` 函数。
2. 以 `callback` 的函数引用作为 key 查找 Runtime；找不到时才创建。Runtime 保存组件名称、入口函数 `callback`、配置 Schema，以及该组件的所有 Fiber。
3. 为本次调用创建一个新 Fiber，保存本次传入的 `config` 和生命周期状态。

所有 Context 共享同一个底层 Registry。Registry 负责按入口函数索引 Runtime 和 Fiber：

```text
所有 Context ──→ 同一个 Registry
                  └── callback: Greeter
                      └── Runtime
                          ├── name / callback / Config schema
                          └── fibers
                              ├── Fiber A
                              └── Fiber B
```

这里的 key 是函数引用，不是组件名、包名或组件行的 `id`。

`ctx.inject(deps, callback)` 是在组件代码中临时挂载一段依赖逻辑的快捷方法。它不会创建带有 `id`、包名和配置的组件行，也不会写入 `cordis.yml`；内部只是构造 `{ inject: deps, apply: callback, name: callback.name }` 这个内存中的组件定义，再交给 `ctx.plugin()`。因此它同样会创建子 Fiber，并由 Fiber 管理依赖变化和卸载。

因此，Registry 解决的是：**这段组件代码是否已经登记，以及这次注册要创建哪个 Fiber？**

### 2.3 Fiber：管理一个组件实例的生命周期

从代码结构看，一个组件 Fiber 的主要字段如下：

| 成员 | 保存的内容 |
| --- | --- |
| `uid`、`name` | Registry 分配的实例编号，以及从 Runtime 或祖先继承的显示名称；Root Fiber 的 `uid` 为 `0`，销毁后变为 `null` |
| `parent` | 创建当前 Fiber 时所使用的 Parent Context，通过 `parent.fiber` 可以找到父 Fiber |
| `ctx` | 当前 Fiber 对应的 Context |
| `runtime` | 该实例所属的 Runtime，包含组件入口和配置 Schema；Root Fiber 的值为 `null` |
| `inject` | 组件声明的 Service 依赖表 |
| `config` | 本次激活所使用的、经过校验和处理的组件配置 |
| `store` | 保存本轮运行绑定的 Service；卸载完成后变为 `undefined` |
| `state` | 当前生命周期状态 |
| `inertia` | 当前正在进行的加载或卸载任务；状态稳定时为 `undefined` |
| `dispose` | 卸载并永久移除这个组件实例 |

Fiber 会在下面几个状态之间变化：

```text
PENDING（等待 Service）
    ↓
LOADING（执行组件代码）
    ↓
ACTIVE（组件正在运行）
    ↓
UNLOADING（执行清理）
    ↓
DISPOSED
```

Fiber 最核心的方法是 `effect()`，组件通常通过快捷入口 `ctx.effect()` 调用它。这正是 Cordis 中 **Revertible Effects** 的具体实现：执行一项会改变外部状态的操作时，同时提供撤销这项操作的清理函数。

```ts
function apply(ctx: Context) {
  ctx.effect(() => {
    const timer = setInterval(work, 1000)
    return () => clearInterval(timer)
  }, 'work-timer')
}
```

传给 `effect()` 的函数会立即执行，返回的清理函数则由当前 Fiber 保存。组件卸载、重启或被移除时，Fiber 会自动执行清理；也可以调用 `effect()` 的返回值提前清理。`ctx.provide()`、`ctx.on()` 和 `ctx.plugin()` 建立的注册也采用这套机制，因此都会随所属 Fiber 一起撤销。

Fiber 还提供一些生命周期辅助方法：`getEffects()` 用于查看已登记的 Effect，`await()` 用于等待加载或卸载完成，`restart()` 和 `update()` 用于重新激活组件，`dispose()` 用于永久移除实例，`assertActive()` 用于确认实例尚未销毁。

除 Root Fiber 外，每个组件 Fiber 都由 `parentCtx.plugin(component, config)` 构造，同时得到一个与它对应的 Context。如果组件继续通过自己的 Context 调用 `ctx.plugin()`，新 Fiber 就会成为它的子节点。因此，组件树在内存中对应一棵由 Fiber 与 Context 共同组成的运行时树：

```text
Root Fiber ── Root Context
├── Fiber A ── Context A
│   └── Fiber C ── Context C
└── Fiber B ── Context B
```

子 Fiber 的构造函数通过下面的方式，把自己的销毁流程挂到父 Fiber 上。简化后的代码如下：

```ts
childFiber.dispose = parentFiber.effect(() => {
  return async () => {
    // 从 Runtime 中移除并卸载 childFiber
  }
}, 'ctx.plugin()')
```

`parentFiber.effect()` 会生成一个 `dispose` 包装函数。父 Fiber 把它保存在自己的 `_disposables` 清理列表中，子 Fiber 则把同一个函数保存为 `childFiber.dispose`。

因此有两个入口可以触发同一套销毁流程：主动调用 `childFiber.dispose()`，或者卸载父 Fiber。父 Fiber 卸载时会依次执行清理列表中的包装函数，于是子 Fiber 被卸载；子 Fiber 的清理列表中又保存着下一层子 Fiber 的包装函数，所以最终会递归卸载整棵子树。

因此，Fiber 解决的是：**这个组件实例何时运行、依赖谁，以及卸载时要清理什么？**

### 2.4 Reflect：组件如何提供和依赖 Service

在 Cordis 中，一个组件不能直接依赖另一个组件或它的 Fiber。`ctx.plugin()` 只会把组件注册到 Registry 并创建 Fiber；组件还需要在入口执行时调用 `ctx.provide()`，才能把某项能力作为 Service 提供出来。另一个组件的 `inject` 声明依赖的正是这个 Service 名称。

一棵组件树只有一份底层 Reflect。Root Context 创建它以后，所有子 Context 都继续使用其中的 `props` 和 `store`：

```text
Root Context ─────┐
Child Context A ──┼──→ 同一个 Reflect
Child Context B ──┘     ├── props
                        └── store
```

两张表的分工如下：

| 记录 | 保存什么 | key | 是否区分 Service 作用域 |
| --- | --- | --- | --- |
| `props` | 属性的解析规则，例如 Service 或 accessor | 属性名，例如 `greeter` | 否，整棵树共享一条属性定义 |
| `store` | Service 的实际实现 `Impl`，包括 `value` 和所属 Fiber | 一个 Symbol | 是，同名 Service 可以在不同作用域中有不同实现 |

`props.greeter = { type: 'service' }` 只告诉 Proxy：“读取 `ctx.greeter` 时，应该把它当作 Service 处理。”真正返回哪个对象，还要去 `store` 查找。

#### Service 隔离：让同名 Service 使用不同实现

Service 的实现保存在 `reflect.store` 中，但它的 key 不是 Service 名称，而是记录在 `ctx[Context.isolate]` 中的 Symbol：

```text
ctx[Context.isolate].greeter → Symbol A
reflect.store[Symbol A]      → greeter 的实现
```

之所以多出这层映射，是为了让不同 Context 可以为同名 Service 使用不同实现。普通子 Context 派生时会继承 Parent Context 的映射，所以两者查询 `greeter` 时使用同一个 Symbol，也就找到同一个实现。

通过 `isolate()` 派生时，Cordis 会为子 Context 创建一层新映射，并只给指定的 Service 换一个 Symbol：

```ts
const child = ctx.isolate('greeter')
```

```text
Parent Context：greeter → Symbol A
Child Context： greeter → Symbol C
```

Parent Context 不会被修改，其他 Service 仍然继承 Parent Context 的 Symbol。此后，Parent Context 下的组件通过 `Symbol A` 查找 `greeter`，Child Context 下的组件则通过 `Symbol C` 查找，因此两边可以分别注册和使用自己的 `greeter` 实现。`isolate()` 只改变查找所用的 Symbol，本身不会注册 Service。

#### `provide` 注册 Service 的详细过程

下面的 `greeterComponent` 是一个普通组件，它在入口中提供名为 `greeter` 的 Service：

```ts
const greeterComponent = {
  name: 'greeter-component',
  apply(ctx: Context) {
    const greeterService = {
      greet: (who: string) => `Hello, ${who}!`,
    }
    ctx.provide('greeter', greeterService)
  },
}
```

这里的 `ctx` 是创建 `greeterComponent` 对应的 Fiber 时，从 Parent Context 派生出的专属 Context；`greeterService` 是要提供的具体对象。`ctx.provide()` 是 `ctx.reflect.provide()` 的快捷方式，内部依次完成以下操作：

1. 在 `props` 中把 `greeter` 标记为 Service。
2. 确保 Root Context 中存在 `greeter` 的默认 Symbol。
3. 从当前 Context 的“门牌表”取得 `greeter` 实际使用的 Symbol；如果当前 Context 隔离过 `greeter`，这里取得的就是隔离后的 Symbol。
4. 创建包含 Service 名称、实际对象和所属 Fiber 的 `Impl`。
5. 把注册过程包装成当前 Fiber 的 Effect，使 Fiber 卸载时自动删除 Service。

最终形成下面的结构：

```text
ctx.reflect.props.greeter = { type: "service" }

Impl
├── name: "greeter"
├── value: greeterService
└── fiber: greeterComponent 对应的 Fiber

当前 Context 的门牌表
└── greeter ──→ Symbol A

同一个 Impl 可以被多处引用
├── ctx.reflect.store[Symbol A] ──→ Impl
├── greeterComponent 对应的 Fiber.store.greeter ──→ Impl
└── 成功解析该实现的各个 Consumer Fiber.store.greeter ──→ Impl
```

`provide()` 执行时会先把 `Impl` 放入 `reflect.store` 和提供者自己的 `Fiber.store`；Consumer 解析 `inject` 时，从 `reflect.store` 取出同一个 `Impl`，并在激活时放入自己的 `Fiber.store`。因此提供者和 Consumer 都可以通过各自的 `ctx.greeter` 访问同一个 `Impl.value`。Service 的生命周期所有者由 `Impl.fiber` 记录。

如果 `greeterComponent` 只创建了 Fiber，却没有调用 `provide()`，Reflect 中就不会出现 `greeter`，依赖它的 Fiber 会停在 `PENDING`。`greeterComponent` 仍然可以监听事件或启动定时器，只是不能被其他组件通过 `inject` 依赖。`greeterComponent` 对应的 Fiber 卸载时，`provide()` 对应的 Effect 还会自动删除 Service，并让依赖它的 Fiber 回到等待状态。

#### Reflect 的其他快捷方法

除了 `provide()`，Reflect 还提供四个相关方法：

| 快捷方法 | 能力 | 背后的机制 |
| --- | --- | --- |
| `ctx.get(name)` | 探测一个可选 Service | 根据当前 Context 的隔离作用域在 `store` 中查找，默认只返回已激活的实现 |
| `ctx.set(name, value)` | 更新 Service 的实现值 | 找到当前作用域中的记录；只有提供该 Service 的 Fiber 才能修改 |
| `ctx.accessor(name, hooks)` | 给 `ctx` 增加一个按需读取的属性 | 读取 `ctx[name]` 时调用传入的 `get`；写入时调用可选的 `set` |
| `ctx.mixin(source, keys)` | 把 Service 的方法直接暴露在 `ctx` 上，添加快捷方式 | 例如 `ctx.mixin('timer', ['setTimeout'])` 让 `ctx.setTimeout()` 转发到 `ctx.timer.setTimeout()` |

两者的区别是：`accessor()` 由组件自己编写单个属性的读取和写入逻辑；`mixin()` 则在内部为多个成员批量创建这样的 accessor。它们都只在 `props` 中登记访问规则，不会向 `reflect.store` 注册 Service。

`provide()` 和这四个方法都没有复制到 Context 对象上。Reflect 初始化时调用 `mixin('reflect', ...)`，在 `props` 中为它们创建 accessor；读取 `ctx.get` 时，外层 Proxy 会把调用转发给当前 Context 的 `ctx.reflect.get`。`runtime`、`plugin` 和 `on` 等快捷入口也使用相同机制，分别转发到 Fiber、Registry 和 Events。初始化完成后，`props` 中已有 16 个快捷入口，而 `store` 仍为空；以后调用 `provide()` 或 `accessor()` 时，`props` 才会继续增加记录。

因此，Reflect 解决的是：**当前作用域中哪个 Service 实现可用，如何通过 `ctx` 访问它，以及依赖它的 Fiber 何时运行？**

### 2.5 Events：组件如何发送和监听事件

一棵组件树共享同一个 Events，内部的监听表以事件名为 key，以监听器数组为 value：

```text
Events
└── "greeter/used"
    ├── { ctx: Context A, callback: listenerA }
    └── { ctx: Context B, callback: listenerB }
```

调用 `ctx.on('greeter/used', callback)` 时，Cordis 会在对应数组中加入一条记录，其中包含回调和当前 Context。保存 Context 是为了在发送带有作用域目标的事件时过滤监听器；这项注册同时归当前 Fiber 管理，组件卸载时会自动移除。`ctx.on()` 返回的函数也可以提前取消监听。

调用 `ctx.emit('greeter/used', 'DSH')` 时，Events 使用同一个事件名找到数组，完成作用域过滤后，将 `'DSH'` 依次传给留下的回调。事件没有监听器时，调用不会产生效果。

```ts
ctx.on('greeter/used', (who) => {
  ctx.logger.info(`greeted ${who}`)
})

ctx.emit('greeter/used', 'DSH')
```

不同发送方法决定监听器怎样执行：

| 方法 | 执行方式 |
| --- | --- |
| `emit()` | 同步调用全部监听器，不等待 Promise。 |
| `parallel()` | 并发调用全部监听器并等待完成。 |
| `serial()` | 依次等待，遇到第一个有效返回值时停止。 |
| `bail()` | `serial()` 的同步版本。 |
| `waterfall()` | 监听器通过 `next()` 包裹后续处理，也可以不调用 `next()` 来截断。 |

### 2.6 Boot 如何建立并更新组件树

`runProfile()` 会先读取 Profile 的 `package.json`，按顺序收集 bundle patch、Profile patch、全局用户 patch 和命令行覆盖层。随后 `boot()` 创建 Root Context，启动过程才正式进入 Cordis。

#### Root Context 创建后的默认行为

1. `new Context()` 创建 Root Fiber，以及 `reflect`、`registry`、`events`、`logger` 四项基础能力。
2. `boot()` 设置组件包的解析基准 `baseUrl`，然后调用 `ctx.provide('dshHomePath', dshHomePath)`，将路径生成函数 `dshHomePath` 注册为 Root Context 上的第一个 Service。例如，`dshHomePath('sessions')` 会返回 `$DSH_HOME/sessions` 的绝对路径，Loader 解析配置中的 `!!js` 表达式时也可以使用它。
3. DSH 把代码中静态导入的 Loader 作为第一个组件交给 `ctx.plugin()`。Loader 不能依赖尚未建立的组件树来加载自己，所以必须先由 Boot 直接启动。Registry 此时创建第一条 Runtime 和对应的 Fiber；Loader 激活后提供 `ctx.loader` Service。

#### Loader 如何加载整棵组件树

DSH 每次启动都会把 Profile 下的 `cordis.yml` 写成空数组 `[]`。它只用来确定 Profile 目录和模块解析位置，真正的组件行来自各层 `cordis.patch.yml`：

```text
空的 cordis.yml
        +
bundle patches → Profile patch → $DSH_HOME/cordis.patch.yml → --patch 等覆盖层
        ↓
Include 组合出最终组件行
        ↓
Loader 为每行创建 Entry 和 entry.ctx
        ↓
按 name 导入组件包
        ↓
entry.ctx.registry.plugin(component, config)
        ↓
创建 Fiber；inject 满足后激活组件
```

Loader 就绪后，Boot 先登记 `cordis:include` 和 `cordis:group` 两个内置组件，再创建一个固定 `id` 为 `include` 的根组件行。Include 读取 `cordis.yml`、按顺序应用所有 patch，并把最终组件行交给 Loader 的 Entry Tree。

最终形成的 Context 层次大致如下：

```text
Root Context
└── Loader Context
    └── Include Context
        ├── 组件行 A 的 Context
        ├── 组件行 B 的 Context
        └── Group Context
            ├── 子组件行 C 的 Context
            └── 子组件行 D 的 Context
```

#### `cordis.patch.yml` 如何触发运行时更新

初次启动成功后，`runProfile()` 会确保 `timer` 和 `hmr` Service 可用，再通过 HMR 分别监听：

- `$DSH_HOME/profiles/web/cordis.patch.yml`
- `$DSH_HOME/cordis.patch.yml`

HMR 会监听文件的创建、修改和删除。任一文件发生变化时，DSH 都会重新读取这两个用户 patch，再与原有的 bundle patch 和启动覆盖层重新组合，最后把新的完整 patch 列表交给根 Include：

```text
patch 文件变化
        ↓
重新读取两个用户 patch
        ↓
重新组合全部 patch 层
        ↓
更新根 Include
        ↓
Loader 按 id 对比新旧 Entry Tree
        ↓
创建、更新、替换或删除对应 Fiber
```

| 组件行变化 | Loader 的处理 |
| --- | --- |
| 增加新 `id` | 导入组件并创建新的 Fiber。 |
| 删除一行或设为 `disabled` | 销毁对应 Fiber，并撤销它拥有的 Effect。 |
| `id` 不变，只修改 `config` | 更新原 Fiber 的配置，并重新激活组件。 |
| 修改 `name`、`inject` 或分组 | 销毁旧 Fiber，再用新定义创建 Fiber。 |

这次更新按事务处理。如果新组件树应用失败，Loader 会尽量恢复上一次成功的组件树，HMR 则记录错误并发送 `hmr/config-update-failed`。替换 Service 提供方时，依赖它的 Fiber 会在旧实现消失后进入等待，并在新实现可用后重新激活。

因此，修改这两个被监听的用户 `cordis.patch.yml` 不需要重启 DSH。Profile 的 `package.json`、bundle 清单、bundle 自带的 patch 和组件包代码不属于这条配置监听链路，修改后仍需重启。

## 参考资料

- [DeepSeek Harness 源码](https://github.com/deepseek-ai/deepseek-harness)
