# 操作者完成契约

技能注册表中的 checks 定义技能的一般成功条件。任务还可以有操作者明确指定的完成契约，用于核对最终验证技能的实际输出。例如 asset.verify 可以成功证明归档内部哈希一致，但归档字节仍可能不是操作者要求的版本；完成契约会独立检查预期 SHA256 和大小。

## 输入与权限

`session.completion-contract` 使用现有 planning.use 权限、会话主体/机器人范围和 expected_revision，输入 contract 为 v1 对象或 null。设置/清除会递增 revision 并清除旧分析，旧草稿不能继续提交。任务尚未接受前可以显式修改；已接受任务的契约不随当前会话变化，修改任务要求应创建新任务。手工 `task.submit` 也可通过独立 completion_contract 参数提交同一格式，遵循原有 tasks.submit 权限。

```json
{
  "schema_version": 1,
  "verifier_skill": "asset.verify",
  "checks": [
    {"id": "integrity", "path": "verified", "op": "eq", "value": true},
    {"id": "nonempty-document", "path": "size", "op": "gte", "value": 1}
  ]
}
```

这是契约格式示例，不是执行记录；任务实际需要的哈希、大小、单位和阈值必须来自操作者要求或已确认的证据。自然语言 GoalContext.completion_criteria 继续保留为解释文本，不自动升级为执行约束。模型输出中的 completion_contract 字段会被拒绝，不能覆盖独立参数。

## v1 规则

- 固定顶层字段 schema_version、verifier_skill、checks；1–64 项检查，唯一非空 id，整体不超过 64 KiB 有限 JSON。
- path 是点分隔的对象字段路径，不解释代码、数组下标、通配符或引用。封闭输出 schema 明确排除的路径在接收时拒绝；其他缺失路径在实际检查时失败。
- eq 比较规范 JSON，保留类型与数组顺序差异；nonempty 使用实际值的非空判断且不得携带 value；gte/lte 要求有限数值，布尔值不能充当数值。
- verifier_skill 必须是注册的 verifier。计划最后步骤及其 fallback 都必须使用该技能；技能输入、输出 schema、停止和证据检查仍先执行。

## 从上下文到执行

会话契约作为必须保留的 operator 权限 completion-contract 片段进入目标分析和规划；已接受任务的上下文从冻结任务契约读取。规划快照保存原契约，任务单独保存 completion_contract_hash，命令处理与新派发核对快照/任务契约，防止来源不一致。比较使用规范 JSON 哈希，不把 true 与 1 误认为相同。

选定既有任务生成修订草稿时，会话必须使用相同契约；只读查看/解释既有任务不要求操作者先采用该契约。人工修订和自动恢复继续使用已接受契约，Runtime.revise 不提供修改完成契约的路径。模型可以提出新计划，不能改变原验收要求。

最终技能返回成功并通过既有协议检查后，Runtime 逐项核对输出，在结果保存 completion_evaluation：契约哈希、execution_id、验证技能、每项预期值、实际值/缺失错误以及通过/失败状态。reported_status 保留技能报告的成功；若任一任务检查失败，执行账本和任务按失败处理，实际输出及停止证据仍保留，资源按原有已停止终态规则释放。

上下文额外以 data 权限 completion-evaluation 片段暴露实际检查记录，供后续诊断或恢复使用；它与 operator 权限的要求分开，保存任务版本、执行 ID 和来源证据。

## 边界

契约只验证明确列出的输出条件，不自动证明自然语言目标的全部语义已被覆盖，也不能把不可信技能自述变成独立世界观测。现有无契约任务保持原有技能验证行为，历史结果不回填为新契约验收。物理任务仍需要真实适配器、观测来源、时效/坐标规则、停止证据和适当的任务完成指标。

本增量提供共享动作与 Runtime 接口，尚无专门的完成契约编辑界面。


## 实际验证

[completion-contract-live.json](validation/completion-contract-live.json) 记录真实环境模型的两条完整路径：目标分析 → 结构化计划 → 共享动作提交 → 独立 worker → 实际归档字节 → 完成契约检查。通过运行的 4 条响应均保存原文、模型响应 ID、请求哈希、Bundle 和 Manifest；所保存输入准确重建。

未改变的文件通过全部检查并完成任务。另一条路径在模型规划后实际修改文件：file.ingest 和 asset.verify 确实处理了修改后的字节，verified 为 true；任务却因操作者要求的哈希、大小不符而失败，reported_status 仍为 succeeded，并保留 completion_evaluation、实际输出与停止证据。

首轮测试错误地要求该预期失败任务返回 CLI 退出码 0，实际 CLI 按约定返回 1；修正断言后重新执行真实模型与 worker 路径通过，没有修改生产检查来取得通过。两轮合计 8 条真实响应，首轮证据保留。最终专项 1 项通过，实际文件/SQLite/动作回归 40 项通过，覆盖显式契约、schema/操作符/范围拒绝、来源哈希变更拒绝、人工修订保留要求及恢复上下文携带实际检查明细。该首轮增量未运行真实模型自动重规划试验；后续专项见下文。

## 完成契约失败后的真实模型恢复

[completion-recovery-live.json](validation/completion-recovery-live.json) 补充真实模型自动重规划的端到端证据。先实际读取同内容主文件与授权备用文件，再由环境配置模型分析目标并生成主文件归档计划；接受任务后实际修改主文件。file.ingest 与 asset.verify 成功处理变化后的字节，但原 SHA256 和大小验收失败，任务进入 replanning。

恢复请求包含必须保留的 operator 完成契约和 data 验收差异，后者精确对应真实执行的逐项检查。接受后清除当前会话契约不改变任务要求；真实模型改用已授权备用文件，保留同一最终验证技能，通过独立 worker 执行后归档字节与原文完全一致。主文件保持实际修改后的内容，备用文件未改变，资源租约已释放。

新增测试 tests/test_completion_recovery_live.py 使用 environment_config()，保存并校验三条实际响应及其供应商 ID；三份实际输入、response_format 和预算分配均准确重建。专项 1 项通过（70.85 秒），相关实际文件/账本回归 40 项通过（7.76 秒）。这补齐了一个受明确约束的文件恢复场景，不代表通用恢复成功率、物理世界观测或机器人执行验收。本增量未改变生产执行逻辑。
