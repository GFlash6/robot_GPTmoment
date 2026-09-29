# 上下文 Provider 接口

ContextBuilder 负责解析当前会话或已接受的不可变提交快照，随后按固定顺序调用可信 Provider。Provider 只读取真实账本和资产来源，返回 ContextFragment 元组；预算和角色渲染仍由 ModelCaller 统一处理。模型不能通过参数注册 Provider。

## 当前实现

| Provider | 数据来源 | 校验 |
|---|---|---|
| GoalCapabilityProvider | 请求目标、技能目录 | 能力只包含契约字段 |
| TaskStateProvider | 当前任务账本 | 显式 robot 范围、revision、generation |
| SessionProvider | 已解析会话、摘要记录 | 摘要哈希、覆盖消息哈希、固定消息原文 |
| MemoryProvider | 已绑定记忆及资产 | robot 范围、有效期、绑定版本、实际字节 |
| AssetProvider | 会话绑定资产 | v1 绑定、精确登记记录哈希、实际字节与 robot 范围 |
| SelectionProvider | UI 选择对应的任务账本 | TTL、版本、选中节点存在性；恢复使用当前任务状态而非旧 UI 选择 |

接口位于 `robot_agent/context_providers.py`：`ContextProvider.collect(store, inputs: ProviderInput) -> tuple[ContextFragment, ...]`。输入包含同一请求、目录和已解析会话；没有会话时会话相关 Provider 返回空元组。必需来源失效时抛出异常，禁止捕获后静默丢弃。Builder 深拷贝请求、目录和会话，并为各 Provider 单独复制输入；调用返回时检测输入变化并拒绝违反只读约定的结果。返回片段与 Bundle.request 也分别复制，调用方修改嵌套字典不会回写原始目录、请求或另一轮构造结果。这里提供数据隔离，不是深度不可变对象或插件安全沙箱；Provider 仍可访问真实 Store，必须是可信服务端代码。

Builder 校验 Provider 名称唯一、返回类型和片段 ID 唯一。每个片段 metadata 增加 `provider` 和 `provider_contract_version=1`，实际模型调用的 ContextManifest.sources 会保存这两个字段。Bundle.diagnostics 记录各 Provider 的片段列表，包括本次没有适用来源的 Provider；它不是执行成功证据。

## 完整上下文包的持久化

`context_codec.py` 为 ContextBundle 定义独立的 `schema_version=1`，保存 request（含完整 GoalContext）、fragments 和 diagnostics。它与 planning_contexts 的提交快照版本各自独立。规划和重规划先编码并重新解析 Bundle，再使用解析后的片段准备模型输入；真实模型记录通过 `context_bundle_id` 和 `context_bundle_hash` 关联 `context_bundles` 集合中的完整内容。

编码器仅接受 JSON 类型，拒绝非字符串键、非有限浮点数、bytes、嵌套 tuple、循环和超过 64 层的嵌套。读取器拒绝未知版本、未知结构字段、非法请求身份、非法证据 ID、重复片段和不一致的目标 disposition。任意 content/metadata 内部的业务字段仍由对应 Provider 契约负责，不将通用 JSON 校验冒充世界状态 schema。

已有模型记录没有 Bundle 链接时继续保留，不补造历史上下文；尚未存在的无版本 Bundle 不推断为 v1。恢复 Bundle 只用于复核历史输入，不提供绕过当前权限、来源时效和执行前置条件的任务提交入口。重新准备输入的一致性依赖相同模型配置、方法提示和渲染实现，原始 request.messages 仍是实际发送内容的证据。

规划及重规划的 ContextManifest.provider_diagnostics 进一步保存每个 Provider 的 `collected/empty` 状态、返回片段、实际纳入片段和因预算丢弃的片段及原因。`empty` 只表示返回空元组，不推断具体缺失原因，也不表示世界状态可用。旧 Manifest 可以没有该字段；未经过 Builder 的调用默认是空清单。本增量不声明所有模型方法均已接入 Provider 诊断，也不把失败后未生成的 Manifest 解释为成功记录。

`ContextBuilder.capabilities()` 和 `task_state()` 保留兼容入口；默认调用方无需调整。自定义 Provider 列表仅供可信服务端组合，不能视为插件权限沙箱。当前为接口版本 1，不宣称跨版本序列化迁移已经完成。

## 世界状态接入边界

当前没有 WorldStateProvider 生产实现。实际 ROS2 发现结果仍只有诊断主题，不能从这些消息推断位姿、电量、对象或地图。来源记录见 `validation/context-provider-ros-discovery.json`。

后续实际适配器应使用同一接口，并在生成 world_state/data 片段前核查真实来源、时间域、观测时效、坐标系和地图版本。没有设备观测时报告缺失，不生成默认位姿或默认成功状态。具体 schema 需结合实际设备消息确定，不能把普通文件或模型文本标为传感器观测。

## 验证证据

[真实模型与执行记录](validation/context-providers-live.json) 保存实际请求关联的 Manifest、Provider 版本、模型响应 ID、实际 worker 文件核验结果及原始报告哈希。2 项真实模型测试通过；31 项实际文件/账本测试与 9 个子测试通过。没有使用替代模型或虚构机器人观测。

## 规划快照的持久化版本

`context_snapshot.py` 统一创建和读取规划快照。新记录写入 `schema_version=1`；既有完整无版本记录按 v0 只读解释，不自动重写。未知版本、缺失目标/能力哈希或不完整谱系均拒绝。当前兼容范围是现有 planning_contexts 记录，不代表所有 Context 类型的跨版本迁移已经完成。

读取器检查记录身份、会话与目标内容哈希、规范化 GoalContext、目标原文与会话一致性，并按调用点核对 robot、session、catalog。派生记录检查父记录整体哈希；除 history_summary 绑定外，不允许更改原始会话、目标和能力目录。谱系重复或超过 32 层会拒绝。

新草稿将整体 `context_snapshot_hash` 传递到命令和任务；草稿提交、worker 应用及自动恢复都复核绑定。提交后记录发生变化时，worker 拒绝命令，不创建任务或派发技能。这里的哈希提供完整性检查，不替代本地数据库的访问控制。

历史记录可缺少新增加的整体绑定哈希，但仍必须通过内容和谱系校验。首次生成的 v1 快照与 v0 的内容格式兼容，派生快照会使用 v1 并继续引用原父记录的实际哈希。

实际旧记录兼容证据：[context-snapshot-legacy.json](validation/context-snapshot-legacy.json)。

快照实际验收：[context-snapshot-live.json](validation/context-snapshot-live.json)。环境真实模型的摘要恢复与快照变更拒绝两条链路通过；已接受的原计划实际执行并验证文件哈希，损坏快照命令未创建任务。38 项回归与 9 个子测试通过。


上下文隔离与诊断增量：Builder 为各 Provider 隔离嵌套输入，拒绝调用期间的输入修改，并将返回片段与调用方对象分离；规划/重规划 Manifest 保存 Provider 返回、纳入及预算丢弃清单。22 项实际文件/账本回归通过；环境真实 qwen3.7-plus 的目标分析及两次规划均取得有效原始响应，独立 worker 完成文件归档及哈希核验，记忆过期后的命令拒绝执行。证据见 [context-isolation-live.json](validation/context-isolation-live.json)。这不是 Provider 沙箱或完整 Context 序列化迁移；世界状态与机器人验收仍未完成。


完整上下文包增量：新增 context_codec.py，提供 ContextBundle v1 编码与严格读取；规划/重规划保存完整包和绑定哈希，并使用解析后的片段生成模型输入。36 项回归通过；环境真实 qwen3.7-plus 完成目标分析和两次规划，两份持久包均能精确重建实际 messages 与 response_format。独立 worker 完成真实文件归档及哈希核验；未知快照版本和提交后快照变化均拒绝。证据见 [context-codec-live.json](validation/context-codec-live.json)。旧模型记录不补造 Bundle，解码不授予执行权限；世界状态和真机验收仍未完成。


失败节点解释追溯增量：task.explain 在发送真实模型请求前，原子保存完整 ContextBundle、哈希、来源/预算 Manifest 和请求准备参数；实际缺失文件执行失败后，环境 qwen3.7-plus 返回的解释通过文件名、错误含义及来源引用检查。保存包重建的 messages 与 response_format 和实际请求一致，任务保持 failed。1 项真实模型测试（4 条实际响应）及 23 项实际文件/账本/HTTP 回归通过；证据见 [explanation-context-live.json](validation/explanation-context-live.json)。此范围不包含其他模型方法的统一追溯、旧记录回填、世界状态或真机验收。


目标分析与澄清追溯增量：预算预检现在返回完整 ContextBundle，goal_analysis 和 goal_clarification 保留来源诊断，并在网络调用前原子保存 Bundle/哈希、Manifest、实际请求及准备参数；直接调用没有 Provider 时不补造诊断。实际多轮验收发现并修复澄清参数经持久化改变 JSON 键顺序、导致实际提示无法精确重建的问题。普通文件闭环、澄清/失败解释、自动摘要后文件闭环三条通过路径共保存 13 条真实模型响应；23 项实际文件/账本/HTTP 回归通过。首次失败与修复后重验分别保留，见 [goal-context-live.json](validation/goal-context-live.json)。详细边界见 [模型上下文证据](MODEL_CONTEXT_EVIDENCE.md)；摘要/自动化完整 Bundle、世界状态和真机闭环仍未完成。


自动诊断上下文包增量：explain_event 已保存完整 ContextBundle v1、哈希与准备参数，并在真实网络调用前同 Manifest、requesting 记录原子提交。上下文只表示绑定的历史事件，不附会当前任务 revision/generation，不补造 Provider 诊断。实际事件诊断、SIGKILL/SIGINT 中断和显式重试共 4 项专项通过，另有 23 项实际文件/账本/HTTP 回归通过；5 条实际响应与原错误一致，2 条中断请求保持 unresolved，7 份输入均准确重建且来源事件哈希与账本一致。证据：[automation-context-live.json](validation/automation-context-live.json)。供应商是否接收中断请求仍未知；摘要完整追溯、世界状态、真机和 Momo 同步仍未完成。


会话/恢复摘要追溯增量：每个分块使用 data 权限的 summary-source 片段，完整包、Manifest、来源字符范围/哈希、请求准备参数及实际消息在模型调用前原子保存。分块预检与发送统一构造；恢复摘要绑定原规划快照与任务版本，已有编辑/取消 guard 保留。四条通过路径共 15 条真实模型响应、8 个摘要包；2 项实际文件任务完成哈希验证，1 项取消任务保持 canceled，并发编辑路径拒绝绑定旧摘要。23 项实际文件/账本/HTTP 回归通过。首次测试范围输入缺失及真实规划拒绝均保留，修正真实前置输入后重验相关路径；详见 [summary-context-live.json](validation/summary-context-live.json)。这些记录不代表跨提示版本重放、实时世界状态或真机验收，Momo 同步仍待完成。


AssetProvider 的 asset-evidence 元数据现含 asset_bindings，明确保存绑定版本，scope 为 stored_asset_bytes_and_bound_record。它核验归档字节与登记记录，不把文件注释升级为世界事实。旧的非空 ID-only 会话需要重新附加资产；历史 Bundle 保留原样只读。生命周期与实际故障验证见 [资产上下文绑定](ASSET_CONTEXT_BINDINGS.md)。


完成契约增量：SessionProvider 在普通规划提供操作者明确设置的 completion-contract 必需片段；TaskStateProvider 对既有任务提供冻结契约，存在实际检查记录时另提供 data 权限 completion-evaluation（实际值、预期值、逐项状态、执行与来源身份）。要求与执行证据分开，模型不能修改冻结验收标准。查看任务可使用另一会话；生成该任务修订草稿则要求会话契约与任务一致。说明与证据见 [完成契约](COMPLETION_CONTRACTS.md)。
