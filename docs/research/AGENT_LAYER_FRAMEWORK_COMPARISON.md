# Agent 层框架调研与当前工程适配

调研日期：2026-09-22。范围聚焦 Agent 层：目标理解、任务分解、工具调用、上下文与记忆、重规划、多 Agent 协作和调试评测。机器人专用 Agent 范式属于本轮重点；驱动、运动控制和执行调度的替换不属于本轮重点。

用户进一步明确需要机器人专用 Agent 范式后，研究顺序调整为：**先比较 RAI、DimOS、EmbodiedAgents 的具身 Agent 组织方式，再决定是否用 LangGraph/PydanticAI 实现或补充。** 下文第 1–8 节保留通用框架比较，第 9 节补充机器人专用范式；不能将通用框架的推荐顺序理解为机器人 Agent 架构的最终选型。

## 1. 初步结论

有比 Agent-Native 更直接面向 Agent 推理与编排的候选。优先深入比较 **LangGraph 与 PydanticAI**；**Deep Agents** 作为完整 Agent harness 的对照。这里的优先级是结合本项目的适配判断，不是性能实测排名。

- **需要把 Agent 的分析、查资料、澄清、计划评审、修正做成明确流程：优先评估 LangGraph。** 它提供状态图、分支、循环、子图和暂停恢复等编排基础，适合显式控制推理过程。
- **希望尽量沿用当前工程，先增强类型化输出和工具调用：优先评估 PydanticAI。** 它与现有 Python、结构化契约和 DBOS 路线比较接近，适合作为可替换的 Agent 后端。
- **希望尽快获得带规划、文件上下文、摘要和子 Agent 的完整工作循环：评估 Deep Agents。** 它提供更多默认机制，也要求对这些机制与现有上下文系统的重叠进行取舍。

Agent-Native 继续作为共享动作、数据和 UI 协作的参考。这些应用层设计可以和上述 Agent 框架共存，无须把它们当成只能二选一的整套技术栈。

## 2. 当前 Agent 层基线

本轮读取了 `goal_analysis.py`、`planner.py`、`model_call.py`、`model_methods.py`、`context_models.py` 及项目应用层说明，得到以下基线：

| 已有机制 | 当前作用 | 新框架应提供的增量 |
|---|---|---|
| GoalAnalyzer / GoalContext | 理解目标、记录歧义与缺失信息、生成澄清问题 | 根据中间结果选择继续询问、检索或规划 |
| ContextBuilder / Bundle / Manifest | 组织上下文、权限层级、来源、预算和实际输入追溯 | 支持多轮 Agent 调用，每轮继续保留这套追溯 |
| Planner / validate_plan | 生成 JSON DAG，校验能力、依赖与最终 verifier | 分阶段提出计划、读取校验错误、在预算内修正 |
| ModelCaller | 明确的方法提示、输入分配、HTTP 调用、响应检查 | 模型—工具—结果—再推理的完整循环 |
| 会话、记忆、摘要 | 持久对话、绑定来源、原文固定和预算整理 | 按当前问题主动选择检索，而不是重复建第二套记忆库 |
| 统一 Action 层 | 身份、范围、幂等与调用审计 | 为 Agent 提供受控工具适配 |

一个具体发现：当前 `ModelCaller.send_prepared()` 要求 `finish_reason == "stop"`，并读取非空字符串 `message.content`；所读调用路径没有处理 `tool_calls` 并循环回传工具结果。`Planner.plan()` 的当前职责是一次模型计划生成及本地校验。系统外围已有重规划，因此不能把项目描述为“只有一次调用、没有恢复”；更准确的缺口是**通用、多轮、可观察的 Agent 工具调用与推理编排**。

本机项目声明 Python >=3.10，当前环境文档为 Python 3.10；DBOS 固定为 2.31.0。模型通过自定义 Chat Completions 兼容端点接入。框架声称支持某 provider，不等于已经验证这个实际端点支持工具调用和严格结构化输出。

## 3. 候选总表

事实依据是官方仓库及文档；“适配判断”是本轮分析。完整固定提交和下载文件哈希见 [来源清单](framework-refresh-2026-09-22/inventory.json)。

| 候选 | 官方提供的主要机制 | 对当前工程的适配判断 | 首轮位置 |
|---|---|---|---|
| [LangGraph](https://github.com/langchain-ai/langgraph) | 有状态图编排、持久状态、人工介入、短期与长期记忆基础 | 最适合显式表达 Agent 决策流程；状态图与现有会话/快照需要清楚分工 | 主候选：编排能力 |
| [PydanticAI](https://github.com/pydantic/pydantic-ai) | 类型化输出、工具、依赖注入、多模型、Pydantic Graph、持久执行集成 | 与当前契约层接近；可分步替换模型/Agent 调用，保留原有校验与证据 | 主候选：渐进接入 |
| [Deep Agents](https://github.com/langchain-ai/deepagents) | 基于 LangChain/LangGraph 的规划、文件上下文、子 Agent、上下文管理和 skills | 能快速获得完整工作循环；与已有摘要、记忆和预算功能重叠较多 | 完整 harness 对照 |
| [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) | Agent/Runner、函数工具、handoff、Agent-as-tool、sessions、guardrails、tracing | 轻量工具循环很合适；复杂流程及原有审计需要应用适配 | 轻量备选 |
| [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) | Python/.NET、多 provider、图工作流、并发/交接、checkpoint、人工介入 | 能力覆盖广；当前项目没有体现必须选它的 .NET 或微软生态需求 | 编排备选 |
| [Agno](https://github.com/agno-agi/agno) | Agent SDK、AgentOS 服务、会话/记忆存储、上下文源、接口和观测 | 若以后希望采用现成 Agent 服务平台很有价值；当前已有应用服务和工作台，整体引入重叠较大 | 平台方向备选 |
| [CrewAI](https://github.com/crewAIInc/crewAI) | 角色/任务/Crew 协作及显式事件驱动 Flows | 适合快速组织专家协作；本项目还需证明多角色比单 Agent 更有收益 | 多角色试验备选 |
| [smolagents](https://github.com/huggingface/smolagents) | CodeAgent、ToolCallingAgent、多模型及多模态工具接入 | 适合小规模研究原型；代码动作还需额外映射到项目动作与审计契约 | 原型对照 |

SDK 开源库和托管服务需要区分：LangGraph 不要求使用 LangSmith 才能本地编排；CrewAI 的商业平台不等于其开源库；Agno SDK 与 AgentOS 整体平台也应分别评估。这里不把厂商“production-ready”或 README 的性能措辞当作本项目的可靠性证明。

## 4. 三个重点候选

### 4.1 LangGraph：显式组织 Agent 的决策过程

LangGraph 定位为底层、有状态的 Agent 编排框架，官方列出持久执行、人工介入及记忆支持。它可以独立使用，业务仍需定义图中节点、状态和条件。依据：[官方概览](https://docs.langchain.com/oss/python/langgraph/overview)、[持久状态](https://docs.langchain.com/oss/python/langgraph/persistence)。

对本项目的价值在于把以下“认知流程”表达清楚：

```text
理解目标 → 判断信息是否足够 → 查询允许的数据/请求澄清
    ↑                              ↓
    └──────── 更新上下文 ──────────┘
                    ↓
                 生成计划
                    ↓
              确定性契约校验
                    ↓
          合格：发布草稿 / 不合格：限次修正
```

这张 Agent 流程图和模型输出的“业务任务 DAG”是两个对象：前者描述如何思考、获取信息和形成计划，后者描述待执行的任务依赖。不能因为都叫 graph 就合并成同一个状态模型。

接入建议：先让图节点调用现有 GoalAnalyzer、上下文构造与计划校验，只引入思考流程的编排。节点生成的新模型输入和工具结果仍写入项目证据记录。若使用 checkpoint，应定义它只恢复 Agent 推理状态，业务会话 revision 和计划有效性仍由现有系统判定。

代价：需要自己实现图与状态转换，并协调 graph thread/checkpoint 与 session、request、task 的关联。具备 checkpoint 也不自动意味着节点中的外部副作用不会重复；这仍需具体工具语义。适合“我要精确控制 Agent 如何解决问题”，不保证开箱即用的规划质量。

### 4.2 PydanticAI：增强当前 Python Agent 调用边界

PydanticAI 提供类型化输出、依赖注入、工具与多模型接入，也有 Pydantic Graph；因此不能简单把它视为只会调用模型的包装器。依据：[仓库](https://github.com/pydantic/pydantic-ai)、[官方概览](https://pydantic.dev/docs/ai/overview/)。

接入建议：在 `Planner`/`GoalAnalyzer` 与模型之间引入候选 Agent 后端，使用输出类型表达“需要澄清”“计划草稿”“无法完成”等结果；把 schema 错误反馈给 Agent 做有预算的修正。保留 `validate_plan()` 对依赖关系、能力白名单、引用路径和最终验证节点的领域检查。类型正确不等于计划可执行。

工具的依赖对象可携带主体、会话、catalog 与上下文引用；这些值由服务端提供，不能让模型通过工具参数提升权限。`context_models.py` 可继续作为通用契约，不需要为了引入 PydanticAI 全量改写成其专用类型。

已有 DBOS 官方集成是适配优势，但不是本轮必须启用的部分。固定提交中的文档采用 `DBOSDurability` capability，要求在 `@DBOS.workflow` 内运行；旧 `DBOSAgent` 包装路线已标为 deprecated。自定义工具并非自动全部成为 DBOS step。依据：[固定版本集成说明](framework-refresh-2026-09-22/pydantic__pydantic-ai/docs/durable_execution/dbos.md)。不要照抄不同年代教程，把“安装了集成”写成“所有 Agent 状态和工具都已可靠恢复”。

代价：需要把每轮实际请求/响应和工具调用接回项目记录，处理 SDK 消息类型到 Bundle/Manifest 的映射，并核对现有模型的结构化输出与工具调用能力。

### 4.3 Deep Agents：完整工作循环的参考与对照

其仓库明确区分三层：LangGraph 是图运行基础；LangChain `create_agent` 提供较小的 Agent harness；Deep Agents 在其上加入文件系统、子 Agent、上下文管理和 skills。它的规划和 todo 能力不自动等于本项目的可校验 DAG 规划器。依据：[仓库说明](https://github.com/langchain-ai/deepagents)。

适合研究的部分：如何把长任务拆成工作项、按需读取资料、把中间材料外置、隔离子任务上下文，再由主 Agent 汇总。对当前工程可先作为相同输入/工具下的完整方案对照。

接入代价：已有会话摘要、绑定记忆和预算管理需要确定唯一职责；框架追加的提示、摘要和子 Agent 上下文必须进入实际输入记录。文件工具应绑定允许的资料区与来源记录，不能把任意文件内容直接升级为可信事实。

环境限制：本轮固定的 `deepagents` 包声明 Python >=3.11,<4.0，不能直接装入项目当前 Python 3.10 环境。若试点，应使用独立 Agent 环境或先评估升级影响。该限制针对所查版本，不代表全部历史版本。

## 5. 接入边界与共同要求

以下是候选评估用的边界建议，尚未实施：

```text
用户目标 / 会话
       ↓
现有 GoalContext + ContextBuilder + 来源/预算
       ↓
候选 Agent 后端（首轮分别比较，避免同时叠加）
  ├─ 理解、澄清、查询、计划、限次修正
  ├─ 受控 Action 工具适配
  └─ 每轮 messages、工具结果、用量、来源关联
       ↓
PlanCandidate / Clarification / CannotComplete
       ↓
现有 validate_plan + 版本绑定草稿 + 统一提交入口
```

其中 `PlanCandidate / Clarification / CannotComplete` 是建议的输出分类，不是当前已经新增的 Python 类型。

1. **上下文：** Bundle/Manifest 继续解释每轮实际输入；SDK 隐式追加的提示、消息整理和工具描述也须可追溯。
2. **记忆：** 会话历史、模型摘要、检索证据与持久事实分开；不能因为框架自带 memory 就取消已有来源和版本校验。
3. **工具：** 复用 Action 的身份与范围检查。第一轮只开放能力发现、任务/资产/记忆查询和草稿生成相关能力；提交继续走现有契约。
4. **模型兼容：** 同一实际模型、同一端点下检查 tool call 格式、结构化结果、错误返回、超时和流式行为。普通聊天成功只证明聊天路径。
5. **预算：** 限制模型轮数、工具调用和计划修正次数；多 Agent 共享总预算，不能各自重新获得完整预算。
6. **状态：** 澄清等待、预算耗尽、服务错误、用户修改会话、取消与迟到返回都有显式结果；不能把空输出转为成功。

## 6. Python、版本与许可快照

下表版本是本次 HEAD 文件中的声明，不代表已经确认的最新稳定发行版。声明支持当前 Python 不等于完整依赖解算和运行兼容已经通过。

| 候选 | 本轮提交（短 SHA） | 所查 Python 声明 | 包版本声明 | 仓库根许可 |
|---|---|---|---|---|
| PydanticAI | `e8895d2905d7` | >=3.10 | 动态版本，本轮不推断发布号 | MIT |
| LangGraph | `49cce0ca852b` | >=3.10 | 1.2.12 | MIT |
| Deep Agents | `d4e1fb3fedd5` | >=3.11,<4.0 | 0.7.17 | MIT |
| OpenAI Agents SDK | `32edd3c3ecde` | >=3.10 | 0.22.3 | MIT |
| Microsoft Agent Framework core | `a8acb4e0e9d7` | >=3.10 | 1.19.0 | MIT |
| Agno | `54516f4186b4` | >=3.9,<4 | 3.0.10 | Apache-2.0 |
| CrewAI | `bdd1bc62007f` | 根 workspace：>=3.10,<3.14；具体子包待核对 | 未确认具体子包发布号 | MIT |
| smolagents | `30bb1161095d` | >=3.10 | 1.27.0.dev0（开发版） | Apache-2.0 |

PydanticAI slim 的 DBOS extra 声明 `dbos>=2.10.0`，当前项目 2.31.0 满足这个单独版本条件；尚未执行全量依赖解算或集成测试。实际采用时固定发行版本并核对对应 API，而不是直接依赖移动的 main 分支。

GitHub REST API 本轮返回 403 rate limit exceeded，因此未确认最新 release、归档标记和提交时间。随后使用 `git ls-remote HEAD` 获取 SHA，再通过固定 SHA 下载文件，成功取得上述八个 Agent 候选的 README、许可和相应配置。失败路径也保存在来源清单，不能把 404/403 当成已阅读证据。HEAD SHA 是可重查的内容基线，不是维护频率指标。

## 7. 下一轮如何选出真正适合的方案

先比较现有实现、PydanticAI 和 LangGraph，Deep Agents 按需加入。第一轮无需多 Agent：先确认单 Agent 工具循环带来收益，再增加只读计划评审角色。

| 用例 | 观察内容 | 合格标准 |
|---|---|---|
| 目标存在歧义 | Agent 是否先澄清 | 不虚构用户意图；补充信息后继续原会话 |
| 需要现有记忆 | 是否按需查询真实索引 | 工具结果保留来源、版本和有效性 |
| 多步骤目标 | 生成现有计划格式 | 通过同一个 validate_plan 和 verifier 检查 |
| 计划引用错误 | 能否利用错误修正 | 有界修正；不改校验器来适应错误答案 |
| 能力不足 | 如何表达不可完成 | 不创造不存在的工具或假结果 |
| 长上下文 | 固定条件和预算处理 | 重要约束保留，实际输入能重建 |
| 会话更新或取消 | 如何处置迟到返回 | 旧版本计划不被采用，预算不被重置 |
| 服务错误 | SDK 是否隐藏失败或自动多次重试 | 错误与重试可见，调用总量可解释 |

比较相同目标、相同模型、相同工具集合与预算；保存每轮输入/原始返回及框架版本。记录计划合法率、有效澄清、幻觉工具/引用、修正成功率、模型与工具调用数、token 用量、延迟和追溯完整性。固定小任务集并重复运行，报告样本量与波动；本轮没有这些运行数据，不能声称某框架规划更准确或成本更低。

首轮取舍规则：若主要收益来自类型化输出和工具循环，倾向 PydanticAI；若明显需要自定义分支、循环和人工暂停，倾向 LangGraph；若需要完整文件工作区与委派能力，再比较 Deep Agents。无需默认叠加三个框架。

## 8. 调研交付与阅读入口

本轮交付为源码/文档调研和来源快照；没有安装候选依赖、修改 Agent 实现、调用模型或进行运行性能测试。RAI、DimOS、EmbodiedAgents 的已有快照纳入第 9 节机器人专用范式比较；ROSA、OM1 保留为后续候选。本轮没有统一运行评测排名。

- [固定来源清单](framework-refresh-2026-09-22/inventory.json)：仓库 SHA、下载 URL、文件 SHA256 和失败记录。
- [LangGraph README](framework-refresh-2026-09-22/langchain-ai__langgraph/README.md) 与 [包配置](framework-refresh-2026-09-22/langchain-ai__langgraph/libs/langgraph/pyproject.toml)。
- [PydanticAI README](framework-refresh-2026-09-22/pydantic__pydantic-ai/README.md)、[slim 包配置](framework-refresh-2026-09-22/pydantic__pydantic-ai/pydantic_ai_slim/pyproject.toml) 与 [DBOS 集成](framework-refresh-2026-09-22/pydantic__pydantic-ai/docs/durable_execution/dbos.md)。
- [Deep Agents README](framework-refresh-2026-09-22/langchain-ai__deepagents/README.md) 与 [包配置](framework-refresh-2026-09-22/langchain-ai__deepagents/libs/deepagents/pyproject.toml)。
- [OpenAI Agents SDK 官方说明](https://developers.openai.com/api/docs/guides/agents/sdk) 与 [模型/provider 说明](https://developers.openai.com/api/docs/guides/agents/models)：支持多 provider，但仍需核对实际端点。
- [Microsoft Agent Framework](framework-refresh-2026-09-22/microsoft__agent-framework/README.md)、[Agno](framework-refresh-2026-09-22/agno-agi__agno/README.md)、[CrewAI](framework-refresh-2026-09-22/crewAIInc__crewAI/README.md)、[smolagents](framework-refresh-2026-09-22/huggingface__smolagents/README.md)。
- [已有 Agent-Native 参考](AGENT_NATIVE_PROJECT_REFERENCE.md) 与 [上一轮整体架构调研](REPORT.md)：用于背景对照，不替代本轮 Agent 层判断。

## 9. 机器人专用 Agent 范式：本项目更应优先研究的对象

聚焦 Agent 层仍需研究机器人特有的认知问题：自身能力与限制、当前对象与位置、观测有效性、技能可行性、执行反馈、任务完成判定。通用工具循环可以承载这些逻辑，但没有自动定义这些语义。

### 9.1 有具体代码可借鉴的框架

| 框架 | 机器人 Agent 的组织方式 | 对本项目的借鉴位置 |
|---|---|---|
| [RAI](https://github.com/RobotecAI/rai) | 本体描述、机器人状态、多模态消息、专用工具与 ReAct 循环；whoami 从机器人文档、图像和 URDF 构造本体信息 | 优先研究：机器人能力如何进入上下文；Agent 如何调用感知/任务工具并利用结果 |
| [DimOS](https://github.com/dimensionalOS/dimos) | Agent 作为机器人模块，连接感知流、空间记忆和技能 | 优先研究：具身上下文如何更新，空间记忆怎样支持主动查询；本轮不因此决定更换其底层运行系统 |
| [EmbodiedAgents](https://github.com/automatika-robotics/embodied-agents) | LLM/VLM、语义路由和记忆组件组成事件驱动的 Agent 图 | 比较感知、对话、记忆、决策的拆分方式；组件图不自动等于任务规划 DAG |

RAI 的[完整教程](https://robotecai.github.io/rai/tutorials/walkthrough/)明确给出了状态监测、专用工具、whoami 和 Agent 调用过程。其 [agentic-mobile-manipulator](https://github.com/RobotecAI/agentic-mobile-manipulator) 是可继续审阅的移动操作案例，但仓库将该案例描述为 ROS2 仿真演示，不能记为本项目真机验证。EmbodiedAgents 的[架构说明](https://agents.automatikarobotics.com/development/architecture.html)解释了生命周期节点、模型客户端与组件的分工。

### 9.2 研究范式与可直接复用框架分开判断

- **[SayCan](https://say-can.github.io/)**：同时考虑技能对目标的语义贡献和技能在当前状态下的成功可能性。后者通过技能 affordance/value function 接地，不是让语言模型重复回答“我觉得能做”。适合借鉴技能候选筛选与可行性分离。项目页提供代码入口并注明开放了桌面仿真版本，不是通用生产 SDK。
- **[Inner Monologue](https://innermonologue.github.io/)**：把场景描述、主动感知问答、成功检测与人工反馈持续带回规划，形成闭环。适合借鉴执行后如何更新上下文与修订计划；本轮作为论文方法参考，没有确认一个可直接安装的通用框架。
- **[Code as Policies](https://code-as-policies.github.io/)**：由语言模型生成组合感知与控制 API 的程序。适合研究技能组合的表达方式；对当前以 JSON DAG 和确定性校验为边界的项目，引入生成代码需要额外定义程序执行与验证契约，不作为首选路线。

### 9.3 对当前工程的映射判断

建议的认知链路是：目标与机器人能力 → 当前世界信息/记忆 → 判断需要澄清还是感知 → 生成子目标 → 选择可行技能 → 消费执行与验证结果 → 更新任务状态并重规划。这是综合上述工作的项目建议，不声称任一框架原样提供整条链路。

`examples/jev/reference_examples.py` 中的目标消歧、上下文相关性和技能语义选择，恰好对应其中的若干局部决策。该文件明确使用合成数据；其中技能选择示例只判断语义匹配，不能作为 SayCan 式物理可行性估计或现场成功率证据。需额外输入真实对象、状态、技能前置条件和可验证结果。

下一轮应先审阅 RAI 的 Agent 状态/工具/本体契约，以及 DimOS 的 Agent/空间记忆/技能结果接口，形成与 GoalContext、ContextBundle 和现有 Action 的逐项映射。通用框架作为实现基础留待这一层范式确定后选择，暂不以安装新框架代替范式研究。
