# 只读观察 API v1

`robot_agent_observer.server` 与核心包平级，不导入 Runtime、DBOS、ROS 或技能适配器。它使用 SQLite `mode=ro`、`query_only` 和请求内读事务，读取指定目录的 `ledger.sqlite`。该只读服务没有创建账本、更新记录或下发控制的路径。前端只访问 HTTP DTO。

真实问答使用独立启动的 `robot_agent_observer.model_test` 网关：`GET /model-test/config`、`GET /model-test/history`、`POST /model-test/run`。它复用模型调用层，将问答写入独立 `model-tests.sqlite`，不修改运行账本。POST 需要本地 Host/Origin、服务签发的请求令牌、JSON 输入及唯一请求 ID；同一 ID 重发返回既有记录。说明见 [模型测试 UI](MODEL_TEST_UI.md)。下文 GET-only 契约仅指原观察 API。

成功响应为 `{api_version: "1", observed_at: "ISO UTC", data: ...}`。`observed_at` 是查询完成时间，不是机器人心跳。错误为 `{api_version: "1", error: {code, message}}`；写方法返回 405 / READ_ONLY。缺失账本返回 503 / LEDGER_MISSING，忙返回 503 / LEDGER_BUSY，不支持的表结构返回 422 / SCHEMA_UNSUPPORTED，无法解析记录返回 422 / LEDGER_INVALID，未找到记录返回 404 / NOT_FOUND。

| GET 路径 | 参数 | data |
|---|---|---|
| `/api/v1/overview` | 无 | task_counts、collections、resource_count、lease_count、latest_event_seq/at、recent_events；worker_status 与 robot_status 为 unobserved |
| `/api/v1/tasks` | robot_id、status、q、limit、offset | items 任务摘要、total、limit、offset |
| `/api/v1/tasks/{id}` | 无 | task 当前快照、executions 实际执行、control 或 null、history 保存的计划与步骤快照 |
| `/api/v1/tasks/{id}/events` | after_seq 默认 0、limit 默认 100，最大 500 | items、next_seq、has_more；按 seq 递增 |
| `/api/v1/resources` | 无 | items：name、capacity、used、owners；owner 保留执行 ID，并附实际可解析的 task_id/step/status |
| `/api/v1/assets` | kind、robot_id、frame_id、version、start_ns、end_ns、q、limit、offset | items 资产元数据、total、limit、offset |
| `/api/v1/memories` | kind、q、limit、offset | items 记忆与来源资产 ID、total、limit、offset |
| `/api/v1/models` | status、q、limit、offset | items 响应摘要（不含 raw/plan）、total、limit、offset |
| `/api/v1/models/{id}` | 无 | 单条已保存模型响应，含实际 raw、错误或计划（如存在） |
| `/api/v1/models/{id}/context` | 无 | 关联 Bundle、Manifest、allocation、preparation 和限定范围的 integrity 检查；不调用模型 |
| `/api/v1/models/{id}/context-diff` | against：必填的基准模型记录 ID | 同一读事务内比较 against → id；双方 integrity、结构问题、请求/片段/Manifest/预算/诊断差异 |

模型上下文查询在同一个只读事务中读取模型记录及引用。`integrity.status` 为 matched（包和清单均存在且本次检查一致）、partial（仅有其中一种证据且没有已发现的不一致）、unavailable（历史记录没有可用关联）或 inconsistent（引用缺失、包哈希不匹配、未知包版本、身份或 request/phase 关联不一致）。不存在的模型记录仍返回 404；已有模型但证据有问题时返回 200 和明确问题列表，便于查看原始记录。

`integrity.scope=persisted_links_and_bundle_hash_only`：只检查存储关联和原始包的规范 JSON 哈希，不验证 Manifest 全文真实性、不重建模型请求、不验证世界事实或重新授予执行权限。哈希按服务端未脱敏记录计算；返回对象经过既有敏感字段过滤和大整数转换，客户端不能直接对展示 JSON 重新计算并假定相同。写入权限控制不能被哈希替代，两个关联记录一起被修改不在该检查的证明范围内。详情见 [模型上下文证据](MODEL_CONTEXT_EVIDENCE.md)。

普通分页默认 50，最大 200；q 为字面子串匹配，SQL 使用绑定参数。资产时间过滤使用纳秒整数，闭区间。所有超过 JavaScript 安全整数范围的整数以十进制字符串返回，避免纳秒时间戳失真。任务详情包含该任务全部执行和历史；极长任务的详情分页仍是后续工作。事件页面最多保留最近读取的 1000 条，账本不裁剪。

API 删除已知配置敏感字段，如 model_config、token_env、authorization、api_key、endpoint、allowed_roots；资产列表不返回本地 path。任意模型正文仍可能含模型自己返回的敏感文本，因此服务只绑定 loopback；没有远程身份认证。UI 使用文本节点渲染输入和响应，不执行其中的 HTML。资产哈希只是登记值，查询不会重新读取或验证资产文件。

默认同源：观察服务 `--static ui/dist` 提供构建产物。开发模式由 Vite 代理 `/api`。需要独立静态源时，在构建前设置 `VITE_API_BASE` 为实际 API origin，并对观察服务传入 `--origin` 允许该前端 origin；静态宿主的 CSP 必须允许连接该 API。观察服务自带的静态宿主 CSP 限制 connect-src 为 self，适合同源部署。跨机器访问需另行实现认证代理与访问边界。

前端轮询间隔两秒，请求六秒超时，卸载时取消请求。切换任务时清除旧任务视图；同一查询断连保留上次快照并显示错误和最近观测时间。新修订记录保存并展示对应版本的技能契约；兼容旧账本时，缺失的历史契约明确标记不可用，不用当前契约替代。

## 两次模型调用的上下文差异

`GET /api/v1/models/{after_id}/context-diff?against={before_id}` 明确指定方向，不自动查找或推断父调用。缺少/空白 against 返回 400，任一模型记录不存在返回 404；写操作返回 405。双方及其 Bundle、Manifest 在同一 SQLite 只读事务中读取。

`status=compared` 表示两侧已通过既有存储关联/包哈希检查和比较所需的结构检查。`changes.request` 逐字段报告值及 before_present/after_present，区分缺失与 null；`fragments` 按 ID 对齐，报告 added、removed、changed、unchanged_ids 及原始顺序。内容使用 `content_sha256`，来源、权限层级、必需性、优先级、元数据、证据 ID 和纳入/丢弃状态分别比较。Manifest、allocation 和 Provider diagnostics 也保留差异；嵌套对象作为所属字段的整体值比较，不宣称语义等价。

两侧证据缺失、已有 integrity 非 matched、片段 ID 重复、Manifest 纳入/丢弃集合重叠或不能恰好覆盖片段时，返回 `status=unavailable, changes=null` 及双方问题；这与没有变化不同。结构检查只服务于无歧义比较，不替代完整业务 schema 或 Manifest 真伪验证。

`scope=redacted_persisted_context_only`：先执行既有敏感字段过滤和大整数显示转换，再计算差异及片段内容哈希。因此隐藏字段的变化不作为可见内容变化；片段哈希与原始 Bundle 的 integrity 哈希不可混用。不会重新生成提示或调用模型。`scope_differences` 标明 robot_id、session_id、task_id、goal 的值差异；`lineage=explicit_pair_not_verified` 表示仅比较明确选择的记录，不证明两次调用属于同一任务或祖先链，也不授予执行权限。

真实账本验证见 [context-diff-live.json](validation/context-diff-live.json)：原规划到恢复规划新增任务状态和摘要，能力内容不变但来源转为冻结目录，输入预算由 32768 变为 18719。模型记录页面已接入双记录比较：固定基准后选择当前记录，或粘贴任意已知基准 ID；显示方向、预算、来源与内容哈希变化。浏览器证据及审查状态见 [context-diff-browser-live.json](validation/context-diff-browser-live.json)。
