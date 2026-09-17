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

普通分页默认 50，最大 200；q 为字面子串匹配，SQL 使用绑定参数。资产时间过滤使用纳秒整数，闭区间。所有超过 JavaScript 安全整数范围的整数以十进制字符串返回，避免纳秒时间戳失真。任务详情包含该任务全部执行和历史；极长任务的详情分页仍是后续工作。事件页面最多保留最近读取的 1000 条，账本不裁剪。

API 删除已知配置敏感字段，如 model_config、token_env、authorization、api_key、endpoint、allowed_roots；资产列表不返回本地 path。任意模型正文仍可能含模型自己返回的敏感文本，因此服务只绑定 loopback；没有远程身份认证。UI 使用文本节点渲染输入和响应，不执行其中的 HTML。资产哈希只是登记值，查询不会重新读取或验证资产文件。

默认同源：观察服务 `--static ui/dist` 提供构建产物。开发模式由 Vite 代理 `/api`。需要独立静态源时，在构建前设置 `VITE_API_BASE` 为实际 API origin，并对观察服务传入 `--origin` 允许该前端 origin；静态宿主的 CSP 必须允许连接该 API。观察服务自带的静态宿主 CSP 限制 connect-src 为 self，适合同源部署。跨机器访问需另行实现认证代理与访问边界。

前端轮询间隔两秒，请求六秒超时，卸载时取消请求。切换任务时清除旧任务视图；同一查询断连保留上次快照并显示错误和最近观测时间。新修订记录保存并展示对应版本的技能契约；兼容旧账本时，缺失的历史契约明确标记不可用，不用当前契约替代。
