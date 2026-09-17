# 决策

Confirmed：用户批准正式 Momo 单项目注册并开始实现。外部上游继续作为来源，不纳入源码所有权。
Confirmed（实际代码与安装）：DBOS 2.31.0、py_trees 2.5.0 条件链、MCAP 1.4.0、jsonschema、httpx；本机 Python3.10/ROS2Humble。
Inference：本地 SQLite DBOS 适合这一轮单进程实现验证；不据此断言生产分布式部署已就绪。
Confirmed：恢复只查询原 execution_id；停止证据通过前不释放控制资源；自动重规划不能覆盖用户取消或较新 generation。
Confirmed：rosbag2 使用实际安装的 sqlite3；缺失 mcap 插件时明确拒绝。DimOS memory 和向量/场景图尚未集成。

## 2026-09-06 UI 边界

Confirmed：按用户指令停止使用 superpowers，直接实施；继续维护原 Momo 单项目。选择独立 React 前端和只读观察服务，仅通过版本化 DTO 通信；不导入或启动 Runtime/DBOS。SQLite 不初始化缺失账本。API 连接不能作为机器人在线证据；历史契约未保存就显示不可用。
Confirmed：默认端口 8765 已占用；本次查看服务显式使用 8766，读取独立真实文件验证账本。

## 2026-09-06 工程状态同步

Confirmed：用户要求更新当前维护的工程状态文件。本轮统一 Momo 对象摘要、PROJECT/HANDOFF、问题台账、README 与研究材料的状态入口；保持单一项目、既有关系与总体 in_progress。历史验证保留原始日期和结果，不以文档更新冒充重新验收。

Confirmed：本次只读请求确认 8766 的页面与 overview 返回 200，具体时间与摘要保存在 docs/validation/status-check.json；它只证明核对时刻观察服务可达。

## 2026-09-06 依据问题台账修正模块状态

Confirmed：用户要求结合 docs/OPEN_QUESTIONS.md 更新工程状态。按原文覆盖 13 条基础、11 条调研扩展和 6 条 UI 问题，不修改其原始条目；逐项注明状态、关联模块和关闭证据。编号仅用于追踪，不代表用户批准的优先级或排期。

Confirmed：台账仍列有控制端隔离、恢复补偿、数据保留/背压及地图/记忆策略等工作，因此“任务执行与控制权”和“原始记录与证据目录”的完整模块状态为 in_progress；保留第一版验证通过，不将此修正表述为实现回退。只读 UI 已完成的交付范围保持 done，其后续功能保持 open。整个项目并非只等现场接口。

Confirmed：候选框架、完整行为树、向量库、DimOS memory 及生产多机部署是待需求/证据判断的扩展，问题台账不构成全部采用的决定。Momo 维护为持续事项，本轮没有新增关闭问题。

## 2026-09-06 统一工程状态文档

Confirmed：根据用户澄清，`docs/PROJECT_STATUS.md` 成为详细工程状态的统一入口，按模块和细项使用“已完成、进行中、未完成”三种状态，并记录证据或完成条件。`OPEN_QUESTIONS.md` 继续管理问题，不承担完整状态表；Momo `PROJECT.md` 只保留摘要和指针。

Confirmed：状态按具体能力判断，模块总状态由未关闭细项决定。第一版只读 UI 的已交付细项保持完成，但 UI 模块因控制、心跳、数据预览等仍缺而总体进行中；相同规则适用于编排、恢复、资源、模型、存储和验证模块。

## 2026-09-07 分阶段构建与历史契约

Confirmed：工程按“执行权威与恢复闭环、真实机器人技能纵向切片、真实模型长程规划、多模态数据与长期记忆、操作控制与可视化、生产部署与多机器人、陌生环境场景验收”的依赖顺序推进。探索与目标趋向导航继续作为组合验收场景，不侵入框架核心或替代下层算法。

Confirmed：阶段 1 先关闭 U05。计划修订历史保存对应的 plan、steps、catalog、revision、generation 和时间；UI 读取历史 catalog，旧账本缺失字段时明确不可用。新增回归先在旧实现上失败，修复后 31 tests / 9 subtests、前端构建和 4 项 Chromium 回归通过。下一项实现控制权 fencing。

## 2026-09-07 实际模型配置

Confirmed：模型 API 密钥只从 `API_KEY` 环境变量读取；URL 与模型显式配置，用户在服务目录确认结果后选择 `qwen3.8-max`。本地配置与原始响应只保存在被 Git 忽略的 `.runtime`，版本化验证记录不保存密钥或 endpoint。

Confirmed：保持严格计划契约，不接受模型返回的对象型 `verification`。通过更明确的提示要求顶层 `verification` 为最终 verifier 步骤 ID 字符串；实际重试得到合法两步 DAG。该决定不把模型规划成功扩大为任务执行成功。

Confirmed：大模型响应验收以真实 API 问答和独立可计算期望值为准；本地模拟服务只证明请求/解析/契约边界。live test 必须显式设置 `RUN_LIVE_MODEL_TESTS=1`，不纳入默认离线 API 消耗。

## 2026-09-07 模型流转图范围

Confirmed（用户请求）：在现有单一项目内独立展示模型调用和上下文流转；沿用 model-adapter 作为容器，不另建项目、不迁移原节点或删除旧关系。Confirmed（代码）：UI 历史不自动进提示词；自动重规划仅注入选定任务状态。未实现的连续会话、摘要检索和预算继承修复只记录，不声称已接通。

## 2026-09-08 详细目标架构

Inference（高置信，待后续实现逐项验证）：依据用户已确认的单机器人优先、长程编排、真实结果、多模态记忆和开源复用目标，以及当前 Runtime、技能和账本实现，目标架构采用“模块化 Agent 控制平面、机器人适配平面、证据数据平面、独立安全平面”。LLM 只产生计划候选；Runtime 是任务和资源状态权威；控制端 fencing 决定物理执行权；独立 verifier 判断目标完成。

Confirmed：本轮只生成和链接 `docs/DETAILED_ARCHITECTURE.md`，没有实现目标架构中尚缺的 fencing、补偿、ROS2/Unitree 技能、独立验证、多模态现场流或多机器人能力，也没有改变其工程状态。

## 2026-09-11 当前任务拆分流程

Confirmed（代码与验证记录）：当前 Agent 任务拆分是“一次性受约束 DAG 生成、确定性双层校验、失败后有界整计划修订”。首次 `submit_goal` 不自动注入会话或记忆上下文；`recover_plan` 注入 previous_plan、step_results 和 revision。当前不是 Pi Agent 风格的连续工具循环，也没有边执行边递归创建子任务。

Confirmed：流程图同时保存为 Mermaid 文档和 Graphviz SVG；只记录现有行为，不改变任务规划代码或能力状态。

## 2026-09-12 上下文第一轮范围

Confirmed（用户决定）：第一轮先完成必须的上下文基础框架。GoalContext 不只是把自然语言转为 JSON，而要保留原始输入并显式表达解释、歧义、疏漏、假设、感知获取和人工澄清；TaskStateContext 采用层级分解与 DAG 关系并存的图模型。第一轮不优先引入向量记忆和实时世界状态。

Confirmed（用户决定）：完整自动语义完善延后到整体对话记忆之后；当前先交付初步模型分析与问讯，并为分析和问讯分别使用独立 System Prompt。当前实现保持该入口与任务提交分离。
