# 应用动作与任务协作

当前新增 Python 共享动作层、持久命令队列、会话、计划草稿和任务协作页面。Agent-Native 仅作为架构参考，没有引入其运行时或替换机器人 Runtime。

## 运行

在项目根目录使用已有 `.venv`。应用服务和 worker 指向同一个运行目录：

```bash
npm run build --prefix ui
.venv/bin/python -m robot_agent.application --root .runtime --auth-config .runtime/application-auth.json --static ui/dist --port 8768
```

另一个终端启动执行端：

```bash
.venv/bin/robot-agent --root .runtime run
```

`application-auth.json` 示例只包含环境变量名称，不包含凭据值：

```json
{
  "principals": [
    {
      "subject": "operator",
      "token_env": "ROBOT_AGENT_ACTION_TOKEN",
      "permissions": ["planning.use", "tasks.read", "tasks.submit", "tasks.control", "assets.read"],
      "robots": ["r1"]
    }
  ]
}
```

在服务进程环境配置实际 `ROBOT_AGENT_ACTION_TOKEN`。打开 `http://127.0.0.1:8768`，进入「任务协作」，输入该操作凭据。凭据只保存在当前 React 内存中，不进入 URL 或浏览器存储。此凭据不是模型 API Key。

模型配置优先使用环境变量 `ROBOT_AGENT_MODEL_CONFIG` 指向的 JSON 文件；未指定时读取 `base_url` / `llm_model` / `API_KEY`，或 `OPENAI_BASE_URL` / `OPENAI_MODEL` / `OPENAI_API_KEY`。基础 URL 自动补齐 `/chat/completions`；没有默认模型或默认回答。模型密钥只由服务端环境读取。

应用服务保持 loopback 部署。原有 `/api/v1` 观察接口仍是本地只读接口；新增 `/actions` 使用独立凭据。此版本不提供公网部署或完整多租户隔离保证。

## 操作流程

1. 创建目标会话，显式点击「分析当前目标」调用真实模型。
2. 若模型提出问题，填写补充信息并保存，再分析当前目标。每次修改均有 session revision。
3. 需要感知或读取证据的目标保持 `needs_grounding`，允许生成包含实际取证工作的计划；需要操作者澄清的目标阻止规划。
4. 检查计划节点、参数、最终 verifier、版本与哈希，再点击「提交当前计划」。草稿有效期为五分钟；引用任务选择时，不能超过选择的有效期。
5. 命令先返回 `accepted`，worker 原子应用后为 `applied`；机器人或文件任务是否完成，以任务和执行结果为准。
6. 在任务 DAG 选中当前版本节点，点击「在任务协作中分析此节点」，到对应会话关联节点，再调用「解释所选节点」。解释显示模型引用的实际账本记录和未知项，不修改任务状态。

只读观察服务独立启动时也会显示协作入口，但应用动作不可用，页面会明确显示连接失败。会话 ID 可以复制并在相同身份下恢复；切换 UI 页面不会清除当前会话。

## 共享动作契约

`GET /actions` 返回按主体基础权限筛选的动作契约（catalog_version=1）；发现动作不代表已满足机器人范围、所有权、额外权限或运行状态要求。所有动作使用 `POST /actions/<name>` 和 JSON 参数，身份来自服务端 token 映射。客户端不得在参数里注入角色或权限。

写操作需要 `Idempotency-Key`，可选 `X-Request-ID` 用于调用关联。CLI 的 `action <name> <JSON文件> --idempotency-key <key>` 调用相同 Python 注册表。

| 动作 | 语义 |
|---|---|
| task.list / task.get / task.events | 范围内的真实任务与事件 |
| asset.get | 资产元数据；不会宣称重新核验字节 |
| task.submit | 校验并接受计划提交命令 |
| task.pause / cancel / resume / revise / preempt | 带 expected_revision / expected_generation 的控制命令 |
| command.get | accepted / applied / rejected 回执；confirmed_stopped 固定为 false |
| session.create / get / message | 主体隔离的持久会话与补充条件 |
| session.attach-assets | 核验实际资产字节并绑定登记记录版本；后续使用边界复核 |
| selection.set | 服务端校验任务、步骤与版本，保存五分钟选择快照 |
| goal.analyze | 使用实际会话和能力上下文进行目标分析及澄清 |
| plan.propose / plan.submit | 生成版本绑定草稿，提交确切哈希对应的计划 |
| task.explain | 真实模型解释实际选中记录，引用必须来自已提供记录集合 |

CLI `submit/pause/cancel/resume/preempt/replan` 现入队。`submit` 的 `id` 和 `task_id` 指向预分配任务 ID，但 worker 应用提交命令前任务记录尚未创建，需使用 `command.get` 查看回执。`run --until <task_id>` 支持等待尚未应用的提交命令。

CLI `agent` 经过会话分析、草稿与命令队列；若需要澄清则返回会话信息，不提交执行。优先级和自动重规划预算保留。

## 持久化与并发

- 每个账本保持单 worker 所有权；任务级文件锁协调不同 SQLite 连接及 DBOS 线程。
- 命令应用、Runtime 账本变更和命令回执处于同一个事务；嵌套 Runtime 事务使用 savepoint。
- 外部机器人/文件技能 IO 不在命令事务内执行，仍由 Runtime 先持久化 execution intent 再调用技能。
- 相同主体和幂等键不重复提交；参数不同则拒绝。模型调用中的进程故障不会被自动重放，未完成请求保留为 unresolved，需检查记录后显式重新发起。
- 已接受的取消命令优先于尚未应用的修订、恢复和迟到自动规划。
- 草稿提交及 worker 应用时核对技能目录与有效期，旧会话/任务版本和不同计划哈希被拒绝。

## 证据与边界

关联链：session → turn → action_call → command → task → execution → evidence。模型记录保存实际 messages、请求模型、原始返回、返回模型和 response ID；不保存 HTTP 鉴权头。

ContextBuilder 新增会话、已解析 UI 选择和实际资产字节证据。Manifest 保存使用来源、权限层次、版本元数据和证据引用。资产证据说明存储的字节，不自动等同于机器人当前环境状态。

当前验证使用真实文件、进程、HTTP 服务、浏览器和环境配置中的真实模型，没有 mock 或仿真。真实设备接口、传感器世界状态 Provider、运行端 fencing、硬件停止与跨主机调度尚未验收；事件自动化及多 Agent 功能尚未实施。

## 检索记忆并带入会话（后续增量）

`memory.search` 接受 `text`、`robot_id`、可选 `kind` 和 `limit`（1–20，默认5）。它使用现有 SQLite FTS5 的词组检索；先过滤机器人范围和有效期再限制数量。每条结果附带 `record_hash` 和已读取核验的 `verified_assets`。这是结构化文本检索，不是向量或语义相似度检索。

调用主体需要 `memory.read` 与 `assets.read`。记忆记录及其全部来源资产必须属于指定机器人命名空间；没有 robot_id 的历史条目不自动混入。缺失或损坏的来源会明确报错，不退化成无证据文本。

`session.attach-memories` 参数为 `session_id`、`expected_revision`、`memories: [{memory_id, record_hash}]`（最多10条）。绑定更新会话版本并使旧目标分析失效。再次构造上下文、提交草稿以及 worker 应用命令时，都会重新检查记录哈希、有效期和实际来源字节；已接受但尚未执行的命令也不能使用失效记忆。失效后需重新检索、绑定和分析。

上下文将文本标记为 `stored_annotation`，权限为 `data`：核验文件字节并不证明注释内容的语义真实性。每条上下文片段和规划 Manifest 保存记忆版本、来源资产 ID 与核验时间。此入口可通过统一动作调用，工作台现已支持关键词检索、来源查看、选择绑定和清除。绑定会替换现有记忆并使旧目标分析和草稿失效；切换会话会清空检索结果。

真实记忆验收曾发现模型把 `save.asset_id` 错写成 `save.output.asset_id`。本地 file.ingest / asset.verify 已补全封闭输出 schema；计划校验会拒绝该 schema 明确排除的引用路径，在创建任务前报错。对于开放 schema 或组合 schema，框架仍保留执行时校验，不宣称已经静态证明所有引用。

## 自动重规划的会话快照

计划草稿生成时保存 planning_contexts，包含会话原文、语义目标、来源哈希和 catalog_hash；提交命令将 snapshot ID 绑定到任务。自动重规划读取该快照并读取最新任务账本，保留人工澄清与绑定记忆；提交后的新会话消息不自动修改既有任务。旧 UI 选择不作为自动恢复的当前事实，当前节点状态由 Runtime 账本提供。记忆在上下文构造及模型返回后均复核有效期、版本和实际资产。

真实模型验收见 [replanning-context-live.json](validation/replanning-context-live.json)：实际移除源文件触发技能失败，模型依原会话及记忆选择备用文件，真实 worker 完成归档和哈希验证。模型配置来自系统环境。本次只覆盖文件恢复；不代表机器人停止、长历史摘要或所有自动恢复故障均已验收。

工作台实际浏览器验收见 [memory-browser-live.json](validation/memory-browser-live.json)：真实记忆检索和绑定→环境真实模型输入/响应→实际 worker 文件归档及哈希校验。另验证空结果、清除绑定、失效草稿、会话隔离与移动端无横向溢出。运行 `node ui/scripts/test-memory-ui.mjs` 前需 `npm --prefix ui run build`，模型配置由服务端系统环境读取。

## 可追溯的历史摘要

共享动作 `session.summarize` 接受 `session_id`、`expected_revision`，可选 `keep_recent`（2–32，默认6）与 `pinned_turn_ids`（最多64条）。模型调用通过服务端实际环境配置执行；HTTP 与 CLI 复用同一动作、身份范围和幂等记录。例：

```json
{"session_id":"实际会话ID","expected_revision":8,"keep_recent":2,"pinned_turn_ids":["必须保留原文的实际消息ID"]}
```

CLI 可用 `robot-agent --root <账本目录> action session.summarize <参数JSON文件> --idempotency-key <唯一请求键>`。通过 `session.get` 的 turns 获取消息 ID。

该动作对旧消息原文重新摘要，保留最近消息和指定固定消息的原文，不递归改写旧摘要。省略 pinned_turn_ids 时继承上一摘要的固定集合；显式空数组表示解除固定。摘要保存覆盖消息的 ID/哈希、每个要点的来源引用、实际模型输入/响应及版本。模型调用在数据库事务外，返回后重新检查会话版本；会话若已改变则不绑定迟到结果。成功绑定会增加会话版本并使旧分析、草稿失效，原始消息不删除。

ContextBuilder 将摘要作为 data 级资料，固定消息和未覆盖消息保留原文。目标分析不再额外复制完整会话；初始规划和提交时快照的自动重规划均可使用同一来源链。摘要不证明文字真实性或执行成功，重要约束应显式固定。原始目标始终由 GoalContext 保留。

显式摘要动作和可配置的调用前自动预算处理均已实现，工作台现已提供摘要/策略控件。摘要使用同一 ModelCaller 预算按原文分块；超长单条消息按 Unicode 字符范围拆分并记录偏移。每块独立引用原文，不递归改写旧摘要；最多64次请求，超限在发出模型调用前拒绝。所有块通过校验且合并结果缩短历史后才生成可绑定摘要。各块响应、原文范围/哈希和汇总运行记录均保存。固定/近期原文本身或合并摘要仍可能超过后续规划预算，此时调用继续明确拒绝，不静默丢弃约束。验收证据：[session-summary-live.json](validation/session-summary-live.json)，覆盖真实摘要、固定约束、实际规划、worker 字节核验和原消息变更拒绝。

分块验收见 [chunked-session-summary-live.json](validation/chunked-session-summary-live.json)：原始历史超过单次实际配置预算，4块真实输入/响应验证通过，后续真实模型规划与文件 worker 哈希核验通过。逐块原文范围连续且无遗漏。并发会话修改用例在首块真实请求进行时添加消息，保留首块返回、停止后续调用且不绑定摘要。单条原文的字符拆分也经实际项目文档校验。

## 自动预算策略

`session.context-policy` 设置当前会话的 `auto_summary`（默认关闭）、`keep_recent`（2–32，默认6）和 `pinned_turn_ids`。参数还必须包含当前 session_id/expected_revision。设置策略本身不调用模型；增加会话版本并使旧分析、草稿失效。显式传入固定消息列表会替换策略中的列表；不传则沿用已有策略或摘要的固定消息。新固定的旧消息即使曾被摘要覆盖，也会重新以原文进入上下文。

`goal.analyze` 和 `plan.propose` 在模型调用前使用实际 ModelCaller/renderer/allocator 检查完整请求。预算足够时直接继续；不足且启用 auto_summary 时，先验证固定/近期原文及所有其他必需上下文能够容纳，再执行一次完整的原文分块摘要，并再次检查预算。无法缩减、没有新的可整理历史或合并结果仍超限时明确拒绝，不丢弃固定内容、不循环重试摘要。原始目标仍必选。

自动摘要作为候选上下文使用，在模型结果返回且会话版本仍匹配时才与结果一起保存。规划阶段若发生自动摘要，会话版本增加，`plan.propose` 同时返回新的 session 与 draft；调用方须用返回的新版本提交。工作台已接收这个返回版本。语义分析来源的操作员消息没有改变，因此自动规划整理保留原分析并同步 analysis_revision；手动摘要仍会清除旧分析。

`context_budget_events` 保存 fits/policy_disabled/reduced/rejected、触发原因、action_call_id、摘要运行 ID 和最终估算预算。这里的 reduced 表示候选上下文成功缩减，不代表计划已提交或任务已执行。模型请求仍保存在各自记录中。自动策略当前接入上述共享会话动作；Runtime 自动恢复沿用提交时摘要快照，尚未在执行状态增长后重新触发预算整理。

验收：[automatic-session-budget-live.json](validation/automatic-session-budget-live.json)。分别覆盖目标分析和规划入口超预算的真实模型到 worker 文件/hash 路径，并检查默认拒绝、固定内容超限不发模型请求、预算内不重复摘要、重新固定旧消息的原文恢复，以及旧会话版本提交拒绝。

## 工作台摘要与策略操作

工作台“历史摘要与预算”支持启用/关闭自动摘要、配置近期保留数量、勾选必须保留原文的消息。编辑状态明确显示尚未保存；保存策略不会调用模型，但会使旧分析/草稿失效。手动生成按钮使用已保存的策略，尚有未保存修改时不可用。近期消息与固定消息按集合合并保留，重叠消息不额外计数。

当前摘要显示要点、覆盖数量、可展开引用原文，以及覆盖哈希和模型记录。所有原始消息保持可读。`session.get` 现返回经过来源校验的 summary；若摘要或来源已改变，返回 summary_error 和原始 session，避免因摘要失效而无法恢复会话。摘要载入是只读动作，不自动调用模型。刷新与页面重载恢复保存的策略/摘要；旧会话版本的草稿不再重新显示。

实际浏览器验证见 [summary-browser-live.json](validation/summary-browser-live.json)：策略保存无模型调用、固定原文、真实摘要及来源查看、实际规划/worker/hash、策略使旧草稿失效、重载恢复和实际来源修改的失效提示。运行 `npm --prefix ui run build` 后执行 `node ui/scripts/test-summary-ui.mjs`，使用系统实际模型环境。


## 自动恢复的上下文预算

Runtime 自动重规划使用提交快照中的 context_policy；执行后修改会话策略不会改变已经提交的任务。策略允许时，超预算恢复只整理旧会话，保留最近及固定原文、执行账本、能力和绑定记忆。派生 planning_contexts 保存 parent_snapshot_id、parent_snapshot_hash 与 recovery_request_id，实际 Manifest 指向该派生快照，任务仍保留原始提交快照。后续恢复仍从原提交快照重新预检，次数受 max_replans 限制。

context_budget_events 的 replanning 记录区分 fits、reduced、rejected；reduced 仅说明上下文满足预算，不代表新计划已经采用。收到针对本任务的暂停、取消请求后停止追加模型调用，已返回的模型响应保留。最新任务事实本身超预算时明确拒绝，不用模型摘要替换执行证据。

实际验证见 [恢复预算与取消竞态](validation/recovery-budget-live.json)：普通恢复、缩减预算恢复均使用环境真实模型并由实际 worker 验证文件哈希；摘要调用期间的取消最终到 canceled，且没有后续规划请求。


## 失败事件自动化

共享动作已提供创建、暂停/启用、列出规则和读取诊断。独立 automation-worker 消费实际失败事件，按创建者/机器人范围运行有次数预算的真实模型解释；不派发恢复动作。使用、状态与当前限制见 [EVENT_AUTOMATIONS.md](EVENT_AUTOMATIONS.md)。


资产版本绑定增量：session.attach-assets 保存有版本的 AssetBinding，覆盖实际登记记录哈希与字节身份；上下文准备、草稿发布、提交、worker 接受和新技能派发都会复核。旧 ID-only 附件保留只读历史，需要显式重新附加并生成新草稿。详见 [资产上下文绑定](ASSET_CONTEXT_BINDINGS.md) 和 [真实验收](validation/asset-binding-live.json)。


## 显式任务完成契约

新增 session.completion-contract（session_id、expected_revision、contract），在规划前设置/清除操作者要求的最终验证技能输出检查；设置后需重新分析。手工 task.submit 可通过 completion_contract 参数使用同一 v1 格式。契约与模型计划分开保存，任务接受后冻结，修订不能改变它。框架在真实最终结果上逐项保存预期值与实际值；技能报告成功但任务条件不满足时，任务仍失败。详见 [完成契约](COMPLETION_CONTRACTS.md) 与 [真实验证](validation/completion-contract-live.json)。

## 动作发现与调用契约版本

每个发现条目保留 description/input_schema/output_schema，并增加 contract_version、contract_hash、permission、effect_kind、requires_idempotency_key、calls_model、may_schedule_model、dispatches_skill 和 writes_audit_record。契约哈希覆盖动作名及全部上述描述字段（哈希自身除外），调用审计保存版本、哈希与 effect_kind，便于关联客户端所见契约和实际调用。该哈希表示元数据身份，不是代码版本、签名或权限凭据；调用时不要求客户端提交哈希，也不会因客户端缓存旧元数据而绕过现有参数/版本校验。

| effect_kind | 含义 |
|---|---|
| read | 读取业务数据；POST 调用仍写 action_calls 审计 |
| session_write | 修改会话、选择、附件或显式要求 |
| model_call | 可能同步请求真实模型并持久化结果；幂等重放不必再次调用 |
| task_command | 将任务控制意图入队，回执不代表实际执行或停止 |
| automation_write | 配置自动诊断规则，可能使未来事件产生模型作业 |
| diagnosis_queue | 将显式重试诊断入队，由后续处理请求模型 |

calls_model 表示该动作具备同步模型调用行为，不承诺每次调用都发出请求；may_schedule_model 表示可影响后续诊断作业，不表示已调用模型。当前动作均不直接派发技能（dispatches_skill=false）；任务 worker 才推进实际执行。除 read 外均要求幂等键。GET 发现本身不新增 action_calls；返回 schema 为独立副本，调用者修改其对象不会更改注册 schema。

新增 tests/test_action_discovery.py 在真实 loopback HTTP 服务验证认证、权限筛选、元数据与调用审计关联、缺失幂等键拒绝、跨机器人读取拒绝，以及由发现的 schema 校验真实提交/查询结果。命令经独立 worker 执行真实文件归档并核对 SHA256；没有模型替身或仿真。本次未改动模型提示或传输，也没有新增模型调用。专项及动作/完成契约回归共 17 项通过。

## 跨动作幂等键归属

同一主体在同一账本内，写动作的 Idempotency-Key 只能归属一个动作请求。会话、任务命令和自动化创建/启停/重试在写事务内检查全部已持久化键格式；跨动作或相同动作不同参数返回 IDEMPOTENCY_CONFLICT（HTTP 409）。并发调用由同一 SQLite 写事务边界决定唯一接受者；任务入队仍不等于执行完成。查询不占用幂等键。

保留原有自动化规则、请求和重试 ID，不迁移或覆盖历史记录；同动作同参数按原策略重放原回执，重放后仍检查当前主体权限及机器人范围。升级前若一个键已被多个动作实际占用，拒绝该歧义键的重放，不选择某个旧副作用作为唯一结果；操作者应检查历史记录并为新的明确意图使用新键。不同主体、不同账本不是同一幂等命名空间。

修复前已用实际 SQLite 复现“同键创建自动化后还能创建会话”。修复后 25 项回归通过，包括双向跨动作冲突、自动化修改冲突、原回执重放、三类真实 HTTP 并发仅一项接受及独立 worker 文件哈希验收。真实自动诊断专项 1 项通过：实际文件失败、持久作业、并发独立 worker、一次真实环境模型调用、实际错误和证据引用核对、完整输入重建。升级前实际模型账本副本也验证了旧回执原样重放和跨动作拒绝，业务记录不变，无新增模型调用。证据见 [action-idempotency-live.json](validation/action-idempotency-live.json)。
