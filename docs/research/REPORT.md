# 机器人 Agent 框架开源调研与复用建议

调研日期：2026-09-05。阶段：研究完成首轮，选型与真实集成尚未完成。

## 结论与证据边界

建议采用现有组件组合，在本项目中实现机器人执行契约与跨组件协调层。暂不继续初稿中自研全部调度、持久化和记忆后端的路线。最值得进入下一轮验证的是 DimOS、RAI/EMOS、Temporal/DBOS、BehaviorTree.CPP/py_trees、Open-RMF 的任务生命周期，以及 rosbag2/MCAP。

本轮成功定位并固定了 41 个仓库的 HEAD，包含一个许可证为 BSL 的源码可见对照项 Restate；另保留一个错误仓库身份的查询失败记录。范围涵盖机器人 Agent、行为执行、符号规划、持久工作流、模型编排、数据记录、空间和语义记忆。完整逐仓库判断见 [复用矩阵](REPOSITORY_MATRIX.md)，固定提交、上游路径、获取错误和文件哈希见 [inventory.json](inventory.json)。

证据分两级：全部有效仓库读取 README 与许可证；重点组件进一步读取具体实现或接口。没有安装运行这 41 个仓库，没有执行机器人或真实模型联调，也没有证明性能、兼容性或生产可靠性。下文“建议”“候选”为架构判断，不是已实现能力。HEAD 作者/提交者日期只是一个提交的时间，不等于发布版本、维护频率或支持承诺。匿名 GitHub API 限流后使用 git 与固定 SHA 原始文件，不推断星数和发布状态。

## 对原方案影响最大的发现

### 1. DimOS 应重新按最新版评估，尤其是记忆层

当前上游已有类型化 Stream、ObservationStore、BlobStore、VectorStore 和通知机制，支持时间、位置、标签、文本及向量查询；还提供 SQLite 元数据实现及流量积压策略。它比“自己设计一层资产数据库”更值得先验证。当前代码中的 `SkillResult` 有 success、错误码和 metadata，可以适配统一技能结果，但该结构自身没有强制独立后置条件验证。`core/resource.py` 管理 start/stop/dispose 生命周期，不能据名称认定它已经实现底盘等硬件资源的排他租约。[架构](sources/dimensionalOS__dimos/dimos/memory/architecture.md)、[技能结果源码](sources/dimensionalOS__dimos/dimos/agents/skill_result.py)、[资源源码](sources/dimensionalOS__dimos/dimos/core/resource.py)。

需要限制承诺：本次查看的 `memory/store/mcap.py` 是只读存储，没有 append、blob、vector 或 embedding 写入能力。介绍中部分 Rust SQLite 与 MCAP recorder 位于 experimental 命名空间。因此“支持 MCAP 读取”不能写成“完整生产级 MCAP 录制与记忆后端”。优先验证独立复用 memory 所需的依赖、编解码及其与现有 ROS2 消息的兼容性。[MCAP 源码](sources/dimensionalOS__dimos/dimos/memory/store/mcap.py)、[memory 介绍](sources/dimensionalOS__dimos/dimos/memory/intro.md)。

### 2. 机器人原生 Agent 能复用模型和工具接入，但仍需本项目的成功判定

RAI 已有 ROS2、多模态工具与规划/重规划实现。查看的 Plan 将步骤表示为字符串列表，结束条件接受非空 response；该控制流本身不能证明物理目标已完成。可复用工具描述和 ROS2 接入，需要把任务图、资源约束和可验证终态作为外部强约束。工具调用 benchmark 也不能代替真实动作验收。[RAI 仓库](https://github.com/RobotecAI/rai)、[工具文档](https://robotecai.github.io/rai/tutorials/tools/)。

EMOS 的 Embodied Agents 与 Sugarcoat 具有 ROS2 生命周期、事件与故障响应机制，适合组件级模型切换和健康恢复。它们的组件 fallback 与任务补偿、跨任务资源转交属于不同职责，应明确衔接，不能给同一个失败同时安排多套重试。[组件文档](https://agents.automatikarobotics.com/development/advanced_component.html)。OM1 继续作为输入、模型与动作连接层候选；其机器人底层接入涉及外部 SDK，不能把主仓库视为完整的机器人调度系统。

### 3. 长程持久化应复用工作流引擎，先比较 Temporal 和 DBOS

Temporal 的持久执行、历史与 Python SDK 值得优先评估；非确定性模型请求与机器人 IO 应放在 Activity 边界，恢复不能随意重放物理动作。DBOS 可用数据库支撑工作流、队列、优先级与并发约束，适合验证单机器人较轻部署。两者只能选一个作为长程执行状态和重试的权威所有者。[Temporal Python SDK](https://github.com/temporalio/sdk-python)、[DBOS 队列](https://docs.dbos.dev/python/tutorials/queue-tutorial)。

不能笼统说 DBOS 只能在步骤结束后取消：本次固定 HEAD 的实现存在异步 preemptible 步骤和取消监督逻辑。但取消 Python 协程仍不能证明远端控制器已停止；该 HEAD 功能是否进入拟采用发布版也需要验证。两者都不天然提供机器人动作的 exactly-once 保证。[DBOS 工作流管理](https://docs.dbos.dev/python/tutorials/workflow-management)、[固定源码目录](sources/dbos-inc__dbos-transact-py/)。

### 4. 打断必须有“已停止”的证据，参考 Open-RMF，而不只看 interrupt API

Open-RMF Task::Active 将 interrupt、cancel、kill、backup 分开：中断回调表示允许安全转交；cancel 可能经过清理阶段；kill 也不等于硬件急停。该接口是设计统一任务生命周期的重要参考，第一版无需因此引入整套车队系统。[rmf_task](https://github.com/open-rmf/rmf_task)。

ROS2 Action 区分 CANCELING 与 CANCELED。BehaviorTree.ROS2 的 halt 会请求 cancel 并等待相关 future，但存在超时路径；树节点停止不应直接释放机器人排他资源。需要读取真实终态、核对执行 ID，再按技能契约检查停止和后置条件。[ROS2 Action 设计](https://design.ros2.org/articles/actions.html)、[BT 异步节点](https://behaviortree.dev/docs/guides/asynchronous_nodes/)。

LangGraph interrupt 是模型编排暂停与恢复机制；恢复可能从节点开头再次执行，所以中断点之前的副作用必须处理幂等性。它适合规划循环，不单独承担机器人控制停止协议。[LangGraph interrupt](https://docs.langchain.com/oss/python/langgraph/interrupts)。

## 框架责任划分与复用顺序

| 层 | 优先候选 | 本项目必须掌握的契约 | 边界 |
|---|---|---|---|
| 目标、长程分解、重规划 | LangGraph 或 PydanticAI；RAI 工具与规划接入 | 结构化计划、技能白名单、依赖和资源校验、预算、目标验证、计划版本 | 模型提出计划，不能自行声明任务物理完成 |
| 持久任务调度 | Temporal 或 DBOS | 单一状态权威、优先级、资源申请、执行 ID、未知状态核对 | 工作流重试不等于动作可安全重发 |
| 技能行为与局部 fallback | BehaviorTree.CPP + ROS2，或 py_trees + py_trees_ros | 真实结果、超时、取消确认、恢复和后置条件 | 避免同时引入两种行为树内核 |
| ROS2/机器人组件 | 保留当前后端；评估 RAI、DimOS、Sugarcoat 的适配价值 | 能力清单、生命周期、健康事件和权限 | 不为换 Agent 框架重写现有导航或驱动 |
| 资源与打断 | 参考 Open-RMF，结合所选引擎的事务机制 | 多资源原子取得、租约和旧执行者隔离、优先级反转处理、停止确认后转交 | 工作流队列并发数不等于硬件资源锁 |
| 原始观测记录 | rosbag2/MCAP | 时钟、标定、TF、来源、缺帧、索引和校验 | 不向模型塞入全量传感器流 |
| 观测与空间记忆 | 先验证 DimOS memory；按需 Zarr、Spark-DSG | 数据血缘、地图版本、空间/时间查询、证据引用 | 向量库不承担原始数据真实性 |
| 语义和经历记忆 | DimOS 索引优先；LanceDB/Qdrant、Graphiti 按需 | 事实有效时间、置信度、矛盾、过期、源观测和任务事件 | LLM 摘要是派生结果，不能覆盖观测 |
| 调试和追溯 | Rerun + 引擎事件历史 + MCAP | 任务、计划、技能、观测、地图统一关联 ID | 可视化日志不是唯一执行账本 |
| 多机器人扩展 | robot_id 命名空间、能力发现；后续评估 RMF | 控制权和任务归属、资源作用域、时钟域 | 第一版完整处理单机，暂不部署车队基础设施 |

推荐优先比较三种集成路线：

1. **现有 ROS2 后端 + 可替换上层组件**：本项目负责契约；模型、持久工作流、行为树和记录各选一个合适组件。最有利于保留已有工程，但需认真处理跨组件取消和一致性。当前优先验证此路线。
2. **DimOS 为主**：复用模块、技能与记忆，减少自行建设；先确认最新依赖、消息格式、独立引入成本及接口演进风险。若 memory 无法低成本独立使用，再比较整体采用的收益。
3. **RAI/EMOS 为主**：有利于 ROS2 原生模型与生命周期管理；仍需补充持久执行、资源转交和可验证结果协议。RAI 与 EMOS 不同时默认引入。

这些是候选组合，不是已经批准的依赖清单。第一轮集成验证后再固定版本和选型。PlanSys2/Unified Planning 在需要可形式化领域时接入；SkiROS2/CRAM 的技能语义值得参考，但迁移成本与技术栈限制使其暂不作为默认基座。

## 多模态记忆如何分工

| 数据类别 | 保存与索引建议 | 必须保留的信息 |
|---|---|---|
| RGB、深度、原始点云 | MCAP 消息记录；大数组按需用 Zarr；按时间/传感器索引 | 原编码、单位、采集与接收时间、时钟域、frame、标定版本、缺失记录 |
| 点云地图、占据地图、体素地图 | 保存原生格式和不可变版本，构建派生关系；格式处理复用 Open3D/OctoMap 等 | 分辨率、坐标系、TF/定位版本、来源观测范围、算法参数、版本与失效条件 |
| 物体、位置、区域等空间语义 | 评估 DimOS 空间查询与 Spark-DSG，必要时扩展 | 实体 ID、几何引用、观测来源、有效时间、置信度、合并/冲突记录 |
| 任务与技能经历 | 持久工作流事件与原始返回；生成可追溯摘要 | 计划版本、执行 ID、结果、取消/恢复过程、证据引用 |
| 文本/视觉语义检索 | 按需求加向量索引 | embedding 模型与版本、源资产 ID、过滤字段；索引可以重建 |

Hydra、ConceptGraphs、nvblox 是可选的上游空间理解/重建生产者，不是第一版 Agent 内核的必需依赖。尤其 Hydra 当前说明测试环境为 Ubuntu 24.04/ROS2 Jazzy，不能直接推断与当前工程兼容。Graphiti/Mem0 也不能代替高频传感器与地图记录。

## 必须自行定义的最小协调层

- **目标与证据契约**：收到响应、结构合法、技能返回成功、后置条件满足、任务目标完成分别记录；空响应、解析失败、服务超时和未知状态不转换为成功。
- **执行身份与核对**：持久化 task/plan/step/attempt/execution ID；崩溃或网络断开后查询原执行。没有可核对协议的不可重入技能不能自动重发。
- **资源所有权**：底盘、机械臂、相机配置和计算预算按不同资源语义管理；多资源申请有统一顺序或原子协议；租约过期不自动等于物理资源已安全释放。阻止旧执行者继续控制需要适配器或控制端配合。
- **全局打断与局部恢复的协调**：明确任务暂停、取消、优先级抢占和急停的区别；记录停止请求与确认；fallback/补偿先满足资源及技能前置条件。持物等持续状态不能靠工作流回滚消除。
- **记忆血缘与证据绑定**：所有推理引用真实数据位置及版本，保留时空上下文；感知结果过期与地图重定位能够使旧计划重新校验。

以上“需要补齐”是对本轮审查范围的判断，不声称已经穷尽所有上游插件与扩展。

## 下一阶段验证门槛

1. 固定可部署版本：核对本机 Python、ROS2、OS、GPU、现有 action/service/topic 和技能返回协议。HEAD 不直接作为生产依赖。
2. 对 Temporal 与 DBOS 做真实进程/数据库恢复比较，记录重启、重复请求和取消的实际行为；用真实无机器人副作用的本地操作验证持久化，不将其计为机器人验收。
3. 选择一个实际机器人技能，检查接受、运行、终态、结果查询、取消和停止证据。无接入信息时标记未验证，不创建假技能成功补位。
4. 用实际模型端点取得任务分解响应；验证结构、能力边界、资源与后置条件。无端点时保持未验证，不用固定回复代替规划。
5. 用现有真实数据记录验证 MCAP 与 DimOS memory：时间/空间查询、编解码、重新打开、哈希、引用与地图版本。没有某类真实数据时如实记录覆盖缺口。
6. 根据结果只选择一个持久调度权威和一个技能执行后端，提交更新后的架构与实施计划，再进行大规模代码修改。

测试不得伪造模型回答、机器人状态或实验结论。非法输入和确定性契约检查可作为软件检查，但必须与真实联调结果分开记录。

## 项目管理

模块细节问题持续维护于 [OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md)。Momo 接管范围及拟写入内容见 [MOMO_INTAKE_PREVIEW.md](MOMO_INTAKE_PREVIEW.md)；候选图目前没有确认标记，正式注册等待首次范围确认。技术选型保持 Unknown，不因研究建议而变成 Confirmed。此前初稿与失败测试保留为工作记录，不能视为可运行框架。

## 后续状态

本报告记录研究当时的候选结论。用户随后已批准正式 Momo 注册和实现；当前已选择并集成的组件与验证边界见 [ARCHITECTURE.md](../ARCHITECTURE.md) 和 [VALIDATION.md](../VALIDATION.md)。报告中的“等待首次确认”“尚未生产包”等阶段表述仅描述历史状态。
