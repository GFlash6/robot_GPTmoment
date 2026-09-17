> 历史研究阶段材料：项目已正式注册并实现第一版。当前状态以 ../../.momo/momo-workspace.json 与 ../VALIDATION.md 为准，不重放本文件的旧接管步骤。

# Momo 初次接管预览

管理范围：robot_agent_framework 一个自有项目；现有 Unitree/HoloAgent、OM1、DimOS 及其他上游均作为外部研究来源，不纳入源码所有权。

当前阶段：research；早期架构和计划仅为草稿，实现暂停。

候选图：1 个 Project，12 个对象，12 条包含关系，9 条候选语义关系（8 条满足自动添加条件，1 条因语义不足保留审议）；selection 为 Unknown 且暂时隔离，因为尚未有选型结果。

对象覆盖：目标、单机范围、任务编排、多模态记忆、证据要求、开源调研、技术选型、实现、问题台账、真实联调、Momo 维护、失败的初始测试记录。

确认后新增：
- .momo/momo-workspace.json：唯一正式 V2 快照。
- .momo/workspace.json：本地路由与分类。
- .momo/intake/intake-assessment.json：来源和项目边界。
- .momo/intake/relation-assessment.json：关系证据及待审议项。
- .momo/lifecycle/robot-agent-framework/{PROJECT,UNKNOWNS,DECISIONS,WORKLOG,HANDOFF,QUIZ}.md。
- 注册到本机 Momo registry，不启动 Web，不修改 Momo 源码工程。

确认仅用于项目边界与上述管理文件，不代表批准任何技术选型或虚构验证结果。

研究补充：41 个仓库、110 份来源文件的结果已关联到 research 对象；selection 仍为 Unknown。初始失败测试不再作为自动支持实现的关系，保留为待审议证据。上述调整不改变项目边界。
