# 当前交接入口：revision 156

以下为最新状态，后续旧节仅作历史记录。整体目标进行中，不得标记完成。用户要求不使用 Superpowers、mock、仿真；模型测试必须用环境真实配置，并校验真实输入、响应及实际执行。

Momo 已更新 19 个已有对象，保留 41 对象、90 关系（50 语义关系），没有改变项目边界或删除记录。12 条已应用关系的证据经源码复核更新；历史 session→QA history 删除提案仍保留，图不能报告为全部清理完成。确定性校验记录见 .momo/intake/verified-increments-final-health.json 和 verified-increments-final-validation.json。

现已具备：完整上下文包与输入重建、单记录/差异视图、记忆和分块摘要、冻结资产绑定、操作者显式完成契约及真实模型恢复、动作发现版本/副作用说明、跨任务/会话/自动化的幂等键冲突检查。HTTP fencing 和协调停止已有实际文件服务证据，不能当作硬件验收。

近期证据入口：docs/validation/completion-recovery-live.json（3条真实响应及实际备用文件恢复）、action-idempotency-live.json（25项回归、1项真实诊断、旧账本兼容）、context-diff-browser-live.json（已有真实账本浏览器检查，无新增AI调用）。不同范围不相加为全套通过。本轮同步未重跑这些模型调用，仅核验已有记录及指纹。

下一阶段：真实世界状态、实体定位、物理完成指标和技能停止/隔离协议；同时可推进通用补偿/人工接管、任务族评测及生产留存等软件工作。真实 G1 候选桥已找到，接口语义见 docs/G1_INTEGRATION_CONTRACT.md；当前实际 ROS 图只有检查节点诊断发布者。设备 ID、网卡/域、时间与坐标约定已向用户询问，尚无回复，不重复启动发现节点来冒充设备进展。

保留所有未提交改动，不提交、回滚或清理用户工作区。继续修改图前重新读取 revision，执行证据及关系审计；不自动删除历史关系或把不明确物理条件设为默认值。

---

# 交接

更新日期：2026-09-12。先读 docs/PROJECT_STATUS.md 和 docs/BUILD_ROADMAP.md；前者是详细工程状态入口，后者定义阶段顺序与退出条件。再读 canonical .momo/momo-workspace.json、docs/OPEN_QUESTIONS.md、验证文档和 README.md。
当前第一版软件实现可运行，完整框架仍有实现、策略和验收缺口。按路线图继续阶段 1“执行权威与恢复闭环”：历史版本契约已完成，下一项是控制权 fencing，随后是补偿及统一重试责任。`qwen3.8-max` 已取得实际成功响应和合法两步计划，但计划未执行；机器人技能接口仍需按 SKILL_PROTOCOL.md 联调。探索保留为最终检验场景，不替代框架工作。
启动前 source ROS2Humble 环境（仅ROS命令需要）。依赖使用本地.venv；测试关闭系统pytest插件自动加载。运行数据放.runtime，不混入源码。
正式图现为 revision 151，41 个对象、87 条关系，其中 47 条为语义关系。关系审计无孤立、无效或过期证据。后续更新前重读 revision 并验证关系指纹。既有主仓库的其他修改不属于本工作，不提交或回滚它们。

OPEN_QUESTIONS.md 的 30 条跟踪项已一一映射到 PROJECT.md 和正式 questions 对象；U05 已凭实际实现和回归证据关闭，现有 28 条未关闭、1 条持续维护、1 条本轮关闭。详细映射和来源指纹见 .momo/intake/open-questions-status.json。任务执行/控制权与多模态存储模块保持 in_progress；只读 UI 的既定交付保持 done，其他 UI 后续问题保持 open。

docs/PROJECT_STATUS.md 现按 10 个模块组维护详细细项，并在总体概览中明确模块状态。后续交付必须更新该文档对应行；Momo PROJECT.md 只保留摘要和入口，避免重复维护两份细表。

用户明确不再使用 superpowers，直接实施；不要恢复其审批流程。解耦只读 UI 已实现，启动方法见 README，API 见 docs/UI_API.md。
上轮曾确认 http://127.0.0.1:8766 页面及 overview API 返回 200，连接 .runtime/ui-validation 的真实文件操作账本；时间与摘要见 docs/validation/status-check.json。本轮未重新检查在线状态。8766 是此前因默认 8765 被占用而选定的查看端口，后续接手仍需实际检查进程状态。
Python 离线回归 32 tests / 9 subtests 通过、live model 1 项默认跳过；显式启用的真实问答 1 项通过。既有构建与 4 项 Chromium 测试结果保留；项目环境没有 `.venv/bin/ruff`。软件/UI/真实短问答验证不等于模型执行或机器人验收。

本轮新增 Planner 提示契约回归和真实模型问答测试，取得 `qwen3.8-max` 合法两步计划与正确问答；没有执行模型计划，也没有新的机器人或传感器结果。不要把 docs/VALIDATION.md 的历史基线、既有 UI 结果、本轮离线回归和单独 live model 验收混为同一范围。

## 2026-09-07 模型上下文图交接

当前正式图 revision 16。刷新 Momo 后进入「模型调用与上下文流转」（model-adapter）查看独立画布及节点详情。新增18子节点、21语义关系；未实现项标为 open。docs/MODEL_CONTEXT_FLOW.md 给出图例和代码来源。下一步实现仍需按用户指示选择；本次仅细化结构与证据。

## 2026-09-08 详细架构交接

先读 `docs/DETAILED_ARCHITECTURE.md`。它把现有第一版契约扩展成完整目标架构，明确 LLM、Runtime、机器人控制端、Verifier 和独立安全链的不同权威，并用 G1 红色方块入抽屉案例说明纵向链路。该文档是架构和实施边界，不是新增功能完成声明；状态仍看 `docs/PROJECT_STATUS.md`。

当前建议仍先做阶段 1 fencing：扩展 SkillSpec、Execution 持久记录和 HTTP/机器人侧协议，用控制域单调 token 验证旧执行者被拒绝。之后再确定第一项 ROS2/Unitree 真实技能及对应独立 verifier。

此前 relation assessment 与 workspace revision 失配的问题已在 2026-09-12 重建解决；不得恢复或复用旧 baseRevision=16 的评估。

## 2026-09-11 任务拆分流程图交接

当前实现的任务拆分主入口见 `docs/TASK_DECOMPOSITION_FLOW.md`，可直接查看的矢量图为 `docs/diagrams/task_decomposition_current.svg`，可编辑 Graphviz 源为同目录 `.dot` 文件。图以代码为准，明确区分 plan 只输出、agent 提交 Task、recover_plan 修订旧 Task 三条路径。

如果继续实现任务拆分能力，应先用真实长程任务集验证现有“一次性 DAG + 失败后整计划修订”在哪里不足，再决定是否增加 Session 记忆、在线 DAG 修补或递归子 Task；不要仅因 Pi Agent 支持工具循环就直接替换当前确定性任务模型。

## 2026-09-12 上下文基础框架交接

用户决定第一轮优先完善必须的上下文基础框架，并明确 GoalContext 要对歧义和疏漏做可追溯的语义整理，TaskStateContext 要以任务分解加依赖关系图帮助理解。第一段实现位于 `context_models.py`、`context_builder.py`、`context_render.py`，并已接入 ModelCaller、Planner 和 Runtime；验证见 `tests/test_context_framework.py` 与 `docs/VALIDATION.md`。

初步 Goal Analyzer 与澄清/感知分流现已实现为独立调用入口和 CLI `analyze-goal`，分析与问讯使用不同 System Prompt；它不自动提交 Task。下一步先做最小 Session 和回答回填，再完善多轮语义分析。当前离线结果为 41 passed、1 skipped、9 subtests passed。Momo 已同步到 revision 151；上下文新增节点和关系均有当前代码指纹。

## 2026-09-22 当前续接入口

最新状态以本节为准：应用层已落地，参见 docs/APPLICATION_LAYER.md、docs/APPLICATION_LAYER_PLAN.md 与 docs/validation/application-layer-2026-09-22.json。用户目标仍在推进，不得标记整个方案完成。遵守“不使用 superpowers、mock、仿真；AI 调用与验收均为真实环境模型”的约束。

当前 Momo revision 153，41对象/89关系，49条语义关系。历史 session→QA history 有一条待清理提案，其他确定性结构检查通过。应用测试和实际模型证据已保存；不重放已验证调用来刷新时间戳。

下一步：根据用户回复接真实设备；无回复时完善通用记忆/摘要、长程会话与真实控制故障验收。设备问题只询问一次，不把未连接设备当作机器人成功。不要执行历史脚本中的演示数据模式或模型替身测试。

复现：PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests/test_application_actions.py tests/test_runtime.py tests/test_contracts_memory.py tests/test_http_execution.py -q；真实模型测试另显式 RUN_LIVE_MODEL_TESTS=1 运行 tests/test_application_live.py。浏览器脚本入口和验收范围见 UI_VALIDATION。

## 记忆增量验收

记忆上下文增量已实现并通过真实模型闭环及排队后失效拒绝。入口 memory.search / session.attach-memories；代码 context_memory.py；证据 docs/validation/memory-context-live.json。输出引用验证新增 closed-schema 检查，实际错误模型计划保存在 docs/validation/invalid-model-output-reference.json，仅用于校验器回归，不替代 AI 响应。后续仍需 UI 记忆选择、长程摘要与真实设备。


当前 Momo revision 155，41对象/90关系（50条语义关系）；新增记忆→上下文关系已通过确定性证据校验。历史 session→QA history 移除提案仍保留。
