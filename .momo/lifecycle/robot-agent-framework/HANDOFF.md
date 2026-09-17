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
