# 模型调用与上下文流转

2026-09-07：用户要求在 Momo 图中单独细化此模块。此图描述当前实现，不新增运行能力。沿用 `model-adapter` 对象作为容器，保留它与项目主图的语义关系。

当前从自然语言目标生成 DAG、校验、提交以及失败后重规划的完整流程见 [Agent 任务拆分流程](TASK_DECOMPOSITION_FLOW.md)。

## 调用主链

UI 测试网关或 Planner 调用 ModelCaller；ModelCaller 选择 qa/planning 方法，获取基础消息，把外部 ContextFragment 交给 ContextAllocator，再组装 ModelRequest，经 HTTP Transport 调用显式配置的模型，返回 ModelCallResult。调用器不持有会话历史。

ModelConfig 保存 endpoint、model、token_env、timeout、max_input_tokens、max_output_tokens。当前模型为 qwen3.8-max，凭证在请求发送时从环境读取；图中不保存密钥、实际请求正文或本地绝对路径。默认超时 60 秒，本地预算 32768，输出预留 2048；当前分配器实际使用 30720 的估算输入预算，估算采用 UTF-8 字节而非模型 tokenizer。temperature 和 response_format 属于方法输出的请求参数：规划要求 JSON，UI qa 默认普通文本且不显式设置 temperature。

消息顺序：方法 system → 可选上下文 system → 当前 user。上下文提示标记内容为数据，但目前仍使用 system role；这不是隔离任意输入指令的安全保证。

## 历史的三条路径

1. UI：问题 → qa → 实际回答 → model-tests.sqlite。历史仅供查看和重新选择；预期答案不发送，历史不自动进入下一轮问答。
2. 规划：目标＋技能目录 → planning → 实际响应 → JSON/DAG/最终 verifier 校验 → model_responses 证据记录。规划记录不是自动加载的对话历史。
3. 重规划：任务账本中的 previous_plan、step_results、revision → Runtime.recover_plan → 一个必需的 planner_runtime_context 片段 → 规划请求。默认初次 submit_goal 不传额外上下文；CLI plan --context 可显式传入 JSON。

## 图的读法

进入 Momo「模型调用与上下文流转」容器，在专用画布查看：上部为入口和调用装配，中部为预算与 HTTP/返回，下部为历史与重规划，最下方为未完成项。节点详情保留实际数据结构、来源文件和边界。

实线 `supports` 表示上游模块/数据支持下游模块，具体传递字段见节点详情；它不是运行事件顺序。`depends_on` 表示待完成工作依赖已有部件，不表示该能力已接通。包含关系用于分组，不绘制为数据流。

## 当前未完成项

- 会话历史管理：没有 session_id 与跨轮 user/assistant 消息组装；UI 历史持久化不等于连续对话。
- 历史摘要与记忆检索注入：没有自动摘要、滑动窗口或资产/记忆检索接入。可选片段超预算会丢弃；当前重规划使用单个必需片段，超预算报错。
- 重规划参数继承：Runtime 保存 model_config 时只保留 endpoint/model/token_env/timeout，自定义输入输出预算不会随任务保存，自动重规划回到默认预算。

这些是当前缺口的记录，不代表本次已授权实现或已完成修复。

## 代码证据

- `robot_agent/model_call.py`：组合调用方法、上下文分配和传输，返回 ModelCallResult。
- `robot_agent/model_methods.py`：qa/planning 的提示词和请求参数。
- `robot_agent/model_context.py`：ContextFragment、分配规则和消息渲染。
- `robot_agent/model_transport.py`：ModelConfig、ModelRequest、HTTP 请求和环境凭证读取。
- `robot_agent/planner.py`：规划输入、运行上下文封装、计划校验和证据保存。
- `robot_agent/runtime.py`：初次提交、任务配置保存和失败重规划。
- `robot_agent_observer/model_test.py`：真实 QA、预期答案比较及独立历史。
- `ui/src/ModelTest.tsx`：界面发送本次问题与预期答案，不携带历史消息。
