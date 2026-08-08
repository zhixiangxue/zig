# zig PRD (Product Requirements Document)

## 1. 项目定位

zig 是一个 **图域全家桶 Python library**（pip installable），将图数据库封装为统一、直观的服务接口。

### 1.1 心智模型

zig = 图数据库界的 SQLite SDK。

```python
# SQLite
conn = sqlite3.connect("programs.db")
conn.execute("INSERT INTO ...")
conn.execute("SELECT * FROM ...")

# zig (API 体验类似)
g = Graph("falkordb://localhost:6379/programs")
g.node.add("Program", id="p1", properties={"name": "MyHome"})
await g.commit()
await g.execute("MATCH (p:Program) RETURN p")
await g.query("CalHFA 提供了哪些 Program？")
```

### 1.2 职责边界

| 层 | 职责 | 不负责 |
|---|---|---|
| zig（本 repo） | 图数据 CRUD（node/edge）、确定性查询、可选 NLQ、图 DB 抽象 | HTTP 服务、文件处理、Worker 编排、业务 schema 定义、原始数据格式转换 |
| 上层 HTTP Service（另一个 repo） | HTTP 路由/认证/限流、文件接收（zip/file/text）、Worker 编排、原始数据转换为图结构 | 图数据库操作 |

---

## 2. API 设计

### 2.1 设计原则：API 先行，能力渐进

zig 从 Day0 开始采用 **稳定公共 API + backend adapter + capability negotiation** 的设计：

- 公共 API 必须长期稳定，后续新增 Neo4j / ArangoDB / TigerGraph 等 backend 时，不应要求用户改调用方式
- Day0 开始全部采用异步接口，所有涉及 IO 的方法均使用 `async` / `await`
- v0 可以只实现 FalkorDB backend，但 API 与数据模型必须按可扩展形态设计
- 不强行抹平所有图数据库差异；差异能力通过 capability 暴露
- 查询语言、事务、索引、约束、多重边、schema introspection 等能力由 backend 声明支持情况

```python
g = Graph("falkordb://localhost:6379/programs")

if g.supports("transactions"):
    ...

if g.supports("schema_introspection"):
    ...
```

### 2.2 唯一入口

```python
from zig import Graph

g = Graph("falkordb://localhost:6379/programs")
```

URI 格式：

```
{backend}://{host}:{port}/{graph_name}
{backend}://{user}:{password}@{host}:{port}/{graph_name}
```

不同 backend 只需换 scheme：

```python
Graph("falkordb://localhost:6379/programs")
Graph("neo4j://localhost:7687/programs")
Graph("arangodb://root:pass@localhost:8529/programs")
```

`Graph` 是编程模型中的唯一入口。`zig` 只是 repo 名和包名，不出现在代码中。

> v0 只需要实现 FalkorDB adapter；其他 backend 作为架构扩展目标，不作为 v0 交付承诺。

### 2.3 统一数据模型

zig 对外提供统一的图数据模型，所有 backend 结果都应归一到这些对象或等价结构：

```python
Node(
    id="p1",
    label="Program",
    properties={"name": "MyHome", "amount": 50000},
)

Edge(
    source="p1",
    type="OFFERED_BY",
    target="a1",
    properties={"since": 2024, "source": "calhfa"},
)

QueryResult(
    records=[...],
    columns=[...],
    raw=None,
)

GraphSchema(
    labels=[...],
    relationship_types=[...],
    properties={...},
)
```

设计约束：

- `Node.id` 在同一个 graph 内全局唯一
- `Node.label` 表示图数据库节点类型，与业务 schema 解耦，由上层自由定义
- `Node.properties` 承载全部业务属性；业务属性即使名为 `label`，也必须放在 `properties` 中
- `Edge.source` / `Edge.target` 引用 `Node.id`
- `Edge.type` 由上层自由定义
- `Edge.properties` 从 Day0 支持，避免未来破坏 API
- backend 原始返回值可以放在 `raw`，但默认用户应使用统一结果模型

### 2.4 图变更 — node / edge CRUD

```python
# ===== 节点 =====
g.node.add("Program", id="p1", properties={"name": "MyHome", "amount": 50000})
g.node.add("Agency", id="a1", properties={"name": "CalHFA", "county": "Sacramento"})

g.node.update("p1", properties={"amount": 60000})         # 部分属性更新
g.node.upsert("Program", id="p1", properties={...})      # 存在则更新，不存在则新增
g.node.delete("p1")
g.node.get("p1")                          # 获取单个节点，id 在 graph 内全局唯一

# ===== 边 =====
g.edge.add("p1", "OFFERED_BY", "a1", properties={"since": 2024, "source": "calhfa"})
g.edge.delete("p1", "OFFERED_BY", "a1")

# ===== 批量操作 =====
g.node.add_many([
    ("Program", dict(id="p2", name="DreamForAll", amount=100000)),
    ("Agency", dict(id="a2", name="GSFA")),
])

g.edge.add_many([
    ("p2", "OFFERED_BY", "a2", dict(since=2024)),
])

# ===== 持久化 =====
await g.commit()
```

约束：

- `node` / `edge` 是 `Graph` 的子对象，作为图操作的唯一入口
- label、relationship type、id 等结构字段通过显式参数传递；全部业务属性必须放入 `properties` 字典
- `Node.properties` / `Edge.properties` 完全由上层业务决定，zig 不绑定任何业务 schema
- label / relationship type / property key 必须做合法性校验，property value 必须参数化写入，避免查询注入
- 默认不允许同一组 `(source, type, target)` 重复创建多条边
- 如果未来支持多重边，应通过显式 `edge.id` 或 backend capability 引入，不改变现有 API

### 2.5 commit 模式

```python
# 方式 A: 显式调用
g.node.add(...)
g.edge.add(...)
await g.commit()

# 方式 B: 异步上下文管理器（正常退出自动 commit，异常时丢弃未提交的本地 pending operations）
async with Graph("falkordb://localhost:6379/programs") as g:
    g.node.add(...)
    g.edge.add(...)
```

`commit()` 的语义是 **flush pending operations as a unit of work**：

- zig 会在 client side 暂存变更，并在 `commit()` 时批量提交
- 是否具备数据库级原子性，取决于 backend capability
- 不应在公共语义中承诺所有 backend 都支持强事务 rollback
- 如果 backend 不支持事务，异常只能保证未提交的本地 pending operations 被丢弃，不能保证数据库端已执行操作自动回滚

能力检查：

```python
if g.supports("transactions"):
    ...
```

### 2.6 查询

#### 确定性查询

```python
result = await g.execute("MATCH (p:Program)-[:OFFERED_BY]->(a:Agency) RETURN p.name, a.name")
```

`execute()` 用于执行确定性的数据库查询语句。默认查询语言由 backend 决定：

- FalkorDB / Neo4j: Cypher
- ArangoDB: AQL
- TigerGraph: GSQL

也可以显式指定语言：

```python
result = await g.execute(
    "MATCH (p:Program) RETURN p",
    language="cypher",
)
```

设计约束：

- 公共 API 使用 `execute()` 表达“执行确定性查询语句”，避免绑定单一查询语言
- `language=None` 时使用 backend 默认查询语言
- 如果用户显式传入不被当前 backend 支持的 `language`，应抛出明确异常

#### 自然语言查询（NLQ）

```python
answer = await g.query("CalHFA 提供了哪些 Program？")
```

`query()` 用于自然语言查询，是 LLM 驱动的可选能力，不与确定性 `execute()` 混用。

内部流程：`graph.schema() → 组装 prompt → LLM → backend query language → 执行 → 返回结果/答案`

约束：

- `query()` 是 optional / experimental capability
- 上游不需要手写 schema，但可以提供 schema hints 增强准确性
- LLM provider、模型、API key、超时、重试、日志、隐私策略必须可配置
- `graph.labels()` + `relationship_types()` 不足以保证高质量 NLQ，需逐步支持属性名、关系方向、样例值、约束等 schema introspection

能力检查：

```python
if g.supports("nlq"):
    answer = await g.query("CalHFA 提供了哪些 Program？")
```

### 2.7 多图隔离

```python
g_programs = Graph("falkordb://localhost:6379/programs")       # 业务方 A
g_supply = Graph("falkordb://localhost:6379/supply_chain")     # 业务方 B
g_knowledge = Graph("falkordb://localhost:6379/knowledge")     # 业务方 C
```

同一 FalkorDB 实例内用 graph key 隔离，类似 SQLite 的不同 db 文件。

### 2.8 backend capabilities

每个 backend adapter 需要声明自身能力：

```python
g.capabilities
# or
g.supports("transactions")
```

核心 capability 包括：

| Capability | 含义 |
|---|---|
| `transactions` | 是否支持数据库级事务 / rollback |
| `schema_introspection` | 是否支持 labels、relationship types、properties 等结构内省 |
| `parameterized_queries` | 是否支持参数化查询 |
| `constraints` | 是否支持唯一约束等机制 |
| `indexes` | 是否支持索引管理 |
| `multi_edges` | 是否支持同一 source/type/target 的多重边 |
| `nlq` | 是否支持自然语言查询 |
| `vector_search` | 是否支持向量检索能力 |

zig 的公共 API 保持稳定；backend 差异通过 capability 暴露，而不是通过修改用户 API 暴露。

---

## 3. 目录架构

```
zig/
├── src/zig/
│   ├── __init__.py              # 导出: Graph, Node, Edge, QueryResult
│   ├── exceptions.py            # 统一异常
│   ├── models.py                # Node / Edge / QueryResult / GraphSchema
│   │
│   ├── graph/                   # 图模块 — 所有图操作
│   │   ├── __init__.py
│   │   ├── graph.py             # Graph 主类（暴露 node, edge, commit, execute, query, supports）
│   │   ├── nodes.py             # NodeSet（add/update/upsert/delete/get/add_many）
│   │   ├── edges.py             # EdgeSet（add/delete/add_many）
│   │   ├── base.py              # AbstractGraphClient（backend adapter 接口）
│   │   ├── capabilities.py      # BackendCapabilities / capability keys
│   │   ├── registry.py          # BackendRegistry（多图库注册）
│   │   └── backends/
│   │       └── falkordb/
│   │           ├── __init__.py
│   │           └── client.py    # FalkorDBClient 实现
│   │
│   └── query/                   # 查询引擎（内部模块，被 graph.py 调用）
│       ├── __init__.py
│       ├── engine.py            # execute / query 路由
│       ├── cache.py             # 查询结果缓存层
│       └── text_to_query/       # Text → 查询语句（optional capability）
│           ├── __init__.py
│           ├── base.py          # AbstractTextToQuery 接口
│           ├── cypher.py        # Text → Cypher（FalkorDB / Neo4j 等）
│           └── prompts.py       # LLM Prompt 模板
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_models.py
│   ├── graph/
│   │   ├── test_graph.py
│   │   ├── test_nodes.py
│   │   ├── test_edges.py
│   │   ├── test_capabilities.py
│   │   └── backends/
│   │       └── test_falkordb_client.py
│   └── query/
│       ├── test_engine.py
│       ├── test_cache.py
│       └── text_to_query/
│           └── test_cypher.py
│
├── pyproject.toml               # uv 管理
├── .gitignore
└── .python-version
```

---

## 4. 模块职责

### 4.1 `models.py` — 统一数据模型

| 对象 | 职责 |
|---|---|
| `Node` | 统一节点模型：`id`、`label`、`properties` |
| `Edge` | 统一边模型：`source`、`type`、`target`、`properties` |
| `QueryResult` | 统一查询结果模型：`records`、`columns`、`raw` |
| `GraphSchema` | 图结构描述：labels、relationship types、properties、constraints 等 |

统一模型是保持 API 稳定和多 backend 扩展的核心。backend adapter 可以保留 raw result，但必须向上归一到统一模型。

### 4.2 `graph/` — 图模块（对外核心）

| 文件 | 职责 |
|---|---|
| `graph.py` | `Graph` 主类：持有 `node`、`edge`、`commit()`、`execute()`、`query()`、`supports()` |
| `nodes.py` | `NodeSet`：add / update / upsert / delete / get / add_many |
| `edges.py` | `EdgeSet`：add / delete / add_many，支持 edge properties |
| `base.py` | `AbstractGraphClient`：backend adapter 接口，负责连接、写入、查询、schema introspection |
| `capabilities.py` | 定义 backend capability keys 与 `BackendCapabilities` |
| `registry.py` | `BackendRegistry`：register / get |
| `backends/falkordb/client.py` | FalkorDB v0 实现 |

### 4.3 `query/` — 查询引擎（内部模块）

| 文件 | 职责 |
|---|---|
| `engine.py` | 路由：`execute()` 执行确定性查询；`query()` 进入 NLQ 管道 |
| `cache.py` | 查询结果缓存层 |
| `text_to_query/base.py` | `AbstractTextToQuery` 接口：text_to_query(schema, prompt) → query string |
| `text_to_query/cypher.py` | Text → Cypher 实现（FalkorDB / Neo4j 等） |
| `text_to_query/prompts.py` | Prompt 模板管理 |

### 4.4 依赖注入关系

```
Graph(graph.py)
  ├── node: NodeSet             ← 操作节点集合
  ├── edge: EdgeSet             ← 操作边集合
  ├── capabilities             ← backend 能力声明
  ├── supports(name)           → capability negotiation
  ├── commit()                 → AbstractGraphClient.flush / commit
  ├── execute(statement, language) → QueryEngine → AbstractGraphClient.query()
  └── query(prompt)                → QueryEngine → AbstractTextToQuery → AbstractGraphClient.query()
```

- `Graph` 初始化时通过 `BackendRegistry` 获取对应 backend client，注入自身
- `query/` 为内部模块，由 `Graph` 调用，不直接对外暴露
- backend 差异只能通过 adapter 与 capability 暴露，不应污染公共 API

---

## 5. 关键设计决策

| 决策 | 结论 | 理由 |
|---|---|---|
| 演进策略 | API 先行，能力渐进 | Day0 固定公共 API 与统一模型，v0 只实现 FalkorDB adapter |
| 编程入口 | `Graph` 类，`from zig import Graph`，URI 连接 | repo 名不出现在代码中，类似 `sqlite3.connect("file.db")` 的使用体验 |
| 连接方式 | URI: `falkordb://host:port/graph` | 统一、简洁，不同 backend 只换 scheme |
| API 风格 | `g.node.add(...)` / `g.edge.add(...)` | node/edge 是第一公民，CRUD 语义直观 |
| 统一模型 | `Node` / `Edge` / `QueryResult` / `GraphSchema` | 避免 SDK 退化成 backend raw wrapper，支撑长期 API 稳定 |
| Node id | 同一 graph 内全局唯一 | 保持 `g.node.get("p1")` 这类 API 简洁一致 |
| Edge properties | Day0 支持 | 真实业务边通常有来源、时间、权重、置信度等属性 |
| 多重边 | 默认不允许同一 `(source, type, target)` 重复 | 简化 v0 语义；未来通过 capability 或显式 edge id 扩展 |
| commit 模式 | 显式 `await g.commit()` + `async with` 上下文管理 | `commit()` 表示 flush pending operations；数据库级事务取决于 backend capability |
| 查询 API | `g.execute(statement, language=None)` | 显式表达执行确定性查询语句，默认语言由 backend 决定 |
| 自然语言查询 | `g.query(prompt)` | 与确定性执行分离，明确 LLM 查询的可选性和不确定性 |
| capability system | `g.supports(name)` / `g.capabilities` | 不强行抹平 backend 差异，也不让差异污染公共 API |
| ingest 模块 | 不存在，合入 `graph/` | 所有图操作就是 graph 上的 node/edge 操作 |
| schema 管理 | 不维护业务 schema，但提供 `GraphSchema` introspection | 图数据库自描述；NLQ 和工具能力需要结构信息辅助 |
| text-to-query | optional capability | 不作为所有 backend 必备能力；由 `query()` 内部使用 |
| 数据转换 | 不包含 adapter/decomposer/extractor | 属于上层业务逻辑 |
| 多业务方隔离 | `graph` 参数（同一 FalkorDB 实例不同 key） | 天然多租户 |
| 多图数据库 | backend adapter + Registry + capabilities | v0 实现 FalkorDB，后续 backend 不改变用户 API |
| 构建工具 | uv | `uv sync` / `uv add` |
| Docker | 不需要 | 上层 Service 负责部署 |

---

## 6. 已排除的设计

- `Zig` 类 — 编程入口统一为 `Graph`
- `review` 模块 — 查询反馈属于上层业务
- `schema/` 业务 schema 目录 — 不维护业务 schema，但保留 `GraphSchema` 作为 introspection 结果模型
- `g.query(cypher=...)` / `g.query(prompt=...)` / `g.ask(prompt)` — 最终语义为 `g.execute(statement, language=None)` + `g.query(prompt)`
- `adapter / decomposer / extractor` — 数据转换在上层
- `ingest / mutation / workspace / session` 等模块名 — 图操作即 `graph` 模块
- HTTP / REST 层 — 在另一个 repo
- Docker / docker-compose — 上层 Service 负责
