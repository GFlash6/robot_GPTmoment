# 项目状态

更新日期：2026-09-12。阶段 `implementation`，整体 `in_progress`；当前同时推进上下文基础框架的第一轮纵向切片。

详细工程情况统一维护在 [PROJECT_STATUS.md](../../../docs/PROJECT_STATUS.md)，其中按模块和细项区分“已完成、进行中、未完成”，并记录证据与关闭条件；构建顺序和阶段退出条件见 [BUILD_ROADMAP.md](../../../docs/BUILD_ROADMAP.md)。`docs/OPEN_QUESTIONS.md` 保存问题原文；`.momo/intake/open-questions-status.json` 保存 30 条问题与 Momo 对象的结构化映射。

完整目标分层、组件边界、状态机、执行协议、部署视图和 G1 任务案例见 [DETAILED_ARCHITECTURE.md](../../../docs/DETAILED_ARCHITECTURE.md)。该文档是依据现有实现和未关闭问题形成的目标架构，不改变 `PROJECT_STATUS.md` 中的交付状态。

当前自然语言目标如何生成、校验、提交 DAG，以及失败后如何进行有界重规划，见 [TASK_DECOMPOSITION_FLOW.md](../../../docs/TASK_DECOMPOSITION_FLOW.md) 和配套 SVG。该图只描述当前实现。

当前结论：第一版任务编排、资源账本、实际结果判定、多模态资产目录、持久恢复和解耦只读 UI 可运行；`qwen3.8-max` 实际两步计划已通过响应解析和契约校验。模型计划尚未执行，机器人执行、多模态现场数据、补偿、控制端旧执行者隔离、地图失效、数据保留等仍未完成。

最新离线回归为 41 tests / 9 subtests 通过、1 项 live model 默认跳过；显式启用的 `qwen3.8-max` 真实问答 1 项通过。既有 4 项 Chromium 检查及前端构建结果保留；下一项仍为控制权 fencing。这不代表机器人或模型执行端到端验收。本轮未执行 ruff，因为项目环境没有该可执行文件。

Momo 当前正式快照在 `.momo/momo-workspace.json`。图健康和 revision 以该文件及最新审计为准，不在这里复制计数。

## 上下文基础框架（2026-09-12）

已实现 Goal 语义档案、初步模型语义分析与独立澄清问讯、图结构 TaskStateContext、ContextBuilder、权限分层渲染、稳定预算和模型发送前 Manifest，并接入初始规划与自动重规划。当前只证明软件链路；完整多轮语义完善、Session、Memory/World Provider、子规划颗粒度和机器人现场上下文仍未完成。最新离线回归为 41 tests / 9 subtests 通过、1 项 live model 默认跳过。

## 模型调用与上下文子图（2026-09-07）

正式图 revision 151，在原 model-adapter 对象内包含 22 个细项。除调用主链、三类历史和重规划回流外，已加入 GoalAnalyzer、澄清问讯、ContextBuilder 与 ContextManifest；预算继承已完成，连续会话和摘要/记忆检索仍开放。详见 docs/MODEL_CONTEXT_FLOW.md；项目边界与运行能力未改变。
