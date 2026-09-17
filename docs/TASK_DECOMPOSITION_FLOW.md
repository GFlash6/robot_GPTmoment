# 当前 Agent 任务拆分流程

更新日期：2026-09-11  
范围：当前已经实现的 `robot_agent_framework` 任务规划与重规划路径  
详细模型调用：[MODEL_CONTEXT_FLOW.md](MODEL_CONTEXT_FLOW.md)  
完整目标架构：[DETAILED_ARCHITECTURE.md](DETAILED_ARCHITECTURE.md)

本文只描述当前代码实际行为，不把目标架构中的会话记忆、递归子任务、在线计划修补或机器人闭环标成已实现。可直接打开的矢量图见 [task_decomposition_current.svg](diagrams/task_decomposition_current.svg)，Graphviz 源文件见 [task_decomposition_current.dot](diagrams/task_decomposition_current.dot)。

## 总流程

```mermaid
flowchart TB
    subgraph ENTRY[1. 入口]
        A1[CLI agent goal<br/>生成并提交]
        A2[CLI plan goal<br/>只生成计划]
        A3[Runtime.recover_plan<br/>失败后自动重规划]
    end

    subgraph INPUT[2. 规划输入]
        B1[自然语言 goal]
        B2[当前或任务冻结的 Skill Catalog]
        B3{是否为重规划?}
        B4[无额外上下文<br/>首次 submit_goal]
        B5[必需 planner_runtime_context<br/>previous_plan + step_results + revision]
    end

    subgraph PLAN[3. Planner.plan]
        C1[验证 goal 与 ModelConfig]
        C2[过滤技能能力字段<br/>schema/checks/resources/<br/>cancelable/replay_safe/verifier]
        C3[创建 model_responses 记录<br/>status=requesting]
        C4[PlanningMethod 构造提示<br/>要求 JSON DAG]
        C5[ContextAllocator 分配预算]
        C6[组装 ModelRequest<br/>system + context + user]
        C7[Chat Completions HTTP 请求]
    end

    subgraph RESPONSE[4. 响应与计划校验]
        D1{HTTP 2xx?}
        D2{choices/content 完整<br/>finish_reason=stop<br/>未 refusal?}
        D3[保存 HTTP 状态、原始正文、耗时<br/>和上下文分配结果]
        D4[JSON 解析]
        D5[validate_plan]
        D6{最终 verification 对应<br/>已注册 verifier 技能?}
        D7[model_responses<br/>status=validated]
        DX[model_responses<br/>status=rejected<br/>抛出 ContractError]
    end

    subgraph CONTRACT[validate_plan 当前约束]
        V1[1..256 个步骤]
        V2[step id 唯一且非空]
        V3[技能必须来自目录]
        V4[依赖存在且 DAG 无环]
        V5[args / retries / fallback 合法]
        V6[$ref 只指向直接依赖输出]
        V7[verification 是步骤 ID]
        V8[所有步骤均通向最终验证]
    end

    subgraph OUTPUT[5. 输出去向]
        E1{调用入口}
        E2[CLI plan 输出计划<br/>不创建 Task]
        E3[Runtime.submit]
        E4[再次检查当前目录与资源容量]
        E5[冻结 plan + catalog<br/>revision=0 / generation=0]
        E6[持久化 queued Task<br/>写入 submitted 事件]
        E7[后续由 run / DBOS 执行<br/>不属于任务拆分本身]
    end

    subgraph REPLAN[6. 有界重规划]
        R1[执行结束为 failed]
        R2{存在 goal 且<br/>replans < max_replans?}
        R3[Task -> replanning<br/>replans + 1]
        R4[再次进入 Planner.plan]
        R5[Runtime.revise]
        R6{无 running/unknown<br/>generation 未过期<br/>无用户取消覆盖?}
        R7[保存旧 PlanRevision<br/>revision + 1 / generation + 1]
        RX[拒绝新计划<br/>保留 failed/paused/canceled]
    end

    A1 --> B1
    A2 --> B1
    A3 --> B1
    B1 --> B2 --> B3
    B3 -- 否 --> B4 --> C1
    B3 -- 是 --> B5 --> C1
    C1 --> C2 --> C3 --> C4 --> C5 --> C6 --> C7
    C7 --> D1
    D1 -- 否 --> DX
    D1 -- 是 --> D2
    D2 -- 否 --> DX
    D2 -- 是 --> D3 --> D4 --> D5
    D5 -.逐项检查.-> V1 --> V2 --> V3 --> V4 --> V5 --> V6 --> V7 --> V8
    D5 --> D6
    D6 -- 否 --> DX
    D6 -- 是 --> D7 --> E1
    E1 -- plan --> E2
    E1 -- agent --> E3 --> E4 --> E5 --> E6 --> E7
    E1 -- recover_plan --> R5

    E7 -.执行失败.-> R1 --> R2
    R2 -- 否 --> RX
    R2 -- 是 --> R3 --> R4
    R4 --> C1
    R5 --> R6
    R6 -- 否 --> RX
    R6 -- 是 --> R7 --> E7

    classDef current fill:#e7f5ee,stroke:#287a55,color:#173d2c;
    classDef decision fill:#fff4d6,stroke:#a66b00,color:#5c3b00;
    classDef reject fill:#fde8e7,stroke:#b33a32,color:#651d18;
    classDef boundary fill:#e9efff,stroke:#3f63a8,color:#20365f;
    class A1,A2,A3,B1,B2,B4,B5,C1,C2,C3,C4,C5,C6,C7,D3,D4,D5,D7,E2,E3,E4,E5,E6,E7,R1,R3,R4,R5,R7 current;
    class B3,D1,D2,D6,E1,R2,R6 decision;
    class DX,RX reject;
    class V1,V2,V3,V4,V5,V6,V7,V8 boundary;
```

## 当前一次规划的准确调用链

```text
CLI agent
  -> Runtime.submit_goal(goal, robot_id, model_config, priority, max_replans)
     -> Runtime.catalog()
     -> Planner.plan(goal, catalog)
        -> ModelCaller(config)
        -> PlanningMethod.prepare({goal, skills})
        -> ContextAllocator.allocate(...)
        -> ChatCompletionsTransport.send(...)
        -> ModelCaller 校验 HTTP 和响应结构
        -> json.loads(content)
        -> validate_plan(plan, catalog)
        -> 检查最终步骤的 SkillSpec.verifier
        -> 保存 model_responses 证据
     -> Runtime.submit(plan, ...)
        -> 再次读取当前 catalog
        -> 校验技能重试安全性和资源容量
        -> 冻结 plan 与 catalog
        -> 创建 queued Task
```

`CLI plan` 到 `Planner.plan` 为止，只输出计划；`CLI agent` 才把通过校验的计划提交成 Task。

## 模型实际收到的任务拆分约束

当前 `PlanningMethod` 要求模型：

- 只返回 `{"steps":[...],"verification":"step_id"}` JSON 对象；
- 每个步骤使用冻结目录里的技能；
- 用 `deps` 表示依赖并形成可执行 DAG；
- 用 `{"$ref":"dependency_id.output_field"}` 引用直接依赖的真实输出；
- 可声明 `retries` 和 `fallback`，但均有数量上限；
- 最终 `verification` 必须是独立目标验证步骤的字符串 ID；
- 技能目录无法表达或验证目标时返回错误，不得创造观测、技能或成功结果。

模型看不到技能的 endpoint、token 或任意执行权限，只接收以下能力字段：

```text
input_schema
output_schema
checks
resources
cancelable
replay_safe
verifier
```

## 首次规划与重规划的区别

| 项目 | 首次 `submit_goal` | 自动 `recover_plan` |
|---|---|---|
| 目标 | 新 goal | 原 Task goal |
| 技能目录 | 当前 catalog | Task 冻结 catalog 用于模型规划 |
| 运行上下文 | 当前默认不注入 | `previous_plan`、`step_results`、`revision` |
| 上下文优先级 | 无 | required、priority=100 |
| 预算 | `max_replans` 只保存到 Task | 每次尝试先消费一次预算 |
| 接受路径 | `Runtime.submit` | `Runtime.revise` |
| 并发保护 | 创建新 Task | 检查 expected generation；用户取消优先 |
| 副作用保护 | 依赖 SkillSpec | 修订计划要求所选技能均为 `replay_safe` |

重规划只在任务已经失败、没有仍在运行或 unknown 的执行时接受。它不是在某个运行步骤中动态插入新节点。

## 实际验证过的示例

2026-09-07 的实际 `qwen3.8-max` 请求生成并通过了以下两步计划：

```mermaid
flowchart LR
    I[file.ingest<br/>ingest_readme] -->|asset_id| V[asset.verify<br/>verify_readme_asset]
    V --> F[verification = verify_readme_asset]
```

该证据只证明真实模型响应、JSON 解析、DAG/引用和最终 verifier 契约通过。记录明确标记 `plan_executed=false`，因此不证明计划执行或机器人任务完成。

## 当前没有发生的流程

以下能力尚未接入当前任务拆分链：

- 没有连续对话 Session 自动参与规划；
- 没有从资产目录或语义记忆自动检索上下文；
- 没有边执行边递归创建子 Task；
- 没有根据实时世界状态持续改写 DAG；
- 没有 Planner/Executor/Critic 多 Agent 协商；
- 没有让模型直接执行技能或 ROS2 命令；
- 没有真机任务族的长程规划质量评测；
- 自动重规划框架已有软件测试，但没有外部模型加机器人执行闭环验收。

因此，当前最准确的定义是：

> **一次性受约束 DAG 生成 + 确定性双层校验 + 失败后有界整计划修订。**

## 代码证据

- `robot_agent/cli.py`：`agent`、`plan`、`replan` 三个入口。
- `robot_agent/runtime.py`：`submit_goal`、`submit`、`recover_plan`、`revise` 和失败转 `replanning`。
- `robot_agent/planner.py`：技能能力裁剪、模型证据记录、JSON/DAG 和 verifier 校验。
- `robot_agent/model_methods.py`：任务拆分提示与 JSON 输出格式。
- `robot_agent/model_call.py`：方法、上下文、请求和响应校验的组合。
- `robot_agent/model_context.py`：必需/可选上下文预算分配。
- `robot_agent/model_transport.py`：无状态 Chat Completions HTTP 调用。
- `robot_agent/contracts.py`：DAG、依赖、引用、fallback 和最终验证约束。
- `docs/validation/model-planning-qwen3.8-max.json`：实际模型两步规划证据及验收边界。
