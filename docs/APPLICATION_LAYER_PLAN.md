# 应用动作、会话与机器人执行闭环

用户授权：按 Agent-Native 借鉴方案完善现有工程，不使用 superpowers。
沿用 Python Runtime、DBOS、技能协议及现有 React 界面；外部框架仅作为设计参考。

## 交付及验收

- M1：统一动作注册、可信主体与机器人范围检查、幂等命令队列、原子命令回执、HTTP/CLI 入口。重复提交不创建第二任务；命令接受不代表机器人停止；控制与 worker 推进无覆盖；崩溃恢复不重复应用。
- M2：持久会话与目标澄清、界面选择快照、Session/UI/Memory/World Provider、上下文来源清单。过期选择被拒绝或明确报告；不能把 UI 和模型文本升级为环境事实。
- M3：计划草稿与版本绑定、执行控制、失败节点解释与证据关联。迟到草稿不覆盖取消；未停止的执行不能被修订；UI 显示请求和实际执行的不同状态。
- M4：核对实际设备接口并接入可用技能；记录真实观测和进程恢复证据。用户明确禁止仿真模拟，没有实际设备运行证据时保持未验收。

验证约束：不使用 mock 或仿真；AI 验证只使用系统环境中的真实配置和 API Key，保留实际模型输入、响应、内容校验及真实执行证据。文件任务使用实际文件和实际进程，不替代机器人验收。

## 实施边界

应用动作层只操作任务管理接口，不直接调用机器人运动；HTTP 身份来自服务端凭据映射，CLI 身份来自本机操作员。模型参数不能指定角色或权限。
控制命令与 Runtime 转换在同一 SQLite 事务中提交。任务级进程锁协调 DBOS 线程及不同连接，外部技能 IO 不放入命令事务。
观察 API 继续只读；应用服务独立提供动作入口。原有低层 Runtime API 保留，新的外部控制入口统一入队。

## 当前状态

M1：共享动作、HTTP/CLI、幂等队列与原子回执已实现，真实文件/HTTP/进程验证通过。
M2：持久会话、选择上下文、实际资产证据与来源清单已实现，多轮真实模型验证通过；已新增按机器人范围的 FTS5 记忆检索、版本绑定和实际来源复核，真实模型消费检索结果并执行文件任务通过；工作台记忆选择及真实浏览器到模型/worker 闭环已验收；摘要已有后续真实模型及浏览器验收，实时世界状态仍未完成。
M3：草稿版本/哈希绑定、控制入口和失败节点解释已实现；真实模型文件执行与浏览器节点解释通过，更多长程任务族及现场控制仍需验收。
M4：未完成。实际 ROS2 发现仅有 /parameter_events、/rosout；已向用户请求真实设备服务地址或 Action 类型和允许动作范围，不启动仿真。

本次成果不代表原路线全部完成；失败事件自动诊断已接通；定时/条件自动化、多 Agent、真机安全与高可用等仍在后续范围。

增量验收：自动重规划已继承提交时会话快照、语义目标和绑定记忆，读取最新任务失败状态；实际源文件移除、真实模型改用备用路径、worker 最终哈希验证通过。证据：validation/replanning-context-live.json。工作台记忆选择已完成真实浏览器验收，见 validation/memory-browser-live.json；长历史摘要已有后续验收，实时世界状态及真机验收仍未完成。

历史摘要增量：已实现显式 session.summarize，保留近期/固定原文、覆盖消息哈希和实际模型响应，接入目标分析与规划上下文；真实模型摘要→计划→实际文件执行通过。超过单次输入上限的分块处理已完成实际模型/执行与并发拒绝验收；共享会话分析/规划动作的可配置自动预算触发已完成真实模型验收；工作台策略/摘要控件已完成真实浏览器验收，不标记整个长历史能力已完成。证据：validation/session-summary-live.json。

分块摘要：普通/超预算历史真实模型验收2项通过，并发编辑拒绝不完整摘要1项通过；记录与范围见 validation/chunked-session-summary-live.json。共享会话分析/规划动作的自动预算触发已接通；工作台摘要操作已完成真实浏览器验收；Runtime 恢复预算扩展已有下述真实验收；实时世界状态和真机验收继续待完成。

自动预算增量：两条真实路径通过——goal.analyze 超预算自动整理、plan.propose 单独超预算自动整理并返回新版本草稿。均执行实际文件并验证哈希。证据 validation/automatic-session-budget-live.json。

工作台摘要增量：保存策略、固定原文、手动生成及引用原文查看已接通；真实浏览器到模型规划和 worker 文件核验通过，刷新恢复/原文变更失效提示也已验证。证据 validation/summary-browser-live.json。


恢复预算实现增量：新增 recovery_budget.py，在提交时不可变会话快照上执行预算预检和分块摘要，保持固定原文、最新任务账本及绑定记忆；派生快照记录父快照哈希，不修改当前会话或原始提交快照。每次摘要调用前后及规划返回后校验任务版本、原快照和控制请求。策略关闭或必需上下文无法容纳时拒绝调用；同一覆盖范围的既有摘要仍不适配时明确拒绝，不递归压缩。普通及预算受限恢复已完成真实模型、实际文件故障和 worker 哈希验证；实际摘要期间取消已通过真实模型并发验收：保留响应，不创建派生快照或修订计划，worker 最终取消任务。证据见 [恢复预算验证](validation/recovery-budget-live.json)。完整长程任务族、世界状态与真机验收仍未完成。

Provider 接口验收：31 项实际文件/账本回归及 9 个子测试通过；2 项环境真实模型闭环通过（记忆驱动规划、超预算快照恢复），均由 worker 完成文件哈希验证。实际 Manifest 已逐项核对 Provider 名称及接口版本。证据：[context-providers-live.json](validation/context-providers-live.json)。

快照实际验收：[context-snapshot-live.json](validation/context-snapshot-live.json)。环境真实模型的摘要恢复与快照变更拒绝两条链路通过；已接受的原计划实际执行并验证文件哈希，损坏快照命令未创建任务。38 项回归与 9 个子测试通过。


事件自动化增量：新增 automation.create/set-enabled/list/runs 共享动作和独立 automation-worker；实际失败事件按创建者与机器人范围持久入队，游标/预算/去重原子提交。实际模型解释引用精确错误和事件，未改变失败任务状态；queued 跨进程恢复、两个并发 worker 仅一次调用、暂停/范围/事件完整性检查通过。调用中 SIGKILL/SIGINT 与显式重新诊断已有增量验收；工作台操作已有下述真实浏览器验收；其他中断窗口、定时条件和自动恢复执行仍未验收。使用见 [EVENT_AUTOMATIONS.md](EVENT_AUTOMATIONS.md)，证据见 [event-automation-live.json](validation/event-automation-live.json)。


进程中断增量：实际 SIGKILL 和 SIGINT 后原请求均保持 unresolved，重启不重发；后续真实失败事件和 automation.retry 的实际模型响应已验证。重新诊断保留 retry_of、创建者及原不确定记录，受同一预算和幂等键约束。响应与诊断终态现以同一事务提交。证据：[automation-interruption-live.json](validation/automation-interruption-live.json)。供应商是否接收被中断请求仍未知，不能把缺失响应解释为未调用或已成功。


自动诊断工作台增量：创建、暂停/启用、诊断详情和显式重新诊断已接通；真实浏览器经共享动作创建规则，实际文件失败入队、来源损坏拒绝后重新诊断获得真实模型响应，刷新/轮询无额外模型调用。实际断开应用服务后保留上次诊断。证据：[automation-browser-live.json](validation/automation-browser-live.json)。世界状态和真机验收仍未完成。


上下文隔离与诊断增量：Builder 为各 Provider 隔离嵌套输入，拒绝调用期间的输入修改，并将返回片段与调用方对象分离；规划/重规划 Manifest 保存 Provider 返回、纳入及预算丢弃清单。22 项实际文件/账本回归通过；环境真实 qwen3.7-plus 的目标分析及两次规划均取得有效原始响应，独立 worker 完成文件归档及哈希核验，记忆过期后的命令拒绝执行。证据见 [context-isolation-live.json](validation/context-isolation-live.json)。这不是 Provider 沙箱或完整 Context 序列化迁移；世界状态与机器人验收仍未完成。


完整上下文包增量：新增 context_codec.py，提供 ContextBundle v1 编码与严格读取；规划/重规划保存完整包和绑定哈希，并使用解析后的片段生成模型输入。36 项回归通过；环境真实 qwen3.7-plus 完成目标分析和两次规划，两份持久包均能精确重建实际 messages 与 response_format。独立 worker 完成真实文件归档及哈希核验；未知快照版本和提交后快照变化均拒绝。证据见 [context-codec-live.json](validation/context-codec-live.json)。旧模型记录不补造 Bundle，解码不授予执行权限；世界状态和真机验收仍未完成。


多文件任务增量：新增内置 asset.verify-set，逐项核对实际资产字节和调用方预期哈希，拒绝重复资产、损坏数据及跨机器人范围。41 项真实文件/账本回归通过；环境真实 qwen3.7-plus 完成目标分析和七节点计划，独立 worker 完成三个复制、三个归档及一次集合核验，随后独立重读六份产物验证哈希。证据见 [multifile-live.json](validation/multifile-live.json)，范围见 [多文件验收](MULTIFILE_VALIDATION.md)。这是一个明确约束的真实任务样本，不代表统计规划质量或真机验收。


HTTP fencing 增量：显式控制域、单账本单调令牌、执行端持久权威检查和回执绑定已接通；要求同名独占资源。17 项真实 HTTP/文件/控制回归通过；新增 worker 恢复后第二执行令牌递增验证通过。真实环境 qwen3.7-plus 的目标分析、规划、独立 worker 远端文件执行与哈希核验通过。证据见 [fencing-live.json](validation/fencing-live.json)。旧令牌拒绝保持 Runtime unknown 和资源占用，不冒充停止；机器人驱动、多主仲裁及硬件急停仍未验收。


旧执行停止核对增量：当前较新控制者可显式请求 reconcile，服务端调用实际 cancel 并保存停止证据；旧执行只读回取结果后，Runtime 才解除未知状态并按真实终态释放资源。12 项真实 HTTP/控制回归通过，覆盖错误令牌、重复核对和服务重启；真实环境 qwen3.7-plus 的计划实际复制 512 字节后被接管，核对后独立 worker 结束为 canceled，部分字节保留且无成功冒报。证据见 [fencing-reconciliation-live.json](validation/fencing-reconciliation-live.json)。机器人停止、多主仲裁和自动接管仍未完成。


事件分页增量：共享 task.events-page 提供任务绑定游标、固定读取上界和 1–500 条分页，保留原 task.events。8 项实际 HTTP/文件回归通过（3 项其他实时模型测试未在该命令中运行）；本轮真实 qwen3.7-plus 七节点文件任务完成后，分页结果与完整账本逐条相等，重复读取不新增模型请求或执行。证据见 [event-pages-live.json](validation/event-pages-live.json)，协议见 [事件分页](EVENT_PAGES.md)。尚未迁移前端或接入推送，不宣称任意历史删改检测。


工作台事件增量：已接通任务选择、每页 50 条、手动后续页及读完后的增量轮询；断连保留记录，切换任务/凭据清理旧上下文。真实浏览器验证使用已有实际模型任务的账本副本（17 条事件）及实际暂停/恢复和文件执行产生的 69 条事件，验证两页加载、服务重启、去重及权限上下文清理；浏览器未新增模型或执行记录。构建通过，独立界面审阅对列出的可读性修正给出 ship。证据见 [event-browser-live.json](validation/event-browser-live.json)。本次不增加模型生成或真机验收声明。


失败节点解释追溯增量：task.explain 在发送真实模型请求前，原子保存完整 ContextBundle、哈希、来源/预算 Manifest 和请求准备参数；实际缺失文件执行失败后，环境 qwen3.7-plus 返回的解释通过文件名、错误含义及来源引用检查。保存包重建的 messages 与 response_format 和实际请求一致，任务保持 failed。1 项真实模型测试（4 条实际响应）及 23 项实际文件/账本/HTTP 回归通过；证据见 [explanation-context-live.json](validation/explanation-context-live.json)。此范围不包含其他模型方法的统一追溯、旧记录回填、世界状态或真机验收。


目标分析与澄清追溯增量：预算预检现在返回完整 ContextBundle，goal_analysis 和 goal_clarification 保留来源诊断，并在网络调用前原子保存 Bundle/哈希、Manifest、实际请求及准备参数；直接调用没有 Provider 时不补造诊断。实际多轮验收发现并修复澄清参数经持久化改变 JSON 键顺序、导致实际提示无法精确重建的问题。普通文件闭环、澄清/失败解释、自动摘要后文件闭环三条通过路径共保存 13 条真实模型响应；23 项实际文件/账本/HTTP 回归通过。首次失败与修复后重验分别保留，见 [goal-context-live.json](validation/goal-context-live.json)。详细边界见 [模型上下文证据](MODEL_CONTEXT_EVIDENCE.md)；摘要/自动化完整 Bundle、世界状态和真机闭环仍未完成。


自动诊断上下文包增量：explain_event 已保存完整 ContextBundle v1、哈希与准备参数，并在真实网络调用前同 Manifest、requesting 记录原子提交。上下文只表示绑定的历史事件，不附会当前任务 revision/generation，不补造 Provider 诊断。实际事件诊断、SIGKILL/SIGINT 中断和显式重试共 4 项专项通过，另有 23 项实际文件/账本/HTTP 回归通过；5 条实际响应与原错误一致，2 条中断请求保持 unresolved，7 份输入均准确重建且来源事件哈希与账本一致。证据：[automation-context-live.json](validation/automation-context-live.json)。供应商是否接收中断请求仍未知；摘要完整追溯、世界状态、真机和 Momo 同步仍未完成。


会话/恢复摘要追溯增量：每个分块使用 data 权限的 summary-source 片段，完整包、Manifest、来源字符范围/哈希、请求准备参数及实际消息在模型调用前原子保存。分块预检与发送统一构造；恢复摘要绑定原规划快照与任务版本，已有编辑/取消 guard 保留。四条通过路径共 15 条真实模型响应、8 个摘要包；2 项实际文件任务完成哈希验证，1 项取消任务保持 canceled，并发编辑路径拒绝绑定旧摘要。23 项实际文件/账本/HTTP 回归通过。首次测试范围输入缺失及真实规划拒绝均保留，修正真实前置输入后重验相关路径；详见 [summary-context-live.json](validation/summary-context-live.json)。这些记录不代表跨提示版本重放、实时世界状态或真机验收，Momo 同步仍待完成。


上下文只读查询增量：观察服务新增 GET /api/v1/models/{id}/context，同一读事务展开已有 Bundle/Manifest，并报告包哈希、引用与 request/phase 关联问题。实际模型账本副本 HTTP 查询、完整读前后对比、缺失/损坏注入与真实旧记录检查通过，相关 7 项测试通过；本轮新增模型调用为 0，没有执行任务。证据：[context-observer-live.json](validation/context-observer-live.json)。该接口不是完整请求重建、Manifest 全文认证或前端页面交付；真机、WorldState、其他工程范围及 Momo 同步仍待完成。


### 2026-09-22 上下文差异查询增量

单记录上下文面板已完成真实账本浏览器验证及独立界面审查（ship），见 [context-browser-live.json](validation/context-browser-live.json)。另新增两记录上下文差异只读 API，按明确方向比较身份、来源、内容哈希、预算与诊断，不推断调用血缘；缺失或损坏证据明确不可比较。真实历史模型账本 16 组比较及实际 HTTP/文件/账本回归共 8 项通过，副本故障恢复后逻辑账本哈希与来源一致；无新增模型调用、mock 或仿真。证据：[context-diff-live.json](validation/context-diff-live.json)。双记录比较界面见后续增量；世界状态和设备闭环仍待完成，未同步 Momo 图。


### 2026-09-22 上下文双记录比较界面增量

模型记录页面已接入固定/输入/清除基准与明确方向的上下文比较，展示预算、来源、内容哈希、请求身份及诊断变化。切换任一记录清除旧结果，同组合断连保留上次结果并标明过期，缺失或损坏证据显示不可比较。真实浏览器读取 5 条历史模型记录，验证键盘操作、正反向与自身比较、未应用输入隔离、断连/重连、损坏/恢复和桌面/手机布局；无新增模型调用、mock、仿真、页面异常或浏览器写操作，最终账本哈希保持不变。构建通过；独立界面审查 disposition 为 ship、无实质修正，范围仅此增量。证据：[context-diff-browser-live.json](validation/context-diff-browser-live.json)。实体/完成条件契约、世界状态、实际设备闭环及 Momo 同步仍待完成。


### 2026-09-22 资产上下文版本绑定增量

新增 AssetBinding v1，session.attach-assets 绑定真实登记记录与字节身份；Provider、草稿发布、提交、worker 接受及新技能派发复核资产。旧非空 ID-only 附件不会自动回填，需要显式重新附加并生成新草稿；历史可读。真实环境 qwen3.7-plus 的 4 条响应输入准确重建，元数据/字节变化分别在提交、命令处理、派发与恢复处被拒；恢复后实际 worker 核验资产字节/大小/哈希通过。专项 1 项、相关回归 37 项通过，无 mock 或仿真。证据：[asset-binding-live.json](validation/asset-binding-live.json)。此引用只代表归档资产，物理实体定位、世界状态和通用完成条件仍未完成；Momo 未同步此增量。


### 2026-09-22 显式完成契约增量

新增操作者 v1 completion_contract，独立于模型计划，绑定最终注册 verifier 的输出检查；会话设置会使旧分析/草稿失效，任务接受后冻结，修订与恢复保留契约。Runtime 区分技能 reported_status 与任务 completion_evaluation，实际验收不满足时即使技能成功也记为失败。真实模型+独立 worker 的原文件/规划后实际修改文件两条路径通过：一成功、一按哈希/大小要求失败；通过运行 4 条真实响应均重建输入，首轮退出码断言纠正记录保留（两轮共 8 条响应）。专项 1 项、相关回归 40 项通过，无 mock 或仿真。证据：[completion-contract-live.json](validation/completion-contract-live.json)。契约仍需操作者显式提供，不代表自然语言目标自动覆盖、物理任务指标、世界状态或硬件闭环完成；专用编辑 UI 与 Momo 同步仍待完成。


完成契约恢复专项：新增真实模型验收，实际修改主文件导致归档技能成功但任务哈希/大小验收失败；模型接收真实检查差异与冻结要求，改用操作者授权备用文件，独立 worker 完成原字节归档和核验。接受任务后清除当前会话契约不影响恢复要求。三条实际响应输入准确重建，专项 1 项通过、相关回归 40 项通过，无 mock、仿真或生产逻辑改动。证据：[completion-recovery-live.json](validation/completion-recovery-live.json)。范围限一个文件恢复场景；世界状态、物理实体和真机闭环仍未完成。


动作发现契约增量：GET /actions 增加 catalog_version 与每动作版本、哈希、副作用类别、幂等/模型调用行为声明；审计记录关联实际使用的契约，发现结果保留独立 schema 副本。仍按基础权限筛选，实际调用继续检查机器人范围和状态。真实 HTTP 发现→提交→独立 worker→文件 SHA256 验收通过，同时覆盖认证、缺失幂等键与跨机器人拒绝；相关 17 项通过，无新增模型调用、mock 或仿真。详情见 [应用层说明](APPLICATION_LAYER.md)。不代表所有嵌套输出 schema、远程多租户、世界状态或真机已完成。


世界状态接入复核：实际 ROS 图发现仅检查节点自身诊断发布者，未发现设备节点或 Action；已审阅相邻工程真实 G1 状态/运动桥并归档源码哈希。明确接收时间与采样时间、默认 covariance、坐标/速度语义及执行身份/停止证据缺口，见 [G1 接入契约](G1_INTEGRATION_CONTRACT.md) 和 [发现记录](validation/world-source-discovery.json)。无桥接启动、mock、仿真、运动或新增模型调用；世界状态与真机仍待实际连接信息及现场验收。
