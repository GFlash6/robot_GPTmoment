# 工作日志

2026-09-05：用户确认正式接管和开始实现。建立 canonical revision1，应用8条语义关系到revision2，正式注册本项目。
随后实现契约、资源账本、资产记忆、MCAP、HTTP数据技能、DBOS、真实模型适配、CLI和rosbag2录制。
实际检查24 tests和9 subtests通过；包含真实HTTP文件复制/取消、SIGKILL worker后的原ID恢复。ROS2录制真实文件哈希诊断日志25条。
独立审查发现的任务发布、取消、资源别名、终态证据和迟到generation覆盖问题已修复并复查。
revision3更新对象和实现证据；revision4更新研究门槛为支持关系并添加7条实现/验证关系。15条语义关系，无孤立/无效/过期证据。
旧失败测试支持实现的提案已拒绝并保留审议历史；用当前软件验证源自初始测试的关系替代。已经存在的关系保留，不按工具pending中的relation-already-present提示重复创建。
没有宣布实际AI或机器人运动验收完成。

revision5同步总体目标进行中与历史基线标题，避免旧“尚未实现”描述误导后续工作；关系保持15条不变。

新增请求：用户要求解耦 UI 可视化各个流程。已检查现有任务/执行/资源/模型/资产账本，形成 docs/UI_DESIGN.md；独立只读运行台设计待确认，尚未创建 UI 生产代码。Momo 继续作为项目管理，不复用其 Web 来承载运行态。

UI 需求已录入正式图 revision7；新增工作项与支持关系，设计仍为 proposed，无孤立或无效关系。

## 2026-09-06 解耦 UI 交付

用户要求不再使用 superpowers、直接实施。本轮新增 React/TypeScript/React Flow 前端和独立 GET-only SQLite 观察服务；核心任务运行代码未因 UI 改写。展示真实任务 DAG、fallback 尝试、停止证据、资源、资产记忆与模型记录；缺失数据与断连明确显示。
实际验证：Python 30 tests、9 subtests；Vite 构建；Chromium 4 项测试。验证账本来自真实文件操作，不生成模型或机器人成功。截图与报告见 docs/UI_VALIDATION.md。
Momo revision 7→8 更新 UI 工作项并新增验证对象，8→9 添加证据支持 UI 的语义关系；更新已核实仍成立的 UI 设计/依赖文件指纹。现为 19 总对象、35 总关系；单项目与整体 in_progress 不变。

## 2026-09-06 工程状态同步（revision 10）

按用户要求核对当前代码、既有 JUnit/UI 验证、观察服务和 Momo 证据。更新 PROJECT、HANDOFF、UNKNOWNS、DECISIONS、QUIZ、README 与 OPEN_QUESTIONS；纠正问题台账中模型 HTTP 适配、持久执行和存储仍待选型的旧表述。仓库复用矩阵新增当前状态入口，保留研究时的候选判断；第一版验证记录明确指向后续 UI 验证。
实际只读检查：8766 页面和 overview 均返回 200，4 个真实文件任务（2 成功、1 失败、1 暂停）、0 条租用；未推断机器人在线。原始核对见 docs/validation/status-check.json。本轮未重跑功能测试，30 tests / 9 subtests、4 项浏览器与构建结果为既有验证。
正式快照 revision 9→10，更新 5 个对象摘要，未新增/删除关系；19 总对象、35 总关系保持不变。整体 in_progress，真实模型/机器人/多模态验收缺口仍保留。

## 2026-09-06 依据 OPEN_QUESTIONS 逐项同步（revision 11）

用户指定以 docs/OPEN_QUESTIONS.md 更新工程状态。本轮保留问题原文，覆盖 13 条基础、11 条调研扩展和 6 条 UI 问题；29 条未关闭、1 条持续维护，无新增关闭。每条均映射来源行/原文、当前状态、模块对象和关闭证据，保存于 .momo/intake/open-questions-status.json、PROJECT.md 与正式 questions 对象。
修正“第一版交付”被误读为“只差现场接口”的风险：单机器人、编排、记忆、实际判定需求，以及任务执行/控制权、多模态存储的完整模块保持进行中；已通过的软件验证独立保留。只读 UI 的原交付仍 done，后续问题为 open。
更新 PROJECT/HANDOFF/UNKNOWNS/DECISIONS/QUIZ 与 README。正式图 revision 10→11，更新 15 个对象，无新增或删除关系；19 总对象、35 总关系保持不变。仅检查状态、来源映射与图一致性，没有实现功能、重跑功能测试或重新检查服务在线。

## 2026-09-06 建立统一工程状态文档（revision 12）

用户澄清需要一份长期维护的状态文档，按模块和细节标明完成情况。新增 `docs/PROJECT_STATUS.md`，覆盖总体概览、10 个模块组、当前工作队列和维护规则；97 个状态单元中 49 项已完成、19 项进行中、29 项未完成。状态以具体行的范围为准，不按数量计算项目完成率。

README、OPEN_QUESTIONS、仓库复用矩阵和 Momo PROJECT 改为指向统一状态文档。Momo revision 11→12，更新 project、questions、momo 3 个对象及状态来源指纹；19 个对象、35 条关系不变。没有重跑功能测试，没有新增模型、机器人或传感器验收。

## 2026-09-07 建立构建路线并推进阶段 1（revision 13）

新增 `docs/BUILD_ROADMAP.md`，将工程按依赖拆成 0–7 阶段：先完成执行权威与恢复闭环，再接真实机器人技能、真实模型规划、多模态记忆、操作型 UI、生产与多机器人，最终以陌生环境自主探索和目标趋向导航作组合验收。`docs/PROJECT_STATUS.md` 增加当前阶段表；105 个状态单元中 51 项已完成、19 项进行中、35 项未完成，数量只用于状态维护，不表示完成率。

阶段 1 首项关闭 U05：`Runtime.revise` 的历史快照保存 plan、steps、catalog、revision、generation 和时间，UI 使用历史版本 catalog 并兼容旧账本。新增测试先复现旧实现缺少 revision/catalog，再修复通过；完整结果为 31 tests / 9 subtests、前端生产构建和 4 项 Chromium 回归通过，JUnit 保存于 `docs/validation/pytest-roadmap.xml`。项目环境没有 `.venv/bin/ruff`，没有声称该检查通过；没有新增模型、机器人或传感器验收。

正式图 revision 12→13，更新 project、kernel、questions、core-execution、software-validation、workflow-ui、momo 7 个对象，关闭问题映射中的 U05；19 个对象、35 条关系不变。关系审计无孤立对象、无效关系或过期证据。下一项为控制权 fencing。

## 2026-09-07 `qwen3.8-max` 实际规划联调

按用户指定从 `API_KEY` 环境变量读取密钥，显式配置 Chat Completions URL 和模型。`qwen3.8plus` 返回 404 `model_not_found`；用户改选服务目录中存在的 `qwen3.8-max`。首次 HTTP 200 响应把 `verification` 返回为对象，框架正确拒绝。新增本地 HTTP 边界测试先失败，再将提示明确为字符串步骤 ID，模型规划测试 5 项通过。

实际重试返回 HTTP 200，provider response `chatcmpl-5a31965e-d634-988c-aa08-9bc0e4b1d3fa`，实际模型 `qwen3.8-max`；生成 `ingest_readme -> verify_readme_asset` 两步计划并通过契约校验。本次没有执行该计划。脱敏证据见 `docs/validation/model-planning-qwen3.8-max.json`，原始响应仅在 `.runtime/model-validation/ledger.sqlite`。

用户进一步明确大模型响应测试必须以真实问答为标准。新增显式启用的 live model 测试，实际提问可独立手算的中文库存题，期望与模型回答均为 645；`qwen3.8-max` 真实调用 1 项在 7.15 秒通过。本地 HTTP 测试只保留为 Planner 协议边界回归，不计作模型质量证据。

默认离线全量回归为 32 passed、1 live model skipped、9 subtests passed；正式图 revision 13→14，更新 project、model-adapter、verification、software-validation、questions 5 个对象，19 对象和 35 关系总数不变。

状态计数校准后再以 revision 14→15 刷新 project/questions 的状态来源指纹；未增加、删除或改写关系。

## 2026-09-07 模型调用与上下文独立子图

按用户要求将既有 model-adapter 展开为「模型调用与上下文流转」，保留原主图关系，新增18个子节点、21条内部语义关系、18条包含关系和专用画布。说明配置、调用方法、片段预算、HTTP、结果校验，以及问答历史/规划证据/任务状态的不同用途。连续会话、摘要检索和重规划预算继承明确为开放缺口。

正式图 revision 15→16：37对象、74关系（38语义＋36包含）。21条新增关系通过确定性证据校验；原3处落后指纹核对后刷新。最终无孤立对象、无无效关系、无过期证据。没有修改模型运行代码，也未发起新的模型调用。细节见 docs/MODEL_CONTEXT_FLOW.md。

## 2026-09-08 生成完整目标架构

按用户要求不使用 superpowers，结合 `docs/PROJECT_STATUS.md`、用户需求、构建路线、技能协议、模型上下文、现有代码和第一轮开源调研，新增 `docs/DETAILED_ARCHITECTURE.md`。文档定义四平面、三时间尺度、组件职责、SkillSpec 目标契约、execution/fencing 字段、任务和执行状态机、正常/取消/恢复流程、G1 红色方块入抽屉案例、数据所有权、部署、安全、可观测性、测试故障矩阵和分阶段迁移。

外部架构依据只使用官方资料：ROS2 Interfaces/Actions/Lifecycle、Nav2 BT Navigator/Collision Monitor、MoveIt Task Constructor、Open-RMF Fleet Adapter/Task、DBOS Workflow/Queue 和 MCAP 规范。它们是机制参考，不代表本项目已集成所有组件。

同步 README、ARCHITECTURE、PROJECT_STATUS 和 Momo PROJECT 入口；PROJECT_STATUS 只更新文档日期和链接，没有改变任何能力状态。没有修改运行代码或执行模型、机器人、传感器验收。

工作前关系 inspect 显示正式图 revision 149、37 对象、74 关系、无孤立/无效/过期关系；但现有 relation assessment 基于 revision 16，validate/diff 明确拒绝。为避免在 revision 漂移下错误合并，本轮不更新 canonical 图或 relation assessment，将重新评估记为缺口。

## 2026-09-11 绘制当前 Agent 任务拆分流程

依据 `cli.py`、`runtime.py`、`planner.py`、模型调用组件、`contracts.py`、模型规划验证记录和项目状态，新增 `docs/TASK_DECOMPOSITION_FLOW.md`。主图覆盖 agent/plan/recover_plan 三个入口、技能能力裁剪、上下文预算、实际 HTTP 调用、响应拒绝、DAG 与 verifier 校验、Task 冻结提交和失败后的有界重规划；另记录首次规划与重规划差异、实际两步计划及未实现边界。

新增 `docs/diagrams/task_decomposition_current.dot` 并用本机 Graphviz 生成 `task_decomposition_current.svg`。实际渲染检查确认白底、中文标签、分组、拒绝分支和重规划回路可读。README 与 MODEL_CONTEXT_FLOW 增加入口。本轮没有修改运行代码、调用模型或执行任务。

Momo 正式 workspace 仍为 revision 149；relation assessment 的旧 baseRevision 问题仍存在，因此未改 canonical 图。

## 2026-09-12 上下文基础框架第一段实现

按用户确认的第一轮范围实现类型化 Goal/Task Context、统一 Builder、权限渲染、渲染后预算和调用前 Manifest。GoalContext 保留原始语义并允许经校验的解释、歧义、缺失、假设、感知请求和澄清请求；TaskStateContext 以分解和依赖/验证关系图表达运行状态。初始规划与自动重规划已接入 Builder，自定义输入/输出预算可跨重规划保存。

实际离线回归为 39 passed、1 live model skipped、9 subtests passed；compileall 通过。没有新增模型、ROS2 或机器人现场验收。Session、自动 Goal 分析、Memory/World Provider、子规划颗粒度和上下文重放仍未完成。正式图仍为 revision 149、38 条语义关系且无孤立/无效/过期关系；旧 relation assessment 基于错误 revision，未自动同步 canonical 图。

随后按用户决定增加初步模型分析和问讯，但将依赖完整对话记忆的多轮语义完善延后。`goal_analysis` 与 `goal_clarification` 使用独立 System Prompt、独立模型响应证据；可由机器人感知的缺失保持 `needs_grounding`，必须由用户提供的信息才进入问讯。离线边界回归增至 41 passed、1 skipped、9 subtests；未调用真实外部模型。

## 2026-09-12 Momo 上下文架构同步（revision 149→151）

按用户要求重建此前失配的 relation assessment，并将上下文第一轮实现同步到正式图。对象更新先经 `project-doc validate/diff/write` 写入 revision 150：新增 GoalAnalyzer、澄清问讯、ContextBuilder、ContextManifest 4 个节点，更新 14 个既有模型流节点；预算继承缺口转为 done，连续 Session 与摘要/记忆检索仍为 open。

基于 revision 150 和当前代码 SHA-256 重新评估 9 条关系，全部通过 `relation-audit validate/diff` 后应用到 revision 151。最终为 41 个对象、87 条关系（47 条语义关系），无孤立对象、无无效关系、无过期证据。旧 assessment 的 baseRevision=16 问题已消除；本次只同步 Momo 状态，未新增代码、模型调用或机器人验收。
