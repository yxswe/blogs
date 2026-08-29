---
title: "How DSH Builds a Component Runtime on Cordis"
description: Using the Web Profile as an example, this article explains how DSH composes a component tree from bundles and patches, then uses Context, Registry, Fiber, Reflect, and Loader during Boot to build and dynamically update the runtime.
lang: en
translationKey: dsh-cordis-architecture
date: 2026-08-24
tags:
  - DeepSeek Harness
  - Cordis
featured: false
---

## 1. DSH's Real Entry Point: How a Profile Builds the Component Tree

A conventional application often creates its database, model client, tools, and Web server in sequence inside a fixed `main()`. The DSH command-line entry point does something smaller but more consequential: it finds the selected **Profile**, merges the configuration layers declared by that Profile into a Cordis component tree, and hands the result to the Loader.

Using the built-in Web surface as the example, these two commands mean the same thing:

```sh
dsh web
dsh --profile web
```

On the first run, DSH initializes `$DSH_HOME/profiles/web` automatically. The initial directory is small:

```text
$DSH_HOME/profiles/web/
├── package.json          # Profile manifest: dependencies and ordered bundles
├── cordis.patch.yml      # This Profile's own component-tree patch
├── pnpm-workspace.yaml   # pnpm installation rules for external components
└── cordis.yml            # Generated empty root; do not edit by hand
```

### 1.1 `package.json`: what code is available and which bundles are loaded

To understand this file, first distinguish ordinary components from bundles:

- An **ordinary component** is one runnable unit in the component tree, usually delivered as a standalone npm package.
- A **bundle** groups multiple components and uses **the bundle package's own** `cordis.patch.yml` to describe how they enter the component tree; `@deepseek-ai/dsh-web-app` is one example. The bundle itself is not a runtime component—the component rows it contributes are what run.

At the Profile level, `dependencies` records installed external packages, while `dsh.profile.bundles` lists the bundles to apply in order. The built-in Web Profile starts with this manifest:

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

These bundles ship with DSH, so `dependencies` starts empty. DSH applies `dsh-base` first, supplying shared Agent, Session, LLM, Tools, persistence, and Sandbox capabilities. It then applies `dsh-web-app`, which adds the Host API, HTTP server, and browser components. A later bundle can override an earlier row by targeting the same `id`.

Using `dsh-web-app` as the example, a bundle's core directory structure is:

```text
packages/bundle/web-app/
├── package.json          # Declares dsh.bundle.patch and component dependencies
├── cordis.patch.yml      # The bundle's own component-tree patch
└── src/                  # Source for components shipped by the bundle
```

The `dsh.bundle.patch` field in `package.json` points to `cordis.patch.yml` inside the same package. This file defines the bundle's default components; it is not the user's `$DSH_HOME/profiles/web/cordis.patch.yml`, which adds or overrides content for that Profile.

### 1.2 `cordis.patch.yml`: composing the component tree under `cordis.yml`

`cordis.yml` is an empty root. Each `cordis.patch.yml` describes part of the component subtree mounted below it. The Web Profile applies these patches in order:

```text
dsh-base/cordis.patch.yml
          ↓
dsh-web-app/cordis.patch.yml
          ↓
$DSH_HOME/profiles/web/cordis.patch.yml
          ↓
$DSH_HOME/cordis.patch.yml
          ↓
command-line --patch layers, if any
          ↓
final component tree under cordis.yml
```

Each patch may insert component rows or modify and disable an existing row through the same `id`. Later patches take precedence: `dsh-web-app` can override `dsh-base`, and the Profile patch can override every bundle. A `config` override replaces the whole value rather than deep-merging its fields.

Inspect the result without starting the Web server:

```sh
dsh --profile web --dump-config
```

### 1.3 Two Ways to Add Components

A component passes through three stages before it runs:

| Stage | Meaning |
| --- | --- |
| Installation | The component package can be resolved. External packages enter the Profile `package.json` under `dependencies`; built-in packages ship with DSH. |
| Registration | A patch places the component as a row in the final component tree. A patch only decides whether the row exists. |
| Activation | The Loader imports the component and creates a Fiber; Cordis activates that Fiber after its required Services become available. |

An installed but unregistered component does not run. A registered component whose dependencies are not yet satisfied waits.

#### Option one: add a component directly

An individual component represents one instance in the tree. Consider the MCP Client that ships with DSH but is inactive by default. It is already resolvable from the DSH installation, so no installation command is needed. Connecting one MCP server only requires editing `$DSH_HOME/profiles/web/cordis.patch.yml`:

```yaml
- insert:
    - id: mcp-docs
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: docs
        transport: streamable-http
        url: https://example.com/mcp
```

`id` is the instance's stable identity in the component tree, `name` is the component package to import, and `config` is passed to that instance. The MCP Client depends on `ctx.tools`. The Loader waits for `dsh-base` to provide the Tools Service before activating it; only then does it register the remote tools with `ctx.tools`.

An external component package typically has a small directory structure:

```text
my-dsh-component/
├── package.json          # Package name, runtime entry point, and dependencies
├── src/index.ts          # Component source
└── lib/index.js          # Built entry point loaded by DSH
```

To add such a component to the Web Profile, install it first:

```sh
dsh plugin --profile web add <component-package>
```

This only adds the package to `dependencies` and installs it into the Profile. If it is not a bundle, the CLI notes that it is currently a plain dependency. A separate `insert` entry in `cordis.patch.yml`, like the MCP example above, is still required to register an instance. In short: **installation solves module resolution; the patch puts the component into the tree.**

#### Option two: add a group of components through a bundle

A bundle is not a different kind of runtime component. It is an npm package containing “a prepared set of component-tree patches.” Bundles are useful when several cooperating components, default configurations, and overrides should be delivered together. A bundle declares this in its own `package.json`:

```json
{
  "dsh": {
    "bundle": {
      "patch": "./cordis.patch.yml"
    }
  }
}
```

That `cordis.patch.yml` may insert many component rows or override rows supplied by earlier bundles. The same command installs an external bundle:

```sh
dsh plugin --profile web add <bundle-package>
```

The difference is what happens next. After installation, the CLI detects the `dsh.bundle` declaration and automatically appends the package's real name to the Web Profile's `dsh.profile.bundles`. One operation therefore does two things: the package enters `dependencies`, and its patch becomes a configuration layer in the component tree. On later `dsh web` runs, that layer is applied after `dsh-web-app` and before the user's own `cordis.patch.yml`.

### 1.4 What Does One Component Unit Look Like?

The first form, and the most common in DSH, uses named exports to place metadata and the entrypoint in one module:

```ts
export const name = 'greeter-consumer'
export const inject = ['greeter']
export const Config = z.object({ who: z.string().required() })

export function apply(ctx: Context, config: { who: string }) {
  ctx.logger.info(ctx.greeter.greet(config.who))
}
```

`name` identifies the component, `inject` declares its required Services, `Config` defines its configuration schema, and `apply(ctx, config)` is its executable entrypoint. Because this module has no default export, Loader treats the whole module as an object component with an `apply` function.

This metadata is not exclusive to object components. The second form default-exports a function and can attach `inject` and `Config` to the function object with `Object.assign()`:

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

The function itself is the entrypoint, and its function name, `greetingPrinter`, becomes the default component name. Registry can also read `inject` and `Config` directly from this function object.

The third form default-exports a class and declares metadata as static fields:

```ts
export default class Heartbeat {
  static inject = ['timer']
  static Config = z.object({ interval: z.number().min(100).required() })

  constructor(ctx: Context, config: { interval: number }) {
    ctx.interval(() => ctx.logger.info('tick'), config.interval)
  }
}
```

The class itself is the entrypoint, and its class name, `Heartbeat`, becomes the default component name. Registry reads `inject` and `Config` from the class's static properties, while Fiber creates the instance with `new Heartbeat(ctx, config)`. `name`, `inject`, and `Config` are all optional metadata: omitting `inject` means the component waits for no additional Services, while omitting `Config` means no schema processes its configuration. Whichever form is used, Loader must ultimately pass Registry a function, class, or object with an `apply` function.

## 2. How Boot Builds a Runtime Context from a Profile

Chapter 1 produces the final component rows, but they are still static descriptions. Boot turns them into running component instances. The key to that transition is `ctx`, the value passed to every component.

### 2.1 What Is a Context (`ctx`)?

At its core, `ctx` is Cordis's runtime container. It uses a `Proxy` as a single entry point for resolving Services, managing component registration, dispatching events, and recording Effects, so all of these capabilities are available through one object.

`new Context()` first creates the Root Context. Whenever a component instance is registered, Cordis creates a Fiber for it and derives a child Context from the parent Context, bound to that Fiber. The child inherits the parent's core capabilities and gives the component access to Services in the current scope, while the corresponding Fiber owns the component's Effects.

#### Core Members and Context Methods

The Root Context stores the core members directly. A child Context inherits them through the prototype chain and may override its parent's `fiber`, `baseUrl`, or scope information.

| Member | Meaning |
| --- | --- |
| `ctx.root` | Always points to the Root Context. Only the root itself satisfies `ctx.root === ctx`. |
| `ctx.baseUrl` | The base for resolving relative modules and file paths. It starts as `undefined` on the Root Context, and a child inherits it by default. |
| `ctx.fiber` | The Fiber that owns this Context. The Root Context has the Root Fiber with `uid` `0`; a component's child Context has that component instance's Fiber. |
| `ctx.reflect` | The Service registration and resolution layer behind the `Proxy`. |
| `ctx.registry` | The component registry. It stores component Runtimes and creates Fibers. |
| `ctx.events` | The event bus. |
| `ctx.logger` | The logging service. `ctx.logger('name')` creates a named Logger, while `ctx.logger.info()` logs directly. |
| `ctx[Context.isolate]`, `ctx[Context.intercept]` | Two low-level, Symbol-keyed maps holding Service isolation scopes and intercept configuration. |

All of these members appear in the `Context` type declarations. `Context` itself also defines three public methods:

| Method | Meaning |
| --- | --- |
| `extend(meta)` | Create a child Context that inherits this Context and adds local information. |
| `isolate(name, label?)` | Derive a child Context with an independent scope for the specified Service. |
| `intercept(name, config)` | Derive a child Context that adds Service configuration affecting only its descendants. |

#### Shortcut Property and Methods

To avoid repeatedly writing `ctx.reflect.get()` or `ctx.registry.plugin()`, Cordis calls `mixin()` during initialization to map members of several core objects onto the top level of `ctx`. These shortcuts are not copied implementations: the `Proxy` forwards each access to the corresponding object for the current Context.

| Core member | Shortcut mapped onto `ctx` |
| --- | --- |
| `ctx.reflect` | `get()`, `set()`, `provide()`, `accessor()`, `mixin()` |
| `ctx.fiber` | `runtime`, `effect()` |
| `ctx.registry` | `inject()`, `plugin()` |
| `ctx.events` | `on()`, `once()`, `parallel()`, `emit()`, `serial()`, `bail()`, `waterfall()` |

### 2.2 Registry: Turning Component Code into Fibers

Registry is easiest to understand as two layers: a Runtime records “which component is this?”, while a Fiber represents “one running instance of this component.”

The Registry created by `new Context()` initially has no records. Every call to `ctx.plugin(component, config)` performs three steps:

1. It extracts the component entrypoint, internally called `callback`. A function or class component uses itself as `callback`; an object component uses its `apply` function.
2. It uses the `callback` function reference as a key to look up a Runtime, creating one only when none exists. The Runtime stores the component name, entrypoint `callback`, configuration schema, and all Fibers belonging to that component.
3. It creates a new Fiber for this call and stores the supplied `config` and lifecycle state in it.

All Contexts share the same underlying Registry. Registry indexes Runtimes and Fibers by entrypoint:

```text
All Contexts ──→ the same Registry
                 └── callback: Greeter
                     └── Runtime
                         ├── name / callback / Config schema
                         └── fibers
                             ├── Fiber A
                             └── Fiber B
```

The key here is a function reference, not a component name, package name, or component-row `id`.

`ctx.inject(deps, callback)` is a shortcut for temporarily mounting dependency-aware logic from component code. It does not create a component row with an `id`, package name, and configuration, nor does it write anything to `cordis.yml`. Internally, it creates the in-memory component definition `{ inject: deps, apply: callback, name: callback.name }` and passes that definition to `ctx.plugin()`. It therefore creates a child Fiber whose dependency changes and disposal are managed by Fiber in the usual way.

Registry therefore answers: **has this component code been registered, and which Fiber should this registration create?**

### 2.3 Fiber: Managing One Component Instance's Lifecycle

In the source, a component Fiber has the following main fields:

| Member | What it stores |
| --- | --- |
| `uid`, `name` | The instance number assigned by Registry and the display name derived from the Runtime or an ancestor; the Root Fiber has `uid` `0`, and a disposed Fiber has `null` |
| `parent` | The Parent Context used to create this Fiber; its parent Fiber is available as `parent.fiber` |
| `ctx` | The Context associated with the current Fiber |
| `runtime` | The Runtime that owns this instance, including its component entrypoint and configuration schema; it is `null` for the Root Fiber |
| `inject` | The component's declared Service dependency map |
| `config` | The validated and processed component configuration used for the current activation |
| `store` | Holds the Services bound for the current activation and becomes `undefined` after unloading |
| `state` | The current lifecycle state |
| `inertia` | The current loading or unloading task; it is `undefined` when the Fiber is stable |
| `dispose` | Unloads and permanently removes this component instance |

A Fiber moves through these states:

```text
PENDING (waiting for Services)
    ↓
LOADING (running component code)
    ↓
ACTIVE (component is running)
    ↓
UNLOADING (running cleanup)
    ↓
DISPOSED
```

The most important Fiber method is `effect()`, which components normally call through the `ctx.effect()` shortcut. This is Cordis's concrete implementation of **Revertible Effects**: whenever an operation changes external state, it supplies a cleanup function that reverses that change.

```ts
function apply(ctx: Context) {
  ctx.effect(() => {
    const timer = setInterval(work, 1000)
    return () => clearInterval(timer)
  }, 'work-timer')
}
```

The function passed to `effect()` runs immediately, while the current Fiber saves the cleanup function it returns. The Fiber automatically runs that cleanup when the component unloads, restarts, or is removed; calling the value returned by `effect()` can also clean it up early. Registrations created by `ctx.provide()`, `ctx.on()`, and `ctx.plugin()` follow the same mechanism, so they are reverted with their owning Fiber.

Fiber also provides lifecycle helpers: `getEffects()` inspects registered Effects, `await()` waits for loading or unloading to finish, `restart()` and `update()` reactivate a component, `dispose()` permanently removes an instance, and `assertActive()` verifies that the instance has not been disposed.

Except for the Root Fiber, each component Fiber is constructed by `parentCtx.plugin(component, config)` together with its corresponding Context. If a component calls `ctx.plugin()` through its own Context, the new Fiber becomes its child. The component tree therefore becomes an in-memory runtime tree made of Fibers and Contexts:

```text
Root Fiber ── Root Context
├── Fiber A ── Context A
│   └── Fiber C ── Context C
└── Fiber B ── Context B
```

The child Fiber constructor attaches its teardown to the parent Fiber in the following way. In simplified form, the code is:

```ts
childFiber.dispose = parentFiber.effect(() => {
  return async () => {
    // Remove childFiber from its Runtime and unload it
  }
}, 'ctx.plugin()')
```

`parentFiber.effect()` creates a `dispose` wrapper. The parent Fiber stores it in its `_disposables` cleanup list, while the child Fiber stores the same function as `childFiber.dispose`.

The same teardown can therefore start in two ways: by calling `childFiber.dispose()` directly, or by unloading the parent Fiber. When the parent unloads, it runs the wrappers in its cleanup list and thereby unloads the child. The child's cleanup list contains the wrappers for its own children, so the process recursively unloads the entire subtree.

Fiber therefore answers: **when should this component instance run, what does it depend on, and what must be cleaned up when it unloads?**

### 2.4 Reflect: How Components Provide and Depend on Services

In Cordis, one component cannot directly depend on another component or on its Fiber. `ctx.plugin()` only registers the component with Registry and creates a Fiber. The component must also call `ctx.provide()` while its entrypoint runs to expose a capability as a Service. Another component's `inject` declaration depends on that Service name.

A component tree has only one underlying Reflect. After the Root Context creates it, every child Context continues to use its `props` and `store`:

```text
Root Context ─────┐
Child Context A ──┼──→ the same Reflect
Child Context B ──┘     ├── props
                        └── store
```

The two tables serve different purposes:

| Record | What it stores | Key | Service-scope aware? |
| --- | --- | --- | --- |
| `props` | Property resolution rules, such as Service or accessor | Property name, such as `greeter` | No; one property definition is shared by the whole tree |
| `store` | Actual Service implementations (`Impl`), including the `value` and owning Fiber | A Symbol | Yes; the same Service name can have different implementations in different scopes |

`props.greeter = { type: 'service' }` only tells the Proxy: “Treat `ctx.greeter` as a Service property.” Finding the object to return still requires a lookup in `store`.

#### Service Isolation: Using Different Implementations of the Same Service

Service implementations are stored in `reflect.store`, but its key is not the Service name. The key is a Symbol recorded in `ctx[Context.isolate]`:

```text
ctx[Context.isolate].greeter → Symbol A
reflect.store[Symbol A]      → greeter implementation
```

This extra mapping allows different Contexts to use different implementations of a Service with the same name. An ordinary child Context inherits its Parent Context's mapping, so both use the same Symbol to look up `greeter` and therefore find the same implementation.

When a child is derived through `isolate()`, Cordis creates a new mapping layer for it and changes the Symbol only for the specified Service:

```ts
const child = ctx.isolate('greeter')
```

```text
Parent Context: greeter → Symbol A
Child Context:  greeter → Symbol C
```

The Parent Context is not modified, and every other Service still inherits its Symbol from the Parent Context. Components below the Parent Context now look up `greeter` through `Symbol A`, while components below the Child Context use `Symbol C`; each side can therefore register and use its own `greeter` implementation. `isolate()` only changes the Symbol used for lookup and does not register a Service by itself.

#### How `provide` Registers a Service in Detail

The following `greeterComponent` is an ordinary component that exposes a Service named `greeter` from its entrypoint:

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

Here, `ctx` is the dedicated Context derived from the Parent Context when the Fiber for `greeterComponent` is created, and `greeterService` is the concrete object being provided. `ctx.provide()` is a shortcut for `ctx.reflect.provide()`. Internally, it performs these operations in order:

1. Mark `greeter` as a Service in `props`.
2. Ensure that the Root Context has a default Symbol for `greeter`.
3. Read the Symbol actually used for `greeter` from the current Context's address table. If that Context has isolated `greeter`, this is the isolated Symbol.
4. Create an `Impl` containing the Service name, concrete object, and owning Fiber.
5. Wrap the registration in an Effect owned by the current Fiber so that unloading the Fiber automatically removes the Service.

The resulting structure is:

```text
ctx.reflect.props.greeter = { type: "service" }

Impl
├── name: "greeter"
├── value: greeterService
└── fiber: Fiber for greeterComponent

Current Context's address table
└── greeter ──→ Symbol A

The same Impl can be referenced from multiple places
├── ctx.reflect.store[Symbol A] ──→ Impl
├── Fiber.store.greeter for greeterComponent ──→ Impl
└── Fiber.store.greeter for each Consumer that resolves this implementation ──→ Impl
```

When `provide()` runs, it first places the `Impl` in `reflect.store` and in the provider's own `Fiber.store`. When a Consumer resolves its `inject` declaration, it obtains the same `Impl` from `reflect.store` and places it in its own `Fiber.store` during activation. The provider and Consumers can therefore access the same `Impl.value` through their respective `ctx.greeter` properties. Service lifetime ownership is recorded by `Impl.fiber`.

If `greeterComponent` creates a Fiber but never calls `provide()`, `greeter` does not appear in Reflect and Fibers that depend on it remain `PENDING`. `greeterComponent` can still listen for events or start a timer, but other components cannot depend on it through `inject`. When the Fiber for `greeterComponent` unloads, the Effect created by `provide()` automatically removes the Service and returns dependent Fibers to the waiting state.

#### Reflect's Other Shortcuts

In addition to `provide()`, Reflect exposes four related methods:

| Shortcut | Capability | Underlying mechanism |
| --- | --- | --- |
| `ctx.get(name)` | Probe an optional Service | Looks in `store` using the current Context's isolation scope and returns only an active implementation by default |
| `ctx.set(name, value)` | Update a Service implementation value | Finds the record in the current scope; only the Fiber that provided the Service may change it |
| `ctx.accessor(name, hooks)` | Add a property that is evaluated when read | Reading `ctx[name]` calls the supplied `get`; writing it calls the optional `set` |
| `ctx.mixin(source, keys)` | Expose Service methods directly on `ctx` as shortcuts | For example, `ctx.mixin('timer', ['setTimeout'])` forwards `ctx.setTimeout()` to `ctx.timer.setTimeout()` |

The difference is that `accessor()` lets a component define the read and write behavior of one property, while `mixin()` internally creates such accessors for multiple members at once. Both only register access rules in `props`; neither registers a Service in `reflect.store`.

`provide()` and these four methods are not copied onto the Context object. During initialization, Reflect calls `mixin('reflect', ...)` to create accessors for them in `props`. When code reads `ctx.get`, the outer Proxy forwards the call to `ctx.reflect.get` for the current Context. Shortcuts such as `runtime`, `plugin`, and `on` use the same mechanism and forward to Fiber, Registry, and Events respectively. After initialization, `props` contains 16 shortcuts while `store` is still empty; later calls to `provide()` or `accessor()` add more records to `props`.

Reflect therefore answers: **which Service implementation is available in the current scope, how can code access it through `ctx`, and when should a Fiber that depends on it run?**

### 2.5 Events: How Components Emit and Listen for Events

A component tree shares one Events instance. Its listener table uses the event name as the key and an array of listeners as the value:

```text
Events
└── "greeter/used"
    ├── { ctx: Context A, callback: listenerA }
    └── { ctx: Context B, callback: listenerB }
```

When code calls `ctx.on('greeter/used', callback)`, Cordis appends a record containing the callback and the current Context to the corresponding array. The Context is retained so scoped dispatch can filter listeners. The registration is also owned by the current Fiber, so it is removed automatically when the component unloads. The function returned by `ctx.on()` can remove it earlier.

When code calls `ctx.emit('greeter/used', 'DSH')`, Events looks up the array under the same name, filters it for the target scope, and passes `'DSH'` to each remaining callback. Emitting an event with no listeners has no effect.

```ts
ctx.on('greeter/used', (who) => {
  ctx.logger.info(`greeted ${who}`)
})

ctx.emit('greeter/used', 'DSH')
```

The dispatch method determines how listeners run:

| Method | Execution |
| --- | --- |
| `emit()` | Call every listener synchronously without awaiting Promises. |
| `parallel()` | Run every listener concurrently and wait for completion. |
| `serial()` | Await listeners in order and stop on the first effective result. |
| `bail()` | The synchronous counterpart of `serial()`. |
| `waterfall()` | Listeners wrap the remaining chain through `next()` and may stop it by not calling `next()`. |

### 2.6 How Boot Builds and Updates the Component Tree

`runProfile()` first reads the Profile `package.json` and collects bundle patches, the Profile patch, the global user patch, and command-line overlays in order. `boot()` then creates the Root Context, at which point startup enters Cordis.

#### Default Behavior after Creating the Root Context

1. `new Context()` creates the Root Fiber and the four core capabilities `reflect`, `registry`, `events`, and `logger`.
2. `boot()` sets `baseUrl`, which anchors component-package resolution, and then calls `ctx.provide('dshHomePath', dshHomePath)` to register the path-building function `dshHomePath` as the first Service on the Root Context. For example, `dshHomePath('sessions')` returns the absolute path to `$DSH_HOME/sessions`, and Loader can also use it while evaluating `!!js` expressions in configuration.
3. DSH passes the statically imported Loader to `ctx.plugin()` as the first component. The Loader cannot rely on a component tree that does not yet exist to load itself, so Boot must start it directly. Registry now creates its first Runtime and corresponding Fiber; once active, the Loader provides the `ctx.loader` Service.

#### How the Loader Loads the Complete Component Tree

On every startup, DSH writes the Profile's `cordis.yml` as an empty array, `[]`. The file only anchors the Profile directory and module-resolution location; the actual component rows come from the layered `cordis.patch.yml` files:

```text
empty cordis.yml
        +
bundle patches → Profile patch → $DSH_HOME/cordis.patch.yml → --patch and other overlays
        ↓
Include composes the final component rows
        ↓
Loader creates an Entry and entry.ctx for each row
        ↓
Import the component package named by name
        ↓
entry.ctx.registry.plugin(component, config)
        ↓
Create a Fiber; activate it after its inject requirements are met
```

Once the Loader is ready, Boot registers `cordis:include` and `cordis:group` as built-in components, then creates a root component row with the fixed `id` `include`. Include reads `cordis.yml`, applies every patch in order, and hands the final component rows to the Loader's Entry Tree.

The resulting Context hierarchy is approximately:

```text
Root Context
└── Loader Context
    └── Include Context
        ├── Context for component row A
        ├── Context for component row B
        └── Group Context
            ├── Context for child row C
            └── Context for child row D
```

#### How `cordis.patch.yml` Triggers Runtime Updates

After initial startup succeeds, `runProfile()` ensures that the `timer` and `hmr` Services are available, then uses HMR to watch both:

- `$DSH_HOME/profiles/web/cordis.patch.yml`
- `$DSH_HOME/cordis.patch.yml`

HMR watches for each file to be created, changed, or removed. When either changes, DSH rereads both user patch files, recomposes them with the original bundle patches and launch overlays, and passes the new complete patch list to the root Include:

```text
patch file changes
        ↓
reread both user patches
        ↓
recompose every patch layer
        ↓
update the root Include
        ↓
Loader compares the old and new Entry Trees by id
        ↓
create, update, replace, or remove the corresponding Fiber
```

| Component-row change | Loader action |
| --- | --- |
| Add a new `id` | Import the component and create a new Fiber. |
| Remove a row or set `disabled` | Dispose its Fiber and revert the Effects it owns. |
| Keep the same `id` but change `config` | Update the existing Fiber's configuration and reactivate the component. |
| Change `name`, `inject`, or grouping | Dispose the old Fiber and create one from the new definition. |

The update is transactional. If applying the new tree fails, the Loader attempts to restore the last successful tree, while HMR logs the error and emits `hmr/config-update-failed`. When a Service provider is replaced, dependent Fibers wait after the old implementation disappears and reactivate after the new one becomes available.

Editing either watched user `cordis.patch.yml` therefore does not require restarting DSH. The Profile `package.json`, bundle list, bundle-owned patches, and component package code are outside this configuration watch path and still require a restart.

## References

- [DeepSeek Harness source code](https://github.com/deepseek-ai/deepseek-harness)
