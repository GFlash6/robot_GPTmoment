# 技能接入协议

## 注册契约

注册文件包含 adapter（http）、endpoint、input_schema、output_schema、checks、resources、cancelable、replay_safe；verifier 标记此技能能进行目标验证。可选 token_env、timeout、execution_timeout。资源可用未加前缀的名称、当前机器人完整名称或 shared/ 前缀；拒绝折算后重名和跨机器人引用。模型只能使用已经注册的能力。

checks 支持非空 nonempty、类型一致相等 eq、数值 gte/lte；path 为输出对象点分路径。fallback 的实际结果既要满足替代技能契约，也必须满足原技能后置条件。重试仅作用于明确失败且已停止、注册为 replay_safe 的技能；未知不是可重试失败。

## 请求

PUT /executions/{execution_id}：JSON 包含 execution_id、skill、robot_id、args。同一 ID 和相同请求必须关联原执行；不同请求复用同 ID 必须拒绝，不能产生第二个动作。

GET /executions/{execution_id}：查询原执行实际状态。未找到执行不意味着允许重发。

POST /executions/{execution_id}/cancel：请求中断，可返回 canceling；最终通过后续查询或返回的终态确认。适配器必须确认其控制器真实停止。终态不能只根据 RPC 接受构造。

## 响应

execution_id 必须匹配；status 为 accepted/running/canceling/unknown/succeeded/failed/canceled。所有终态都需要 quiescent=true 和非空 evidence 列表，每条证据 source 必须是非空白字符串。成功还必须有实际非空 output 对象，通过输出 JSON Schema 和 checks。失败可有 error 字段记录实际错误。

source 应指向可追溯的控制器日志、观测、文件、资产或测量记录；不要仅使用“已完成”文字。通用框架检查来源结构和后置条件，不能独立证明某个任意远端服务没有谎报物理状态。接入机器人时必须实现可信的停止/目标观测适配器，并单独验收。

## 恢复和控制权

框架先持久化 execution_id 与资源分配，再发送请求。若网络失败或进程在提交边界退出，恢复只能查询同一 ID。超时不释放资源；取消请求也不释放资源。只有通过终态停止证据检查后才释放。

远端服务必须持久保存执行身份和结果。机器人控制端尚需验证旧执行者隔离机制；本版 worker 文件锁只限制本机框架工作进程，不等于硬件 fencing，也不是硬件急停。禁止把本地工作进程退出当停止证据。

本项目 loopback 数据服务执行真实文件操作，供数据管理和协议联调用；不包含假机器人技能。

## 显式启用控制域 fencing

HTTP 技能可注册 `fencing_domain`，名称为 1–64 个 ASCII 字母、数字、下划线或连字符。Runtime 要求 `resources` 中有同名资源且数量为 1，对应 robot/resource 容量也必须为 1。注册在实际执行端的本地技能必须配置相同域；不支持该协议的端点不能静默接受请求。

派发事务同时保存资源占用、execution ID 和 `authority={domain, token}`。token 来自本账本按 robot/domain 递增的持久计数器；查询、取消和 worker 恢复沿用该执行原令牌，不重新发号。新执行使用更大的令牌，已有账本计数器不能随意清空。

PUT 请求增加 `authority` 字段；PUT、GET、POST 都携带 `X-Execution-Authority`，值为同一对象的 JSON。响应必须回传匹配的 authority，客户端校验后才消费结果。执行端持久保存每个 robot/domain 最新 token 和执行 ID：同 ID 同 token 可以继续查询，只有新执行且更大 token 可以更换控制权；旧 token、相同 token 的不同执行以及缺失/不匹配的头均拒绝。

本地数据服务使用共享账本的进程锁，将权威检查与实际同步文件操作串行化。服务重启保留最新令牌；旧复制执行在接管后无法通过查询继续写入。HTTP 拒绝仍只表明请求被拒绝，Runtime 将原执行保持 unknown 并保留资源，不据此生成 quiescent 或硬件停止结果。恢复旧任务需要明确的执行端停止/状态核对，尚无自动强制释放入口。

### 当前控制者显式核对旧执行

`POST /executions/{old_execution_id}/reconcile` 携带当前控制者的 `X-Execution-Authority`。服务端按旧执行绑定的 robot/domain 查询当前权威，要求头中的 token 正是当前持久 token 且大于旧 token；旧令牌和任意自行增大的未生效令牌均拒绝。该接口不接受调用方提供的成功或停止结果。

服务端在同一控制域执行锁下调用旧本地技能的实际 cancel，检查执行 ID、终态、quiescent 和来源证据，再持久保存原请求哈希、原执行 authority、真实结果及执行核对的控制者身份。重复请求返回原证据。若技能没有可核对的持久状态、不可取消或不能给出终态证据，接口拒绝，不制造停止结果。

完成核对后，旧执行的 GET 和待处理 cancel 可携带原令牌读取这份持久结果；这是只读历史查询，不再调用会推进复制的技能 poll。旧 PUT 仍被拒绝。Runtime 校验原执行身份、原令牌和真实终态后才释放资源；已接受用户取消时任务进入 canceled，未要求取消时仍按实际终态处理。核对不会把部分文件改写成完整副本，也不会使失败任务成功。

此接口目前由显式 HTTP 调用触发，没有自动接管、自动跳号或 UI 按钮。机器人适配器必须实现自己的真实停止核对，不能复用文件复制的 quiescent 结论。

当前验证范围是单个持久 Runtime 账本发号、共享持久服务账本执行。它不提供跨独立账本/多主控制者的租约仲裁；外部控制者提交更高令牌后，本地低令牌被拒绝，不自动跳号抢回控制权。令牌不是身份凭据，鉴权仍由部署承担。异步机器人驱动必须在真实副作用发生处持续执行控制权检查并提供停止证据；本地文件服务的锁不能替代这项设备接入工作。

实际验证记录见 [fencing-live.json](validation/fencing-live.json)，包含真实模型到远端文件执行及非模型的控制权故障测试范围。


### Runtime 的任务完成契约

操作者可在任务层另外声明最终 verifier 的输出检查。技能返回成功且通过原有输出/停止/证据检查后，Runtime 才核对这些要求。结果上的 reported_status 与 completion_evaluation 是框架审计字段，不是适配器新增的必填返回字段；若任务要求失败，框架记录 failed，同时保留技能实际输出与停止证据。适配器自身的成功标准没有因此被放宽。详见 [完成契约](COMPLETION_CONTRACTS.md)。
