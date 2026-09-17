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
