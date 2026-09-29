# Agent-Native 对机器人 Agent 项目的借鉴价值与落地方案

评估日期：2026-09-22。本文为源码审阅与后续方案，不表示新增功能已经实现。

## 1. 评估对象与结论

用户提供的路径是本项目 `robot_agent/`，没有单独指定外部仓库。本文结合工作区已有 `agent-native/` 和 `docs/APPLICATION_LAYER_PLAN.md` 中的既有决策，按“Agent-Native 对当前机器人项目的参考价值”评估；若所指为另一个框架，需要重新核对外部来源。

外部源码基线：`agent-native/` 独立 Git 仓库提交 `8b4845652910a462c269f5002bc103d94d48fbb8`。项目实现以本次工作区代码为准，包含尚未提交的增量。尝试访问官方在线 actions/context 文档未成功，外部能力判断使用本地 README、文档和源码，不宣称代表线上最新版本。本次没有安装依赖、修改运行代码、请求模型或执行机器人；验收状态来自已有记录，未重新运行测试。

**建议：借鉴应用层架构，保留 Python 执行内核。** Agent-Native 的高价值是把人、Agent 和界面连接到统一能力、数据与上下文上。它不能直接替代机器人执行协议、资源控制、停止证据、实时世界模型和硬件安全链路。现有项目已吸收大量基础设计，后续收益主要在可靠上下文、可解释操作和实际设备闭环。

三种路线比较：

| 路线 | 适配成本与收益 | 建议 |
|---|---|---|
| 整体迁移到 Agent-Native | 重建 Python/ROS2/DBOS 接口，出现第二套任务生命周期和身份边界；仍需自建物理执行协议 | 当前不选 |
| 引入其独立应用前端/服务 | 可利用其应用生态，但增加 Node 服务、跨服务授权和数据同步；适合未来有明确插件生态需求时试点 | 后置 |
| 按源码模式完善现有 Python + React | 延续现有证据、任务账本、控制接口；可逐项交付并回退 | 首选 |

## 2. 源码对应与价值判断

以下路径均相对项目根目录。

| 参考机制与来源 | 当前对应实现 | 借鉴价值与实际缺口 |
|---|---|---|
| Shared Actions：`agent-native/packages/core/src/action.ts` | `robot_agent/actions.py`、`application.py`、`cli.py` | 高；已有共享校验、主体权限、机器人范围及命令队列。可补统一输出契约、动作版本、调用链 ID；新增协议入口继续复用同一动作层 |
| UI Context：`agent-native/packages/core/docs/content/context-awareness.mdx` | `sessions.py`、`context_providers.py`、`ui/src/Workbench.tsx` | 高；已有选择、任务版本和会话绑定。继续把界面选择解析为服务端实际对象，区分选择提示与世界事实 |
| Context X-ray：`agent-native/packages/core/src/shared/context-xray.ts` | `context_models.py`、`context_builder.py`、`model_context.py`、`context_codec.py` | 很高；已有 Manifest、来源、预算丢弃和持久包。只读 API、单记录面板与跨调用差异界面已接通；后续重点是来源跳转、失效原因以及强制保留项解释 |
| Observational Memory：`agent-native/packages/core/src/agent/observational-memory/types.ts` 等 | `session_history.py`、`session_budget.py`、`context_memory.py`、`recovery_budget.py` | 中高；参考原始记录、观察与总结的分层。已有摘要和记忆绑定，不应重复建设；需强化事实、推断和用户指令的区别 |
| Automations：`agent-native/packages/core/docs/content/automations.mdx`、`src/automations/service.ts` | `automations.py`、`explanation.py` | 中高；已有失败事件诊断、预算、持久作业与显式重试。定时与条件触发仍可借鉴，但不得用模型自然语言判断代替运动前置条件 |
| Agent Teams：`agent-native/packages/core/docs/content/agent-teams.mdx` | 尚无通用多 Agent 编排 | 中；先用于只读诊断或计划评审，统一 Runtime 保持唯一动作执行权。没有基准证明前不增加多 Agent 复杂度 |
| 共享数据库与应用生态：`agent-native/README.md` | `store.py` + DBOS + 独立应用/观察 API | 中；借鉴共享权威数据与读视图，暂不为技术栈统一迁移存储。扩容需单独验证事务、恢复及控制权 |

Agent-Native 中的 application state 是应用状态，不能等同于机器人 world state；持久化子 Agent 状态也不能直接证明跨进程物理动作恰好执行一次。

## 3. 当前已有成果与证据边界

当前不是从零建设应用层：

- `actions.py` 已注册 task/session/plan/memory/automation 等动作；控制命令接受和实际任务终态分离。
- `context_models.py` 已有 GoalContext、TaskNode/Edge、ContextRequest/Fragment/Bundle/Manifest；包括来源、权限层级、证据 ID、任务版本、上下文预算和 Provider 诊断。
- Builder 已隔离 Provider 输入；完整 Bundle v1 已可严格编码、读取并绑定模型记录。`frozen=True` 只冻结 dataclass 属性，不能单独保证内部 dict/list 不可变；现有复制与 codec 校验仍有必要。
- 会话澄清、选择、绑定记忆、摘要与恢复预算已有实现。不要把旧状态表中“未完成摘要”等文字当成当前唯一结论。
- 已有失败事件自动诊断及浏览器操作，也有分页事件读取、断连保留与重连验证。
- HTTP fencing 和显式 reconciliation 已有真实文件服务证据，但没有机器人驱动端和物理停止验收。

关键已有记录：

| 记录 | 支持的结论 | 不支持的结论 |
|---|---|---|
| [上下文包验证](../validation/context-codec-live.json) | 真实模型记录、上下文包重建实际输入、实际文件执行 | 全部 Context 类型跨版本迁移已完成 |
| [多文件任务验证](../validation/multifile-live.json) | 受约束文件任务族的实际规划与执行 | 通用长程机器人任务成功率 |
| [事件浏览器验证](../validation/event-browser-live.json) | 实际账本的 69 条控制任务事件与 17 条既有模型任务事件分页；此浏览器验证新增模型调用为 0 | 本次浏览器测试重新验证模型规划质量 |
| [Fencing 验证](../validation/fencing-live.json)、[协调停止验证](../validation/fencing-reconciliation-live.json) | 文件技能服务的旧令牌隔离、恢复和停止结果处理 | 多账本分布式仲裁、硬件急停、物理制动 |
| [ROS 发现记录](../validation/context-provider-ros-discovery.json) | 当次发现只有诊断主题 | 当前设备实时状态或有效机器人位姿 |

## 4. 建议的目标链路

```text
操作员 / UI / 未来协议客户端
           ↓ 服务端身份与范围
       共享 Action 层
       ├─ Session → Goal 分析 → ContextBuilder → Planner → 版本绑定草稿
       ├─ 只读查询 → 任务、模型、证据及上下文视图
       └─ 提交/控制 → 持久命令 → Runtime / DBOS
                                      ↓ 资源与执行身份
                                  注册 Skill Adapter
                                      ↓
                                  实际设备接口
                                      ↓
                           实际结果 / 独立观测 / 停止证据
                                      ↓
                               账本、资产及验证器
```

世界观测经独立采集/校验层供 ContextBuilder 和执行前检查使用。模型的推断进入计划草稿或解释，不直接写成已观测事实。物理动作只通过 Runtime 派发；新增 HTTP/MCP 等入口也不另建运动路径。

## 5. 重点改造：从通用 Context 到机器人可用事实

### 5.1 保持 context_models.py 为轻量契约层

保留现有类型，避免把 ROS 订阅、检索、模型请求和 UI 状态同步塞入 dataclass。建议分工：

- `context_models.py`：请求、片段、Manifest 等通用类型。
- 新增 `world_models.py`：世界观测、实体引用和有效性契约；字段在确认设备消息后最终确定。
- 新增 `world_state.py`：读取已采集观测，检查时效、坐标与来源。
- `context_providers.py`：新增 WorldStateProvider，输出 data 权限片段。
- `context_codec.py`：保持严格 JSON 边界；新字段遵循显式版本规则，旧包不凭空补出观测。
- `context_snapshot.py`：绑定用于规划的观测快照；提交与派发阶段重新检查动态前置条件。

### 5.2 建议的观测契约

以下为设计字段，不是已经存在的设备消息或接口承诺。

| 字段组 | 建议内容 | 解决的问题 |
|---|---|---|
| 身份 | observation_id、robot_id、source、schema_version | 观测可定位，机器人范围可校验 |
| 时间 | observed_at_ns、received_at_ns、clock_domain、validity_policy_id | 区分采集与接收时间，禁止跨时钟直接比较 |
| 空间 | frame_id、transform_ref、map_version（适用时） | 防止混用位姿、地图及坐标系 |
| 内容 | observation_kind、结构化 value、单位及质量指标（来源支持时） | 避免任意文本充当测量值；不虚构统一 confidence |
| 来源证据 | evidence_ids、payload_hash、采集配置版本 | 可回查原始记录及处理过程 |
| 有效性 | valid/stale/unavailable/invalid、reason | 明确未知；绝不回填默认位姿或电量 |

TTL 应按观测类型和设备能力配置；持物状态、机器人位姿、静态地图不能共用随意指定的时间阈值。跨时钟有效性需要明确转换依据与误差上限。规划快照有效不意味着数秒后的运动仍可执行，派发前必须重新验证所需动态条件。

### 5.3 结构化实体与完成条件

已有首个具体引用契约 AssetBinding v1，将会话归档资产绑定到实际登记记录和字节，跨规划/提交/派发复核，见 [资产绑定说明](../ASSET_CONTEXT_BINDINGS.md)。它不表示物理实体定位已实现。

另已加入操作者显式完成契约，绑定最终验证技能并核对实际输出，见 [完成契约](../COMPLETION_CONTRACTS.md)。它与模型解释的文字条件分开，不能自动证明自然语言目标的全部语义已覆盖。

`GoalContext.entities` 和 `relations` 目前保留通用字典。建议逐步增加有版本的 EntityRef、GroundingResult、CompletionCriterion，而不是一次替换所有历史格式。

例如“笔记本电脑”先是语义目标；绑定到 actual object ID、观测证据、坐标和时效后才成为可执行目标。`grounding_requests` 保留未解决项；缺少对象唯一性时进入澄清或感知步骤。完成条件需绑定可执行 verifier：对象身份正确、位于指定区域、已释放、稳定性达到经实际任务确认的标准。

## 6. 应用协作层的增量方案

**动作契约。** 在当前 ActionSpec 基础上考虑增加 output_schema、contract_version、effect_kind、调用关联信息。effect_kind 可区分 read、model_call、command；仅用于发现与审计，不能替代权限。幂等键继续绑定主体、动作及规范化输入；参数冲突拒绝，不把重复点击转成新运动。MCP 等传输适配按实际需求添加，不是当前阻塞项。

**上下文检查视图。** 已提供 model_record → Bundle → Manifest 的只读查询和模型记录面板，见 [上下文证据说明](../MODEL_CONTEXT_EVIDENCE.md)。既有真实账本浏览器验证及独立界面审查已通过，本次分析未重跑这些验证。当前可显示“使用了什么、丢弃了什么、为什么失效、哪些信息必须保留”。对比计划与重规划的 goal、catalog、任务 revision/generation、记忆及观测版本。界面可以固定用户原文，但不能驱逐策略、当前停止状态或必要能力契约。跨调用差异只读 API 与比较界面已通过真实账本/浏览器验证，独立界面审查为 ship；后续补来源记录跳转及实体/世界观测有效性；无需重新建设已有查询和面板。界面的关联与哈希一致性不代表模型正确或机器人完成。

**记忆分层。** 分离原始观测、任务结果、人工注释和模型摘要；摘要保留覆盖范围及原文哈希。用户声明“电脑在实验室”与传感器近期观测到该电脑是不同证据类别。检索结果不能因被多次引用而升级为实时事实；对象位置和地图相关记忆需要更新与失效规则。

**自动化。** 延续现有失败事件诊断，下一步先支持明确条件的诊断/计划草稿生成。事件去重键包含规则版本及来源事件身份，规则有预算、冷却、范围、启停与未知结果处理。硬条件用确定性校验；模型可解释业务条件但不能放宽权限、停止条件或运动边界。自动执行恢复应单独定义可执行技能和现场验收范围。

**多 Agent。** 仅在基准显示收益后试点 Planner + 只读诊断/评审角色；记录父子关联、预算、取消和证据。所有角色产出建议，统一协调者提交最终草稿；禁止每个 Agent 各持一套机器人执行资源。

## 7. 对“取送笔记本电脑”示例的具体落地

`docs/meeting/laptop-decomposition-demo/generate.py` 明确注明机器人技能为场景假设、非实际执行记录。可继续用于沟通目标，但实际闭环还需要：

| 阶段 | 必须具备的实际输入或证据 | 缺少时的处理 |
|---|---|---|
| 目标澄清 | 实验室/会议室标识、交付位置、目标电脑身份或消歧条件 | 记录澄清项，不默认“唯一且可抓取” |
| 到达实验室 | 实际导航接口、有效地图/定位、资源与到达标准 | 不派发不存在的导航能力 |
| 寻找电脑 | 实际检测/识别结果及 object ID、位姿、时效 | 搜索失败按预算结束或请求人工信息 |
| 抓取 | 经校验的目标输出、操作技能、持物证据 | 未确认稳定持有不进入携物返程 |
| 携物返回 | 持物条件、导航约束、实际执行状态 | 失去持物或定位有效性时进入规定的停止/恢复流程 |
| 放置与交付验证 | 目标区域、释放结果、独立观测及稳定性标准 | 不将技能返回文本或模型自述当作成功 |

DAG 中位置、对象等由实际前序输出引用传递；模型不能预写感知输出。失败补偿按阶段设计：空手导航失败与持物途中失败需要不同的恢复前提，不能统一“重试整条任务”。

## 8. 实施顺序与验收门槛

以下工作量为熟悉工程的单开发者粗估，用于排序；不包含设备到位等待，不是交付承诺。

| 阶段 | 交付与主要文件 | 依赖 | 验收门槛 | 粗估 |
|---|---|---|---|---|
| P0 基线整理 | 统一 PROJECT_STATUS/APPLICATION_LAYER_PLAN 的当前结论与历史记录，建立能力—代码—证据清单 | 当前工作区 | 每个“已完成”限定实际验证范围；消除重复建设项 | 1–2 人日 |
| P1 上下文可追溯性 | 已有主要调用 Bundle、只读查询、单记录/差异面板；补来源跳转及诊断缺口，收敛实体/完成条件 schema | P0 | 实际请求与保存记录一致；失效/未知版本被拒绝；已有记录仍可读 | 3–5 人日 |
| P2 世界状态基础 | world_models/world_state/WorldStateProvider 与真实消息映射 | 设备话题、消息、时钟、TF/地图约定 | 实际观测可回查；陈旧、断流、坐标不一致均明确处理；无默认观测 | 4–8 人日，不含接入等待 |
| P3 单技能闭环 | 一个实际设备技能适配器、派发前检查、停止与恢复证据 | P2 与允许动作范围 | 实际执行；重启查询同一 execution；取消后证据达标才释放资源；旧 authority 被设备端拒绝 | 5–10 人日，硬件联调另估 |
| P4 任务族评测 | 文件、实际单技能、多步真实任务；冻结输入与版本的评测报告 | P1，可先做文件族；机器人族依赖 P3 | 分别记录计划合法率、实际成功率、未知终态、重复副作用、成本和延迟 | 首轮 3–5 人日 |
| P5 选择性扩展 | 条件/定时诊断、多 Agent 只读评审、必要协议入口 | P4 显示明确收益 | 相比单 Agent 基线有可测收益，预算与控制边界保持 | 按入选能力另估 |

建议软件侧先完成 P0 和 P1 剩余项，同时收集 P2/P3 的设备契约；不为等待真机而制造仿真数据，也不把接口定义写成设备接入成功。

## 9. 验证方案

1. **契约与持久化：** 实际文件、账本、HTTP 服务及独立进程验证。关注版本变化、重复命令、进程中断、来源被修改和未知结果；避免只测字段能否往返。
2. **真实模型：** 使用环境已有服务配置与 API Key；保存实际输入、原始响应、模型标识、内容校验及成本/时延。HTTP 成功不算计划正确。
3. **执行闭环：** 模型输出进入现有命令与 Runtime；实际执行后由独立可观察结果核验。文件任务以实际字节/哈希验收；机器人任务以设备观测和任务后置条件验收。
4. **并发与恢复：** 测试迟到模型结果、取消竞争、设备断连、worker 重启、旧控制令牌和原执行查询；未知停止状态不释放资源。
5. **基准比较：** 固定任务族、允许能力、版本与预算，比较单 Agent 与新增机制的成功率、平均模型调用、成本和恢复质量。先做小规模探索，再决定足够的重复次数；单次成功不作统计结论。

具体机器人验收仍需设备/服务地址、ROS2 Action 或 HTTP 契约、允许动作范围、真实资源清单及独立停止证据。它们是 P2/P3 的输入依赖，不影响 P0/P1 推进。

## 10. 复用与交付边界

默认采用设计参考而非整库代码复制。当前根 package.json 声明 ISC，但未在根目录发现 LICENSE；这不能替代最终复用文件和依赖的许可核对。若未来引入包或复制实现，应固定提交/包版本并核对实际分发范围。

本次交付仅为此评估文档，不改变任务、运行端、用户工作区现有增量或 Momo 项目图。推荐的近期投入顺序是：整理真实能力基线 → 补齐上下文追溯 → 接入实际世界状态 → 验证单技能物理闭环 → 扩大任务族，再判断自动化和多 Agent 的收益。
