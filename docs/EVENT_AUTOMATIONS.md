# 失败事件自动诊断

第一版事件自动化订阅实际 `execution_result` 中 status=failed 的记录，将诊断持久入队，再由独立 worker 调用环境配置中的实际模型。模型返回解释、原始错误和记录引用；解释不修改任务，也不代表执行、恢复或物理停止证据。这里订阅的是一次执行失败，后续 fallback 或重规划成功不会抹去该历史事件。

## 使用

通过共享动作创建规则，HTTP 与 CLI 使用同一校验逻辑。创建者需要 `automations.manage`、`tasks.read`、`planning.use`，且具有目标 robot 范围。规则只处理创建之后的新事件，必须显式给出累计诊断次数预算。

将参数保存为本地 JSON 文件，例如：

```json
{"robot_id":"r1","max_runs":10,"question":"请解释实际失败原因，区分已记录事实与待核查假设，并引用事件和执行记录。"}
```

```bash
.venv/bin/robot-agent --root .runtime action automation.create rule.json --idempotency-key failure-diagnostics-r1
.venv/bin/robot-agent --root .runtime automation-worker
```

自动化 worker 与执行 worker 独立启动；诊断模型耗时不会占用机器人执行锁。`--once` 扫描并处理最多 10 个诊断；`--scan-only` 只保存队列后退出，不调用模型。命令返回的 items 是本批处理结果，所有历史结果通过 `automation.runs` 查询。

当前 CLI worker 使用本机操作者身份，只处理同一 subject 创建的规则；它不会冒用其他 HTTP 用户身份。服务端可信代码可向 `run_once` 传入实际主体，每次扫描和执行都会重新检查当前权限。没有根据规则中保存的字符串重建高权限主体。

| 共享动作 | 参数 | 结果 |
|---|---|---|
| automation.create | robot_id、question、max_runs（1–100） | automation |
| automation.set-enabled | automation_id、expected_revision、enabled | automation |
| automation.list | 空对象 | 当前主体和范围内的规则 items |
| automation.runs | automation_id | 该规则的诊断 items |
| automation.retry | run_id、expected_status（failed/unresolved）及新的幂等键 | 保留旧记录并创建新的 run，消耗原规则剩余预算 |

## 持久化及状态

规则保存在 automations，诊断保存在 automation_runs。事件序号和规则 ID 组成稳定的去重键；游标推进、排队和预算计数在同一 SQLite 事务内提交。每次扫描每条规则最多读取 500 个事件，持续 worker 会继续扫描后续事件。max_runs 是累计入队预算，失败或取消的诊断也消耗预算，暂停/恢复不重置预算。

诊断状态为 queued、running、completed、failed、canceled 或 unresolved。同一主体的多个 worker 使用进程锁串行消费，避免同时发送同一模型请求。不同主体拥有独立规则和调用预算，不把不同主体的请求合并。

暂停/重新启用都会递增规则 revision 并将游标移动至当前事件位置；暂停期间的事件不补跑，旧版本尚未派发的队列项取消。已发送的模型请求无法通过暂停撤回，若返回则保留实际结果；暂停防止后续派发。

如果 worker 在 running 状态退出，下一次运行将其标记 unresolved，不自动重发。结果可能已经到达模型服务，unresolved 记录会关联已存在的 model_response_id，必须检查后再决定是否调用 automation.retry。该动作不会改变旧记录的不确定状态，也不能超出原规则的累计预算。模型终态响应与诊断终态在同一 SQLite 事务中保存，避免响应已验证而诊断仍为 running 的提交间隙。该设计不承诺网络调用 exactly-once。实际 SIGKILL 验收覆盖已有请求记录和真实已建立连接时中断、重启不重发，以及后续实际诊断；无法证明被中断请求已由供应商接收或已生成响应，也没有覆盖每一个指令级中断窗口。

## 证据与边界

入队保存实际事件、事件哈希和匹配的执行记录。发送前检查原事件未变、执行快照哈希正确；ContextManifest 保存来源和分配预算。model_responses 保存实际 prompt、原始响应、模型名、供应商 response ID 和结构化解析结果。解析要求 observed_error 与记录错误完全一致，引用包含对应事件及 execution ID。

自动诊断现在使用严格编码/读取后的 ContextBundle v1 生成请求；`context_bundle_id`、`context_bundle_hash` 和 `preparation` 关联完整输入及其准备参数。完整包、Manifest 和 requesting 模型记录在同一事务中提交，然后才进行网络调用。Provider 未参与事件快照构造，diagnostics 保持空列表。

ContextRequest 的 `automation_diagnosis` phase 标识历史事件诊断，goal 原文是规则的实际诊断问题，robot_id 来自已检查范围的规则。事件片段保存真实 task ID、execution ID 和来源哈希；request.task_id 不设置，避免默认 revision/generation 被误读为当前任务版本。新增 phase 不改变 Bundle v1 字段格式；不认识该 phase 的旧读取器会拒绝，不应作为跨版本兼容成功。

已中断调用的上下文仅证明准备及持久化了什么，不证明供应商已经接收请求或生成响应。显式 retry 新建调用身份和上下文包，保留原始事件片段与旧记录的不确定状态；旧 Bundle 不重写。历史诊断没有 Bundle 时不回填。

真实验证使用实际创建后删除的文件，Runtime 产生真实失败事件，独立进程消费诊断。旧事件、其他机器人事件、重复扫描、累计预算、权限、暂停和实际事件损坏均有检查。该版本不含定时任务、自然语言条件、自动执行恢复计划或多 Agent 分派；这些仍属后续目标。工作台规则与诊断 UI 已接通，操作见下节。机器人现场验证也未完成。

完整验证记录：[event-automation-live.json](validation/event-automation-live.json)。自动化专项 2 项通过，实际文件/账本回归 39 项与 9 个子测试通过。


进程中断增量：实际 SIGKILL 和 SIGINT 后原请求均保持 unresolved，重启不重发；后续真实失败事件和 automation.retry 的实际模型响应已验证。重新诊断保留 retry_of、创建者及原不确定记录，受同一预算和幂等键约束。响应与诊断终态现以同一事务提交。证据：[automation-interruption-live.json](validation/automation-interruption-live.json)。供应商是否接收被中断请求仍未知，不能把缺失响应解释为未调用或已成功。

## 工作台操作

连接应用服务后，具备 automation.create 动作权限的主体可在「任务协作」底部使用「失败事件自动诊断」。规则不依赖当前 Session，机器人范围单独填写；服务端继续校验实际权限。创建时明确累计次数和诊断问题，保存本身不调用模型。

规则列表显示启用状态与累计额度。诊断列表保留事件/任务 ID、实际模型解释、原始错误、来源引用和完整记录。failed/unresolved 状态可显式重新诊断；暂停、额度耗尽或读取出错时禁止派发该操作。原结果未知的记录说明再次诊断会发出新请求，旧记录不会被改为成功。

页面仅轮询共享读取动作；独立 automation-worker 必须由相应主体运行。页面连接成功不代表诊断 worker 在线。切换操作凭据会卸载这部分记录，重新连接后按新主体读取。手机下两列内容按创建、查看顺序堆叠。

工作台真实浏览器验收：[automation-browser-live.json](validation/automation-browser-live.json)，包含最终桌面/手机截图及实际服务断开后的记录保留检查。


自动诊断上下文包增量：explain_event 已保存完整 ContextBundle v1、哈希与准备参数，并在真实网络调用前同 Manifest、requesting 记录原子提交。上下文只表示绑定的历史事件，不附会当前任务 revision/generation，不补造 Provider 诊断。实际事件诊断、SIGKILL/SIGINT 中断和显式重试共 4 项专项通过，另有 23 项实际文件/账本/HTTP 回归通过；5 条实际响应与原错误一致，2 条中断请求保持 unresolved，7 份输入均准确重建且来源事件哈希与账本一致。证据：[automation-context-live.json](validation/automation-context-live.json)。供应商是否接收中断请求仍未知；摘要完整追溯、世界状态、真机和 Momo 同步仍未完成。
