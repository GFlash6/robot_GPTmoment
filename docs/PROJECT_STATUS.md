# 机器人 Agent 框架工程状态

更新日期：2026-09-22
工程阶段：`implementation`  
整体状态：**进行中**  
当前版本：`0.1.0`  
维护范围：`robot_agent_framework/`

2026-09-22 新增应用层：统一动作/鉴权/幂等命令已实现；Session、界面选中对象、资产证据及模型原始输入响应已接入。当前 `qwen3.7-plus` 的实际计划已由 worker 完成文件归档与哈希校验，多轮澄清和失败节点解释通过，浏览器节点解释已验证。详见 [应用层说明](APPLICATION_LAYER.md) 与 [实施跟踪](APPLICATION_LAYER_PLAN.md)。此前模型/只读 UI 的条目保留历史范围，机器人与实时环境验收仍未完成。

记忆上下文增量：已新增共享 memory.search / session.attach-memories 动作，按机器人范围检索、先过滤再限制数量、复核来源字节、绑定记录版本并检查失效。真实模型从记忆读取源文件路径后生成计划，实际 worker 归档与 SHA256 核验通过；UI 记忆选择已完成真实浏览器/模型/worker 验收；摘要已有后续实际验收，实时世界状态仍未完成。证据见 `docs/validation/memory-context-live.json`。

自动重规划增量：已保存提交时会话/语义目标快照，重规划继承人工约束与绑定记忆，同时读取最新任务失败账本。实际文件故障→真实模型备用路径计划→worker 哈希核验通过；证据见 [重规划验证](validation/replanning-context-live.json)。UI 记忆选择已接通；长历史摘要与真机验收仍待完成。

历史摘要增量：显式 session.summarize 已接通，保留近期/固定消息原文与完整历史，记录摘要来源哈希并作为 data 级上下文使用；实际模型摘要、后续规划和 worker 哈希验证通过。超大历史分块已通过真实模型、执行和并发校验；共享会话动作的可配置自动预算策略已通过真实验收；工作台摘要交互已通过真实浏览器验收；真机验收仍未完成。证据：[session-summary-live.json](validation/session-summary-live.json)。

这是工程状态的统一入口，长期记录每个模块及其细项的完成情况。分阶段顺序见 [BUILD_ROADMAP.md](BUILD_ROADMAP.md)，需求和待决问题保留在 [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md)，第一版执行契约见 [ARCHITECTURE.md](ARCHITECTURE.md)，完整目标分层、接口、状态机和案例见 [DETAILED_ARCHITECTURE.md](DETAILED_ARCHITECTURE.md)，实际验证边界见 [VALIDATION.md](VALIDATION.md) 与 [UI_VALIDATION.md](UI_VALIDATION.md)。Momo 生命周期文件只记录图状态、决策和交接，不再承担这份详细清单。

## 状态口径

| 状态 | 判定标准 |
|---|---|
| 已完成 | 当前声明的软件范围已有生产实现，并有相应代码、测试或实际运行记录；只代表该行范围完成。 |
| 进行中 | 已有部分实现，但仍缺生产能力、关键决策或适当层级的实际验收。 |
| 未完成 | 尚无生产实现，或只有接口预留、研究材料和元数据契约。 |

HTTP 请求成功、模型自述成功、软件测试通过和机器人真实完成是不同层级的证据。本文不会用前一种证据替代后一种。状态也不使用估算百分比。

## 总体概览

| 模块 | 总体状态 | 当前结论 |
|---|---|---|
| 项目边界与开源调研 | 已完成 | 单一项目范围已确认；第一轮 41 个有效仓库研究和第一版组件选择已完成。 |
| 任务模型与计划 | 进行中 | DAG、人工计划、计划校验和模型适配已实现；真实模型长程分解与任务族验证仍缺。 |
| 编排与技能执行 | 进行中 | 依赖调度、实际输出引用、技能协议和本地数据技能已实现；机器人技能接入和完整行为后端未完成。 |
| 失败、恢复与打断 | 进行中 | 有界恢复、打断和 HTTP 文件服务 fencing/reconciliation 已有证据；通用补偿、设备端控制权与硬件急停仍缺。 |
| 多任务与资源调度 | 进行中 | 单机多任务、多资源原子分配和优先级抢占已有第一版；真机资源配置和跨主机调度未完成。 |
| 持久化与运行部署 | 进行中 | DBOS 本地 SQLite、账本和单 worker 恢复可运行；Postgres、热升级、高可用和性能验收未完成。 |
| 模型规划与重规划 | 进行中 | 当前环境真实模型已完成文件规划、执行和失败后重规划；跨任务族质量及机器人闭环仍待验收。 |
| 上下文构造与会话 | 进行中 | Session、Memory、摘要/预算、Provider、完整 Bundle 和快照绑定已有实际验证；WorldState、全调用点诊断及质量基准未完成。 |
| 多模态数据与记忆 | 进行中 | 资产目录、哈希、时空元数据、MCAP/rosbag2 和基础检索已实现；真实传感器、地图失效和语义记忆未完成。 |
| 解耦流程 UI | 进行中 | 只读 UI、观察 API 和独立真实问答测试网关已完成；独立应用服务的控制入口已实现；运行端心跳、3D/视频和远程认证未完成。 |
| 多机器人 | 未完成 | 仅有 `robot_id` 和资源命名空间预留，尚无多机器人协调实现与验收。 |
| 验证体系 | 进行中 | 软件、文件、HTTP、恢复、ROS2 诊断录制和浏览器验证已有证据；模型、机器人及传感器现场验收未完成。 |
| Momo 与状态维护 | 进行中 | 项目已注册；后续多项增量尚未与 Momo 图逐项核对，不能宣称持续同步完成。 |

## 1. 项目边界、调研与依赖

| 细项 | 状态 | 当前情况 | 证据或完成条件 |
|---|---|---|---|
| 单一工程边界 | 已完成 | `robot_agent_framework/` 为正式单一项目，探索和目标趋向导航只作为检验场景。 | [用户需求](USER_REQUIREMENTS.md)、Momo 正式快照 |
| 第一轮开源调研 | 已完成 | 调研 41 个有效仓库，保存 110 份固定提交材料及哈希。 | [研究报告](research/REPORT.md)、[仓库矩阵](research/REPOSITORY_MATRIX.md)、[来源校验](research/SOURCE_VALIDATION.json) |
| 第一版组件选择 | 已完成 | 采用 DBOS、py_trees 条件链、MCAP、jsonschema、httpx；前端采用 React、TypeScript、React Flow、Vite。 | [架构](ARCHITECTURE.md)、`pyproject.toml`、`ui/package-lock.json` |
| 选定版本分发许可审查 | 进行中 | 研究阶段已记录仓库级许可证，尚未完成最终分发范围的逐文件和依赖审查。 | 台账 R10；确定分发范围后完成固定版本审查 |
| DimOS memory 深层复用 | 未完成 | 只完成源码研究；没有集成 DimOS memory、其向量能力或完整模块运行时。 | 台账 R03；需真实数据读写、依赖边界和查询验证 |

## 2. 任务模型、分解与计划

| 细项 | 状态 | 当前情况 | 证据或完成条件 |
|---|---|---|---|
| 任务、步骤和计划契约 | 已完成 | 定义任务/步骤状态、依赖、重试、fallback、最终验证节点和 schema 校验。 | `robot_agent/contracts.py`、`tests/test_contracts_memory.py` |
| DAG 合法性检查 | 已完成 | 拒绝循环、缺失依赖以及无法通向最终验证节点的计划。 | `test_dag_rejects_cycles_and_unverified_completion` |
| 操作者计划提交 | 已完成 | CLI 和 Runtime 可接收明确计划并持久化任务。 | `robot_agent/cli.py`、`robot_agent/runtime.py` |
| 依赖输出引用 | 已完成 | 后续步骤只引用成功依赖的实际输出，不在计划中伪造结果。 | `Runtime._args`、真实 DAG 回归测试 |
| 模型生成结构化 DAG | 已完成 | `qwen3.8-max` 经实际服务返回两步 DAG，原始响应入本地账本，计划和最终 verifier 契约通过。 | [模型规划记录](validation/model-planning-qwen3.8-max.json)、`Planner.plan` |
| 长程任务分解策略 | 进行中 | 框架可承载长 DAG 和修订，但尚未形成跨任务族的分解策略、上下文预算和质量评估。 | 用多任务族真实目标评测分解、执行和最终验证 |
| 动态子任务/计划修订 | 进行中 | 计划修订、generation 和完整历史快照已实现；动态扩展仍缺实际模型与现场任务验证。 | `Runtime.revise`、计划历史回归测试 |
| 探索与目标趋向导航实现 | 未完成 | 当前仅作为框架验收场景，没有实现探索算法、frontier 策略或拒止导航方案。 | 取得导航技能和地图接口后另行验收，不以框架测试替代 |

## 3. 编排、调度与技能系统

| 细项 | 状态 | 当前情况 | 证据或完成条件 |
|---|---|---|---|
| 依赖就绪调度 | 已完成 | 仅派发依赖已成功且资源可获得的步骤。 | `Runtime.tick`、`tests/test_runtime.py` |
| 技能注册与冻结契约 | 已完成 | 注册参数/输出 schema、资源、取消、重入和 verifier 属性；任务保存冻结 catalog。 | `Runtime.register`、`Runtime.submit` |
| HTTP 执行协议 | 已完成 | 使用固定 execution ID 的执行、查询和取消协议；请求改变会被拒绝。 | [技能协议](SKILL_PROTOCOL.md)、`tests/test_http_execution.py` |
| 本地文件技能 | 已完成 | `file.ingest`、`asset.verify`、分块 `file.copy` 操作实际文件并返回实际结果。 | `robot_agent/file_copy.py`、文件与浏览器集成测试 |
| 成功结果判定框架 | 已完成 | 成功必须满足 execution ID、终态、quiescent、输出 schema、后置条件和非空来源证据。 | `robot_agent/contracts.py`、终态来源证据测试 |
| 任务族后置条件 | 进行中 | 通用检查器已实现；导航、抓取等任务的独立观测指标和阈值尚未定义。 | 台账 Q03/Q04；需真实适配器观测与测量阈值 |
| ROS2 Action/机器人技能适配 | 未完成 | 尚无实际机器人执行、查询、取消和停止回执适配器。 | 台账 Q02；至少接入一项真实技能并保留执行证据 |
| 完整行为树执行后端 | 未完成 | py_trees 只用于结果条件链，没有完整行为树运行、halt 或可视化编辑器。 | 台账 R04；按真实技能需求决定是否引入 |
| 机器人技能库 | 未完成 | 没有导航、感知、操作、充电等生产技能集合。 | 逐项定义输入、输出、资源、取消、重入、后置条件和证据 |

## 4. 失败、fallback、恢复与打断

| 细项 | 状态 | 当前情况 | 证据或完成条件 |
|---|---|---|---|
| 有界技能重试 | 已完成 | 只有声明 `replay_safe` 的技能可自动重试，次数受计划限制。 | `robot_agent/runtime.py` |
| fallback 选择 | 已完成 | 原候选真实失败后依次选择兼容替代，最终结果仍按原步骤契约检查。 | `test_fallback_uses_actual_failure_and_preserves_original_contract` |
| 暂停、取消与恢复 | 已完成 | 控制请求先取消活动执行，确认停止后转换状态；暂停任务可恢复。 | `test_pause_before_dispatch_and_resume`、HTTP 取消测试 |
| 优先级抢占 | 已完成 | 高优先级任务可请求低优先级任务暂停，资源释放仍依赖停止证据。 | `Runtime.preempt` |
| 未知结果处理 | 已完成 | 不可达执行保持 `unknown`，不重发、不释放资源。 | `test_unreachable_service_does_not_release_or_retry` |
| 进程故障恢复 | 已完成 | worker 被杀后恢复原 execution ID，查询原执行，不重复派发。 | `test_worker_kill_recovers_same_remote_execution_without_redispatch` |
| 用户控制与迟到重规划竞争 | 已完成 | 用户取消和较新 generation 不被迟到模型响应覆盖。 | `test_cancel_wins_over_late_automatic_plan_revision` 等 |
| 跨层重试归属 | 进行中 | 框架有技能和模型预算；机器人驱动/行为后端接入后仍需确定唯一重试责任。 | 台账 R06；验证无重复副作用 |
| 补偿与人工恢复 | 未完成 | 没有通用补偿工作流、持物状态恢复或人工接管协议。 | 台账 Q08；需实际补偿技能和恢复前提 |
| 控制端隔离旧执行者 | 进行中 | 显式 HTTP fencing 已在真实文件服务验证旧令牌拒绝、重启持久化及 worker 原执行恢复；机器人驱动端尚未接入。 | 见技能协议与 validation/fencing-live.json；物理控制权及停止仍需现场验证 |
| 硬件急停 | 未完成 | 软件取消不等于硬件急停，没有独立安全链路及停止回执接入。 | 台账 Q07；需硬件接口和现场验收 |

## 5. 多任务与资源管理

| 细项 | 状态 | 当前情况 | 证据或完成条件 |
|---|---|---|---|
| 多任务账本 | 已完成 | 可同时保存并推进多个任务，状态和事件独立。 | `robot_agent/store.py`、Runtime 测试 |
| 机器人资源命名空间 | 已完成 | 资源折算为 `robot_id/resource`，避免机器人间名称碰撞。 | `Runtime.resource_name` |
| 容量与多资源原子获取 | 已完成 | SQLite 事务内检查和写入全部资源，避免部分占用和超配。 | `test_resource_claims_across_connections_do_not_overallocate` |
| 资源别名冲突保护 | 已完成 | 别名折算冲突不会少计容量。 | `test_resource_alias_collision_cannot_underclaim_capacity` |
| 停止前资源保留 | 已完成 | 只有终态且 quiescent 才释放；未知状态继续占用。 | 架构契约及运行测试 |
| 真机资源模型 | 进行中 | 容量机制已实现，尚无底盘、双臂、夹爪、相机、GPU 的实际清单及跨资源约束。 | 台账 Q05；用实际并发任务验证 |
| 多机器人协调 | 未完成 | 仅预留 robot ID 和资源命名空间，没有跨机器人任务分配、队伍状态或协同恢复。 | 明确多机器人范围后设计并实际验收 |
| 跨主机租约与仲裁 | 未完成 | 当前单账本已实现持久 fencing token；没有跨账本/跨主机一致性与租约仲裁。 | 生产部署方案及实际故障验证 |

## 6. 持久化、并发与部署

| 细项 | 状态 | 当前情况 | 证据或完成条件 |
|---|---|---|---|
| 任务/执行/事件持久账本 | 已完成 | SQLite 保存任务、步骤、执行、控制、事件、资源和计划历史。 | `robot_agent/store.py` |
| DBOS 持久工作流 | 已完成 | DBOS 2.31.0 管理本地工作流恢复，单 worker 锁限制重复工作进程。 | `robot_agent/durable.py`、进程恢复测试 |
| 计划历史与版本契约 | 已完成 | 修订时保存原 plan、steps、catalog、revision、generation 和保存时间；旧账本缺失字段保持可读并明确标记。 | `Runtime.revise`、计划历史回归测试、`ui/src/TaskView.tsx` |
| 本地单 worker 部署 | 已完成 | Python 3.10 / ROS2 Humble 环境和 CLI 可运行。 | [README](../README.md)、第一版验证 |
| Postgres 生产部署 | 未完成 | 未配置、未迁移、未做恢复和吞吐验证。 | 台账 Q13/R01 |
| 多进程/跨机器高可用 | 未完成 | 没有热升级、主从切换或网络分区下的任务与资源验收。 | 明确拓扑后进行故障注入和一致性验证 |
| 性能与容量上限 | 未完成 | 没有大规模任务、事件、资产和执行历史的基准数据。 | 实际规模、延迟/吞吐目标及压测结果 |

## 7. 模型规划与重规划

| 细项 | 状态 | 当前情况 | 证据或完成条件 |
|---|---|---|---|
| 显式模型配置 | 已完成 | 要求实际 endpoint、model 和可选 token 环境变量；没有默认模型。 | `robot_agent/planner.py` |
| 实际 HTTP 请求与原文保存 | 已完成 | 使用 httpx 请求兼容端点，保存 HTTP 状态和原始正文。 | `Planner.plan` |
| 响应内容校验 | 已完成 | 检查非空内容、finish reason、JSON 和计划契约；传输成功不算计划成功。 | Planner 及失败路径测试 |
| 缺配置/连接失败处理 | 已完成 | 不生成默认计划，不提交假任务；失败记录消耗有界预算。 | `tests/test_durable_planner.py` |
| 自动重规划框架 | 已完成 | 支持最大次数、注册 verifier、无活动执行前修订及 generation 保护。 | Runtime/Planner 回归测试 |
| 实际模型成功路径 | 进行中 | qwen3.7-plus 的目标分析、规划、实际文件执行、哈希核验及重规划已有证据；机器人任务仍未验收。 | [文件闭环](validation/multifile-live.json)、[重规划](validation/replanning-context-live.json) |
| 长程规划质量评估 | 未完成 | 没有不同任务族、上下文长度、失败反馈和重规划质量基准。 | 定义数据集与真实执行评价，不能用模型自评 |

### 7.1 上下文构造实施计划与状态

目标是在不替换现有 Runtime、Planner、Memory 和模型调用边界的前提下，增加独立的上下文构造层。完整数据继续保存在各自权威存储中；每次模型调用只生成一个可追溯、受预算约束的上下文视图。

当前结论：Goal 语义分析、Session、Memory、摘要预算、任务状态 Provider 与完整 Bundle 已接入规划/重规划，并有真实模型与文件执行证据。WorldState、各模型方法的统一追溯和跨任务族评测仍未完成，因此本模块总体仍为**进行中**。

```text
ContextRequest
    │
    ├── CapabilityProvider ── Skill Registry / Policy
    ├── SessionProvider ───── Session Store / Summary
    ├── TaskStateProvider ─── Runtime Ledger
    ├── MemoryProvider ────── Memory / Asset Catalog
    ├── WorldStateProvider ── ROS2 / Isaac / Map / TF
    └── OperatorProvider ──── Approval / Override
    │
    ▼
ContextBuilder
    │ validity → retrieval → reduction
    ▼
ContextAllocator
    │ token budget / required / priority
    ▼
RoleAwareRenderer
    │ system policy / conversation / untrusted data
    ▼
Planner / Replanner / Verifier
    │
    └── ContextManifest → Ledger
```

#### 工作包

| ID | 工作包 | 状态 | 具体实现 | 交付物与退出条件 | 依赖 |
|---|---|---|---|---|---|
| CTX-0 | 契约和边界冻结 | 进行中 | 已实现 `GoalContext`、`ContextRequest`、扩展 `ContextFragment`、`ContextBundle`、`ContextManifest`、任务节点/关系契约，并增加经严格字段校验的初步 Goal 分析结果入口；Provider Protocol v1 已实现并接入现有来源；规划快照 v1 及既有 v0 只读兼容已接通，其他 Context 类型的跨版本序列化仍待补充。 | 已有契约和模型边界测试；Provider 已接入；完成序列化兼容后退出。 | `context_models.py`、`goal_analysis.py`、上下文测试 |
| CTX-1 | 权限分层与消息渲染 | 进行中 | `RoleAwareRenderer` 已接入 `ModelCaller`；只有 framework policy 可渲染为 system，普通 Context 作为 user 数据，Session 仅接受 user/assistant。真实 tool-call 配对和更完整污染测试仍待补充。 | 已验证不可信 world data 不会成为 system；补齐真实工具消息与模型请求快照测试后退出。 | `context_render.py`、`model_call.py` |
| CTX-2 | 能力和任务状态 Provider | 进行中 | `ContextBuilder` 已生成紧凑能力视图和 `TaskStateContext`；任务以 `decomposes_to`、`depends_on`、`verifies` 图关系表达，成功结果和证据进入节点；初始规划与重规划已经接入。独立 Provider Protocol 已实现；子规划颗粒度、阻塞/fallback 边尚未完成。 | 已有任务图与陈旧 revision/generation 拒绝逻辑；补齐子规划 ContextProfile 和恢复一致性测试后退出。 | `context_builder.py`、Planner、Runtime |
| CTX-3 | Session 历史和摘要 | 进行中 | 已实现持久 Session、提交时上下文快照、显式历史摘要与近期/固定原文保留；原文预算分块与并发保护已完成真实验证；共享会话动作的自动预算触发已实现并真实验证；工作台控件已实现并验证；自动恢复的快照预算缩减已实现并经真实模型与文件执行验收；更多长程任务族仍待验证。摘要保存覆盖范围、源消息 ID、生成模型及版本；新消息到来后不得静默覆盖原始记录。 | 多轮任务能恢复会话；近期消息原文保留；超预算时先压缩旧历史；摘要可追溯并可重新生成。 | CTX-0、CTX-1 |
| CTX-4 | Memory 检索 Provider | 进行中 | 已实现按 robot ID、有效期与证据过滤的 FTS 检索、版本绑定和工作台选择；自动查询策略与检索质量基准待完善。第一版采用现有结构化过滤与 FTS；有真实召回问题和基准后再增加向量检索及混合排序。 | 过期、错误 robot、证据损坏的记忆不进入上下文；Manifest 记录候选、入选、分数和丢弃原因；建立检索测试集。 | CTX-0、CTX-2；复用现有 Memory |
| CTX-5 | World State Provider | 未完成 | 定义不可变 `WorldStateSnapshot`；从 实际 ROS2/设备、机器人状态、地图和 TF 适配器读取位姿、电量、对象、障碍物及地图版本。进入 Bundle 前检查时间、clock domain、frame、map version、置信度和 evidence。 | 用固定录制数据验证正常、过期、坐标系不一致、地图切换和缺证据路径；实时事实不由长期 Memory 代替。 | CTX-0、真实数据接口、地图/TF 规则 |
| CTX-6 | Builder、预算和调用点接入 | 进行中 | Builder、渲染后预算和稳定排序已接入 Planner 与自动 Replanner；Session/Memory 及恢复预算已接通；旧 CLI context 仍保留兼容路径，World State、模型型 Verifier 和全调用点契约尚未统一。 | 当前核心调用测试通过；移除旧任意 dict 路径并完成各类预算和子规划接入后退出。 | CTX-1 至 CTX-5 |
| CTX-7 | 可观测、重放和质量评估 | 进行中 | 模型发送前已保存基础 `ContextManifest`，包含 request、phase、纳入/丢弃项、预算、估算器和 renderer 版本；Provider 接口版本已记录；完整 Bundle 与快照哈希已保存，规划实际输入重建已验证；统一追溯 UI、各调用点覆盖和消融评测仍待完善。 | 已验证传输失败前 Manifest 仍存在；完成重放和解释接口后退出。 | CTX-2 至 CTX-6 |

#### 第一版契约目标

建议代码边界如下，实际实现前仍需用最小接口测试确认不会与现有平铺模块产生循环依赖：

```text
robot_agent/context/
├── models.py
├── builder.py
├── allocator.py
├── renderer.py
├── manifest.py
├── providers/
│   ├── capability.py
│   ├── task_state.py
│   ├── session.py
│   ├── memory.py
│   ├── world_state.py
│   └── operator.py
├── reducers/
│   ├── history.py
│   ├── memory.py
│   └── world_state.py
└── validators/
    ├── authority.py
    ├── freshness.py
    └── spatial.py
```

`ContextFragment` 的目标字段至少包括：`id`、`kind`、`content`、`source`、`priority`、`required`、`authority`、`observed_at_ns`、`expires_at_ns`、`robot_id`、`frame_id`、`map_version`、`confidence` 和 `evidence_ids`。字段是否适用于某种 `kind` 由契约校验，不要求每段上下文伪造空间属性。

#### 预算和降级顺序

| 顺序 | 上下文类别 | 默认处理 |
|---|---|---|
| 1 | 安全策略、权限、当前 Goal | 必选；超限时拒绝模型调用，不截断语义 |
| 2 | 当前 Plan/Step、成功依赖结果、能力契约 | 必选或高优先级；使用结构化紧凑表示 |
| 3 | 人工覆盖和近期 Session | 高优先级；保留近期原文 |
| 4 | 最新且一致的 World State | 按任务选择；先减少对象数量，不混用过期快照 |
| 5 | 检索 Memory | Top-K；优先证据完整、有效、robot/map 匹配的条目 |
| 6 | 较旧 Session | 先摘要，再按覆盖范围删除原文视图；底层原始消息不删除 |
| 7 | 调试和解释性材料 | 可选；预算不足时最先丢弃 |

#### 分阶段验收顺序

1. `CTX-0 + CTX-1`：先建立类型、权限边界和安全渲染，避免后续 Provider 把不可信数据放入 system。
2. `CTX-2 + CTX-3`：完成 Session 与 Task State 的最小多轮规划/重规划闭环，这是第一项可交付纵向切片。
3. `CTX-4`：接入现有 Memory，先以 FTS 和结构化过滤建立真实基线，不预设必须引入向量库。
4. `CTX-5`：接入带时间与空间一致性检查的世界状态；没有真实接口时只完成契约与录制数据测试，不声称现场完成。
5. `CTX-6 + CTX-7`：统一调用入口、保存 Manifest，并完成重放、超预算、污染上下文和消融评测。

第一版软件闭环的完成条件是：同一 Session 中的初始规划和失败后重规划能够读取受控的近期历史、任务事实及相关 Memory；各 Fragment 有来源、权限和预算记录；过期或不一致数据被拒绝；进程恢复后可以重建上下文。机器人世界状态只有在真实 实际 ROS2/设备 数据、时间/坐标系检查和证据链共同通过后才标记完成。

## 8. 多模态数据、地图与记忆

| 细项 | 状态 | 当前情况 | 证据或完成条件 |
|---|---|---|---|
| 资产分类契约 | 已完成 | 支持 RGB、深度、点云、点云地图、占据地图、体素地图、标定、TF、文档和录制。 | `robot_agent/memory.py` |
| 实际文件摄取与完整性 | 已完成 | 读取实际字节，保存哈希、大小、格式和来源；读取时复核哈希。 | 资产完整性测试 |
| 时空和地图元数据校验 | 已完成 | 空间资产要求 robot/frame/clock/timestamp，图像引用标定，地图携带版本。 | `test_missing_spatial_metadata_is_rejected` 等 |
| 资产父子关系 | 已完成 | 派生资产引用存在且完整的父资产，不接受悬空标定。 | Memory 查询测试 |
| MCAP 记录 | 已完成 | 保存实际消息字节、schema、channel、采集/接收时间并可重读。 | `tests/test_recording.py` |
| rosbag2 录制适配 | 已完成 | 使用实际安装的 sqlite3 插件录制并重开统计；缺失 topic/插件/零消息明确失败。 | [ROS 记录证据](validation/ros-recording.json) |
| 基础记忆目录与检索 | 已完成 | 语义条目引用有效资产，支持结构化条件和文本查询。 | `Memory.remember/search/query_assets` |
| 真实 RGB/深度/点云/地图流 | 未完成 | 当前机器只验证 ROS2 诊断消息，没有机器人传感器 topic 和高频数据证据。 | 台账 Q09；需实际 topic、标定、频率和样本 |
| 地图对齐与版本失效传播 | 未完成 | 已保存 frame/version/父关系，但没有重定位、回环后的计划和记忆失效机制。 | 台账 Q10/R08；需实际 TF/地图版本链 |
| 自动分类、矛盾和实体合并 | 未完成 | 没有分类器、冲突消解、实体合并或遗忘策略。 | 台账 Q11；必须保留来源并用真实数据验证 |
| 向量检索和场景图 | 未完成 | 未集成向量库、Hydra/Spark-DSG 或 ConceptGraphs。 | 台账 R09；先用实际检索问题证明需求 |
| 数据保留、配额与背压 | 未完成 | 没有保留周期、磁盘配额、磁盘满策略、流量背压和丢帧记录。 | 台账 Q12/R07；需数据预算和负载测试 |

## 9. 解耦 UI 与观察 API

| 细项 | 状态 | 当前情况 | 证据或完成条件 |
|---|---|---|---|
| 独立只读观察 API | 已完成 | 原观察服务只用 SQLite `mode=ro/query_only`，GET-only，不导入 Runtime/DBOS；测试网关单独启动。 | `robot_agent_observer/server.py`、`tests/test_observer.py` |
| UI 真实问答测试 | 已完成 | 自由输入问题、可选预期答案、实际回答/耗时/模型/响应 ID、持久历史；复用 `ModelCaller.qa`，服务端环境读取密钥。真实浏览器提问返回 `645`，耗时 2505 ms。 | [启动与验收](MODEL_TEST_UI.md)、`ui/scripts/test-model-ui.mjs` |
| 任务流程可视化 | 已完成 | 展示任务 DAG、节点状态、实际尝试、fallback、停止证据、计划历史和事件。 | `ui/src/TaskView.tsx`、Chromium 验证 |
| 资源/资产/记忆/模型页面 | 已完成 | 全部读取实际账本；无记录时显示空状态，不生成示例结果。 | `ui/src/App.tsx`、[UI 验证](UI_VALIDATION.md) |
| 断连和数据过期提示 | 已完成 | 断开 API 后保留上次快照并明确标记过期；API 在线不推断 worker/机器人在线。 | Playwright 断网测试 |
| 响应脱敏和浏览器整数保真 | 已完成 | 过滤已知配置敏感字段，纳秒等大整数用十进制字符串返回。 | `robot_agent_observer/ledger.py`、observer 测试 |
| 任务控制与编辑 | 进行中 | 已有共享 command API、权限、幂等控制、计划草稿及实际状态展示；真机停止交互尚需现场验收。 | 台账 U01；应用层及浏览器实际验证 |
| worker/机器人健康状态 | 未完成 | 当前显示 `unobserved`，没有心跳来源和失联判定。 | 台账 U02 |
| RGB/深度/点云/地图预览 | 未完成 | 当前只展示元数据和证据关系，没有解码、3D 或视频播放。 | 台账 U03 |
| 大规模详情查询 | 进行中 | 列表和事件已有分页；任务执行/历史详情、索引和推送尚未完善。 | 台账 U04 |
| 跨机器认证与访问 | 未完成 | 服务只绑定 loopback，没有认证代理或模型原文访问策略。 | 台账 U06 |

## 10. 测试、验证与工程质量

| 细项 | 状态 | 当前情况 | 证据或完成条件 |
|---|---|---|---|
| Python 软件验证 | 已完成 | 已有分模块实际文件、账本、HTTP、进程与真实模型验证记录；各记录仅覆盖对应版本和范围，不代表当前全量测试结果。 | [验证记录](VALIDATION.md)、[上下文包](validation/context-codec-live.json)、[事件分页](validation/event-pages-live.json) |
| 浏览器验证与构建 | 已完成 | 观察页面及应用工作台的会话、记忆、摘要、自动诊断、事件分页已有实际浏览器证据；以各次报告限定覆盖范围。 | [UI 验证](UI_VALIDATION.md)、[事件工作台](validation/event-browser-live.json) |
| 实际文件与 HTTP 验证 | 已完成 | 文件摄取、哈希、fallback、分块复制取消及真实部分文件均有记录。 | 第一版及 UI 验证文档 |
| ROS2 软件接入验证 | 已完成 | topic 发现和诊断日志录制通过；只证明软件通路。 | [VALIDATION.md](VALIDATION.md) |
| 实际模型端到端验收 | 进行中 | 文件任务已通过真实模型、worker 执行及最终字节核验；更多任务族与机器人现场仍待验证。 | [多文件任务](validation/multifile-live.json)、[恢复预算](validation/recovery-budget-live.json) |
| 实际机器人技能验收 | 未完成 | 无底盘/机械臂等真实执行和停止证据。 | 至少一项真实机器人任务全链路记录 |
| 实际多模态现场验收 | 未完成 | 无 RGB-D、点云和地图的持续真实流验证。 | 实际传感器数据、标定、吞吐、丢帧和存储记录 |
| CI 自动化 | 未完成 | 当前仓库没有本框架的独立 CI 结果作为证据。 | 配置可重复安装、Python/UI 检查和报告归档 |

## 当前构建阶段

详细依赖、交付物和退出条件见 [BUILD_ROADMAP.md](BUILD_ROADMAP.md)。

| 阶段 | 状态 | 当前目标 |
|---|---|---|
| 0. 可运行骨架与事实边界 | 已完成 | 第一版核心、只读 UI、调研和既有软件验证。 |
| 1. 执行权威与恢复闭环 | 进行中 | HTTP 文件服务 fencing/reconciliation 已验证；继续补偿/人工接管及设备端验收。 |
| 2. 真实机器人技能纵向切片 | 未完成 | 接入至少一项实际技能，验证执行/查询/取消/停止及最终条件。 |
| 3. 真实模型长程规划 | 进行中 | 文件任务及有界恢复闭环已验证，扩展任务族和机器人规划质量。 |
| 4. 多模态数据与长期记忆 | 未完成 | 接入真实传感器，完善背压、地图失效和语义策略。 |
| 5. 操作控制与可视化扩展 | 进行中 | 共享 command API、工作台和分页事件已有验证；心跳、实际传感器预览与远程部署仍缺。 |
| 6. 生产部署与多机器人 | 未完成 | 验证生产持久化、高可用和多机器人协调。 |
| 7. 陌生环境长程场景验收 | 未完成 | 用自主探索与目标趋向导航检验整个框架。 |

## 维护规则

1. 每次实现或验收后更新本文件的日期、对应细项和当前工作队列；不要只更新总体结论。
2. “已完成”必须给出代码或实际验证证据；只有接口、schema 或研究材料时不能把完整能力标为完成。
3. 已实现但缺真实场景验收的条目保持“进行中”，并写清已完成的软件范围。
4. 新问题先写入 [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md)，再在此处增加对应状态；关闭问题时保留关闭证据。
5. 同步更新 Momo 正式快照、`WORKLOG.md`、`UNKNOWNS.md` 和 `HANDOFF.md`，并检查来源指纹和关系健康。
6. 历史测试报告不因状态更新而改写。当前离线回归 41 tests / 9 subtests 通过、live model 1 项默认跳过；显式启用的 `qwen3.8-max` 真实问答 1 项通过。既有 4 项浏览器回归和生产构建结果保留；项目环境没有 `.venv/bin/ruff`。没有新增机器人验收。

工作台记忆选择证据：[memory-browser-live.json](validation/memory-browser-live.json)。不自动调用模型；显示来源完整性与文字内容的区别。实际模型计划使用选中记录中的文件路径，worker 最终哈希验证通过。

分块摘要增量证据：[chunked-session-summary-live.json](validation/chunked-session-summary-live.json)。普通/大历史2项真实模型到实际文件执行通过；首块调用期间实际修改会话的用例通过，后续块未发送、不完整摘要未绑定。

自动预算证据：[automatic-session-budget-live.json](validation/automatic-session-budget-live.json)。目标分析与规划两个入口的实际模型/文件执行路径通过，默认拒绝、固定内容超限不发送、正常预算不重复摘要及会话版本检查均有验证。

工作台历史摘要与预算证据：[summary-browser-live.json](validation/summary-browser-live.json)。真实浏览器完整链路已通过，并验证持久策略、原文来源及损坏提示；不代表机器人执行完成。


恢复预算实现增量：新增 recovery_budget.py，在提交时不可变会话快照上执行预算预检和分块摘要，保持固定原文、最新任务账本及绑定记忆；派生快照记录父快照哈希，不修改当前会话或原始提交快照。每次摘要调用前后及规划返回后校验任务版本、原快照和控制请求。策略关闭或必需上下文无法容纳时拒绝调用；同一覆盖范围的既有摘要仍不适配时明确拒绝，不递归压缩。普通及预算受限恢复已完成真实模型、实际文件故障和 worker 哈希验证；实际摘要期间取消已通过真实模型并发验收：保留响应，不创建派生快照或修订计划，worker 最终取消任务。证据见 [恢复预算验证](validation/recovery-budget-live.json)。完整长程任务族、世界状态与真机验收仍未完成。


Provider 拆分增量：目标/能力、任务账本、会话、记忆、资产、界面选择已迁移至统一 ContextProvider 接口；Manifest 保存 Provider 名称和接口版本。新增实际文件执行/选择/证据损坏与跨 robot 拒绝测试。世界状态来源仍缺失，当前 ROS2 发现只含诊断主题，不将普通资产当作实时观测。接口说明见 [CONTEXT_PROVIDERS.md](CONTEXT_PROVIDERS.md)。

Provider 接口验收：31 项实际文件/账本回归及 9 个子测试通过；2 项环境真实模型闭环通过（记忆驱动规划、超预算快照恢复），均由 worker 完成文件哈希验证。实际 Manifest 已逐项核对 Provider 名称及接口版本。证据：[context-providers-live.json](validation/context-providers-live.json)。


快照版本增量：统一读取器接入 Builder、草稿提交、worker 应用和恢复；新记录写入 v1，检查原文/目标哈希、整体绑定及派生谱系。4 份真实旧记录只读兼容验证通过。尚未完成整个上下文序列化体系及世界状态/真机验收。

快照实际验收：[context-snapshot-live.json](validation/context-snapshot-live.json)。环境真实模型的摘要恢复与快照变更拒绝两条链路通过；已接受的原计划实际执行并验证文件哈希，损坏快照命令未创建任务。38 项回归与 9 个子测试通过。


事件自动化增量：新增 automation.create/set-enabled/list/runs 共享动作和独立 automation-worker；实际失败事件按创建者与机器人范围持久入队，游标/预算/去重原子提交。实际模型解释引用精确错误和事件，未改变失败任务状态；queued 跨进程恢复、两个并发 worker 仅一次调用、暂停/范围/事件完整性检查通过。调用中 SIGKILL/SIGINT 与显式重新诊断已有增量验收；工作台操作已有下述真实浏览器验收；其他中断窗口、定时条件和自动恢复执行仍未验收。使用见 [EVENT_AUTOMATIONS.md](EVENT_AUTOMATIONS.md)，证据见 [event-automation-live.json](validation/event-automation-live.json)。


进程中断增量：实际 SIGKILL 和 SIGINT 后原请求均保持 unresolved，重启不重发；后续真实失败事件和 automation.retry 的实际模型响应已验证。重新诊断保留 retry_of、创建者及原不确定记录，受同一预算和幂等键约束。响应与诊断终态现以同一事务提交。证据：[automation-interruption-live.json](validation/automation-interruption-live.json)。供应商是否接收被中断请求仍未知，不能把缺失响应解释为未调用或已成功。


自动诊断工作台增量：创建、暂停/启用、诊断详情和显式重新诊断已接通；真实浏览器经共享动作创建规则，实际文件失败入队、来源损坏拒绝后重新诊断获得真实模型响应，刷新/轮询无额外模型调用。实际断开应用服务后保留上次诊断。证据：[automation-browser-live.json](validation/automation-browser-live.json)。世界状态和真机验收仍未完成。


上下文隔离与诊断增量：Builder 为各 Provider 隔离嵌套输入，拒绝调用期间的输入修改，并将返回片段与调用方对象分离；规划/重规划 Manifest 保存 Provider 返回、纳入及预算丢弃清单。22 项实际文件/账本回归通过；环境真实 qwen3.7-plus 的目标分析及两次规划均取得有效原始响应，独立 worker 完成文件归档及哈希核验，记忆过期后的命令拒绝执行。证据见 [context-isolation-live.json](validation/context-isolation-live.json)。这不是 Provider 沙箱或完整 Context 序列化迁移；世界状态与机器人验收仍未完成。


完整上下文包增量：新增 context_codec.py，提供 ContextBundle v1 编码与严格读取；规划/重规划保存完整包和绑定哈希，并使用解析后的片段生成模型输入。36 项回归通过；环境真实 qwen3.7-plus 完成目标分析和两次规划，两份持久包均能精确重建实际 messages 与 response_format。独立 worker 完成真实文件归档及哈希核验；未知快照版本和提交后快照变化均拒绝。证据见 [context-codec-live.json](validation/context-codec-live.json)。旧模型记录不补造 Bundle，解码不授予执行权限；世界状态和真机验收仍未完成。


多文件任务增量：新增内置 asset.verify-set，逐项核对实际资产字节和调用方预期哈希，拒绝重复资产、损坏数据及跨机器人范围。41 项真实文件/账本回归通过；环境真实 qwen3.7-plus 完成目标分析和七节点计划，独立 worker 完成三个复制、三个归档及一次集合核验，随后独立重读六份产物验证哈希。证据见 [multifile-live.json](validation/multifile-live.json)，范围见 [多文件验收](MULTIFILE_VALIDATION.md)。这是一个明确约束的真实任务样本，不代表统计规划质量或真机验收。


HTTP fencing 增量：显式控制域、单账本单调令牌、执行端持久权威检查和回执绑定已接通；要求同名独占资源。17 项真实 HTTP/文件/控制回归通过；新增 worker 恢复后第二执行令牌递增验证通过。真实环境 qwen3.7-plus 的目标分析、规划、独立 worker 远端文件执行与哈希核验通过。证据见 [fencing-live.json](validation/fencing-live.json)。旧令牌拒绝保持 Runtime unknown 和资源占用，不冒充停止；机器人驱动、多主仲裁及硬件急停仍未验收。


旧执行停止核对增量：当前较新控制者可显式请求 reconcile，服务端调用实际 cancel 并保存停止证据；旧执行只读回取结果后，Runtime 才解除未知状态并按真实终态释放资源。12 项真实 HTTP/控制回归通过，覆盖错误令牌、重复核对和服务重启；真实环境 qwen3.7-plus 的计划实际复制 512 字节后被接管，核对后独立 worker 结束为 canceled，部分字节保留且无成功冒报。证据见 [fencing-reconciliation-live.json](validation/fencing-reconciliation-live.json)。机器人停止、多主仲裁和自动接管仍未完成。


事件分页增量：共享 task.events-page 提供任务绑定游标、固定读取上界和 1–500 条分页，保留原 task.events。8 项实际 HTTP/文件回归通过（3 项其他实时模型测试未在该命令中运行）；本轮真实 qwen3.7-plus 七节点文件任务完成后，分页结果与完整账本逐条相等，重复读取不新增模型请求或执行。证据见 [event-pages-live.json](validation/event-pages-live.json)，协议见 [事件分页](EVENT_PAGES.md)。尚未迁移前端或接入推送，不宣称任意历史删改检测。


工作台事件增量：已接通任务选择、每页 50 条、手动后续页及读完后的增量轮询；断连保留记录，切换任务/凭据清理旧上下文。真实浏览器验证使用已有实际模型任务的账本副本（17 条事件）及实际暂停/恢复和文件执行产生的 69 条事件，验证两页加载、服务重启、去重及权限上下文清理；浏览器未新增模型或执行记录。构建通过，独立界面审阅对列出的可读性修正给出 ship。证据见 [event-browser-live.json](validation/event-browser-live.json)。本次不增加模型生成或真机验收声明。


失败节点解释追溯增量：task.explain 在发送真实模型请求前，原子保存完整 ContextBundle、哈希、来源/预算 Manifest 和请求准备参数；实际缺失文件执行失败后，环境 qwen3.7-plus 返回的解释通过文件名、错误含义及来源引用检查。保存包重建的 messages 与 response_format 和实际请求一致，任务保持 failed。1 项真实模型测试（4 条实际响应）及 23 项实际文件/账本/HTTP 回归通过；证据见 [explanation-context-live.json](validation/explanation-context-live.json)。此范围不包含其他模型方法的统一追溯、旧记录回填、世界状态或真机验收。


目标分析与澄清追溯增量：预算预检现在返回完整 ContextBundle，goal_analysis 和 goal_clarification 保留来源诊断，并在网络调用前原子保存 Bundle/哈希、Manifest、实际请求及准备参数；直接调用没有 Provider 时不补造诊断。实际多轮验收发现并修复澄清参数经持久化改变 JSON 键顺序、导致实际提示无法精确重建的问题。普通文件闭环、澄清/失败解释、自动摘要后文件闭环三条通过路径共保存 13 条真实模型响应；23 项实际文件/账本/HTTP 回归通过。首次失败与修复后重验分别保留，见 [goal-context-live.json](validation/goal-context-live.json)。详细边界见 [模型上下文证据](MODEL_CONTEXT_EVIDENCE.md)；摘要/自动化完整 Bundle、世界状态和真机闭环仍未完成。


自动诊断上下文包增量：explain_event 已保存完整 ContextBundle v1、哈希与准备参数，并在真实网络调用前同 Manifest、requesting 记录原子提交。上下文只表示绑定的历史事件，不附会当前任务 revision/generation，不补造 Provider 诊断。实际事件诊断、SIGKILL/SIGINT 中断和显式重试共 4 项专项通过，另有 23 项实际文件/账本/HTTP 回归通过；5 条实际响应与原错误一致，2 条中断请求保持 unresolved，7 份输入均准确重建且来源事件哈希与账本一致。证据：[automation-context-live.json](validation/automation-context-live.json)。供应商是否接收中断请求仍未知；摘要完整追溯、世界状态、真机和 Momo 同步仍未完成。


会话/恢复摘要追溯增量：每个分块使用 data 权限的 summary-source 片段，完整包、Manifest、来源字符范围/哈希、请求准备参数及实际消息在模型调用前原子保存。分块预检与发送统一构造；恢复摘要绑定原规划快照与任务版本，已有编辑/取消 guard 保留。四条通过路径共 15 条真实模型响应、8 个摘要包；2 项实际文件任务完成哈希验证，1 项取消任务保持 canceled，并发编辑路径拒绝绑定旧摘要。23 项实际文件/账本/HTTP 回归通过。首次测试范围输入缺失及真实规划拒绝均保留，修正真实前置输入后重验相关路径；详见 [summary-context-live.json](validation/summary-context-live.json)。这些记录不代表跨提示版本重放、实时世界状态或真机验收，Momo 同步仍待完成。


上下文只读查询增量：观察服务新增 GET /api/v1/models/{id}/context，同一读事务展开已有 Bundle/Manifest，并报告包哈希、引用与 request/phase 关联问题。实际模型账本副本 HTTP 查询、完整读前后对比、缺失/损坏注入与真实旧记录检查通过，相关 7 项测试通过；本轮新增模型调用为 0，没有执行任务。证据：[context-observer-live.json](validation/context-observer-live.json)。该接口不是完整请求重建、Manifest 全文认证或前端页面交付；真机、WorldState、其他工程范围及 Momo 同步仍待完成。


### 2026-09-22 上下文差异查询增量

单记录上下文面板已完成真实账本浏览器验证及独立界面审查（ship），见 [context-browser-live.json](validation/context-browser-live.json)。另新增两记录上下文差异只读 API，按明确方向比较身份、来源、内容哈希、预算与诊断，不推断调用血缘；缺失或损坏证据明确不可比较。真实历史模型账本 16 组比较及实际 HTTP/文件/账本回归共 8 项通过，副本故障恢复后逻辑账本哈希与来源一致；无新增模型调用、mock 或仿真。证据：[context-diff-live.json](validation/context-diff-live.json)。双记录比较界面见后续增量；世界状态和设备闭环仍待完成，未同步 Momo 图。


### 2026-09-22 上下文双记录比较界面增量

模型记录页面已接入固定/输入/清除基准与明确方向的上下文比较，展示预算、来源、内容哈希、请求身份及诊断变化。切换任一记录清除旧结果，同组合断连保留上次结果并标明过期，缺失或损坏证据显示不可比较。真实浏览器读取 5 条历史模型记录，验证键盘操作、正反向与自身比较、未应用输入隔离、断连/重连、损坏/恢复和桌面/手机布局；无新增模型调用、mock、仿真、页面异常或浏览器写操作，最终账本哈希保持不变。构建通过；独立界面审查 disposition 为 ship、无实质修正，范围仅此增量。证据：[context-diff-browser-live.json](validation/context-diff-browser-live.json)。实体/完成条件契约、世界状态、实际设备闭环及 Momo 同步仍待完成。


### 2026-09-22 资产上下文版本绑定增量

新增 AssetBinding v1，session.attach-assets 绑定真实登记记录与字节身份；Provider、草稿发布、提交、worker 接受及新技能派发复核资产。旧非空 ID-only 附件不会自动回填，需要显式重新附加并生成新草稿；历史可读。真实环境 qwen3.7-plus 的 4 条响应输入准确重建，元数据/字节变化分别在提交、命令处理、派发与恢复处被拒；恢复后实际 worker 核验资产字节/大小/哈希通过。专项 1 项、相关回归 37 项通过，无 mock 或仿真。证据：[asset-binding-live.json](validation/asset-binding-live.json)。此引用只代表归档资产，物理实体定位、世界状态和通用完成条件仍未完成；Momo 未同步此增量。


### 2026-09-22 显式完成契约增量

新增操作者 v1 completion_contract，独立于模型计划，绑定最终注册 verifier 的输出检查；会话设置会使旧分析/草稿失效，任务接受后冻结，修订与恢复保留契约。Runtime 区分技能 reported_status 与任务 completion_evaluation，实际验收不满足时即使技能成功也记为失败。真实模型+独立 worker 的原文件/规划后实际修改文件两条路径通过：一成功、一按哈希/大小要求失败；通过运行 4 条真实响应均重建输入，首轮退出码断言纠正记录保留（两轮共 8 条响应）。专项 1 项、相关回归 40 项通过，无 mock 或仿真。证据：[completion-contract-live.json](validation/completion-contract-live.json)。契约仍需操作者显式提供，不代表自然语言目标自动覆盖、物理任务指标、世界状态或硬件闭环完成；专用编辑 UI 与 Momo 同步仍待完成。


完成契约恢复专项：新增真实模型验收，实际修改主文件导致归档技能成功但任务哈希/大小验收失败；模型接收真实检查差异与冻结要求，改用操作者授权备用文件，独立 worker 完成原字节归档和核验。接受任务后清除当前会话契约不影响恢复要求。三条实际响应输入准确重建，专项 1 项通过、相关回归 40 项通过，无 mock、仿真或生产逻辑改动。证据：[completion-recovery-live.json](validation/completion-recovery-live.json)。范围限一个文件恢复场景；世界状态、物理实体和真机闭环仍未完成。


动作发现契约增量：GET /actions 增加 catalog_version 与每动作版本、哈希、副作用类别、幂等/模型调用行为声明；审计记录关联实际使用的契约，发现结果保留独立 schema 副本。仍按基础权限筛选，实际调用继续检查机器人范围和状态。真实 HTTP 发现→提交→独立 worker→文件 SHA256 验收通过，同时覆盖认证、缺失幂等键与跨机器人拒绝；相关 17 项通过，无新增模型调用、mock 或仿真。详情见 [应用层说明](APPLICATION_LAYER.md)。不代表所有嵌套输出 schema、远程多租户、世界状态或真机已完成。


世界状态接入复核：实际 ROS 图发现仅检查节点自身诊断发布者，未发现设备节点或 Action；已审阅相邻工程真实 G1 状态/运动桥并归档源码哈希。明确接收时间与采样时间、默认 covariance、坐标/速度语义及执行身份/停止证据缺口，见 [G1 接入契约](G1_INTEGRATION_CONTRACT.md) 和 [发现记录](validation/world-source-discovery.json)。无桥接启动、mock、仿真、运动或新增模型调用；世界状态与真机仍待实际连接信息及现场验收。

跨动作幂等修复：实际复现自动化与会话可重复占用同主体请求键；现统一写事务内的键归属检查，保留历史自动化 ID，冲突返回 409。25 项实际文件/HTTP/账本回归通过；真实自动诊断专项 1 项通过、一次环境模型调用且输入准确重建，旧真实账本重放兼容验证通过。证据：[action-idempotency-live.json](validation/action-idempotency-live.json)。无 mock 或仿真；分布式键归属、世界状态及真机不在本次验收范围。
