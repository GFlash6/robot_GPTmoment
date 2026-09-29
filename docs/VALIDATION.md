# 第一版验证记录

## 2026-09-12 上下文基础框架增量验证

- 新增可审计 `GoalContext`，同时保留原始输入、解释后意图、实体/关系、约束、完成条件、歧义、缺失、假设、感知获取请求和人工澄清请求；`from_analysis` 不允许分析结果替换原始输入。
- 新增图结构 `TaskStateContext`，分别表达 `decomposes_to`、`depends_on` 和 `verifies`，成功节点只引用账本里的实际输出和证据。
- `ContextBuilder` 已接入初始规划和自动重规划，并以 revision/generation 拒绝陈旧任务快照；能力上下文来自初始 Skill Registry 或任务冻结 Catalog。
- `RoleAwareRenderer` 已接入模型调用；只有 framework policy 可以成为 system 消息，普通目标、能力、任务和外部数据均作为 user 数据，Session 只接受原始 user/assistant 角色。
- Context 预算改为按实际渲染消息估算，并使用稳定排序及 `over_budget` 丢弃原因；估算器明确记录为 `utf8_bytes_v1`，不声称是真实 tokenizer 计数。
- Planner 在模型网络请求前保存 `ContextManifest`；实际不可达端点测试证明传输失败时仍保留 request、phase、纳入项、预算和 renderer 版本。
- 修复任务持久化模型配置遗漏 `max_input_tokens` 与 `max_output_tokens`，避免重规划静默回退默认预算。
- 新增独立 `goal_analysis` 与 `goal_clarification` 模型方法：两者使用不同且固定的 System Prompt。初步分析只输出语义候选；只有缺失信息需要用户提供时才调用问讯，能够由机器人感知获取的信息保持 `needs_grounding`，不会错误询问用户。该入口不自动提交 Task。
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q`：41 passed、1 skipped、9 subtests passed。新增两项使用本地 HTTP 边界服务，只证明提示词隔离、解析、分流和证据保存；没有新增实际大模型、ROS2 或机器人现场验收。

本文件保留 2026-09-05 第一版验证结果。后续 UI 阶段全量测试已增至 30 tests / 9 subtests，另有 4 项浏览器检查和构建通过，见 [UI_VALIDATION.md](UI_VALIDATION.md)。当前状态见 [PROJECT.md](../.momo/lifecycle/robot-agent-framework/PROJECT.md)。

## 2026-09-07 阶段 1 增量验证

- 计划修订现在实际保存对应版本的 plan、steps、catalog、revision、generation 和保存时间；回归测试先确认旧实现缺失 revision，再在实现后通过，并验证后续注册的新契约没有污染旧历史。
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests -q`：31 passed、9 subtests passed，18.60 秒；[JUnit 原始结果](validation/pytest-roadmap.xml)。
- TypeScript 检查与 Vite 生产构建通过；4 项 Chromium 浏览器回归通过。现有浏览器账本没有历史修订样本，因此这 4 项检查只证明原 UI 流程未回退；历史契约显示由类型构建和 Python 持久化测试分别覆盖，尚未单独增加浏览器交互用例。
- 本地 `.venv/bin/ruff` 不存在，本轮没有执行 ruff，也不将其记录为通过。

该增量没有模型或机器人响应，不能关闭实际模型、机器人技能或控制端 fencing 验收。

## 2026-09-07 实际模型规划联调

- 模型配置使用显式 Chat Completions URL、`qwen3.8-max`，API 密钥只从 `API_KEY` 环境变量读取；配置文件和证据记录均不保存密钥。
- 首次指定的 `qwen3.8plus` 经服务返回 404 `model_not_found`；查询服务模型目录后由用户明确改为 `qwen3.8-max`。
- `qwen3.8-max` 首次返回 HTTP 200，但把 `verification` 生成为对象，框架按既有契约拒绝。新增本地 HTTP 边界回归先复现失败，再明确提示顶层 `verification` 必须是步骤 ID 字符串，测试转为通过。
- 修正后实际请求返回 HTTP 200，服务声明实际模型为 `qwen3.8-max`；两步计划 `ingest_readme -> verify_readme_asset` 通过 DAG、引用和最终 verifier 校验。原始响应保存在被 Git 忽略的 `.runtime/model-validation/ledger.sqlite`，脱敏摘要见 [模型规划记录](validation/model-planning-qwen3.8-max.json)。
- 大模型响应另以真实问答验收：`RUN_LIVE_MODEL_TESTS=1 ... pytest tests/test_live_model.py -q -rA` 实际调用 `qwen3.8-max`，问题为 37 箱 × 每箱 29 件 − 已用 428 件；独立手算期望值与模型结构化回答均为 645，1 项测试在 7.15 秒通过。该测试默认跳过，避免普通离线回归意外消耗 API 配额。
- 本地模拟 HTTP 只验证 Planner 请求与契约边界，不作为大模型问答正确性的证据。
- 本次只生成并校验计划，没有提交或执行计划；因此不证明技能执行、最终任务完成、长程规划质量或自动重规划成功路径。

日期：2026-09-05。结论：软件框架第一版可运行；真实模型和机器人运动端到端验收仍未完成。Momo 项目保持 in_progress，不标记整个目标完成。

## 实际通过

- Python 3.10.12 环境实际安装 DBOS 2.31.0、py_trees 2.5.0、MCAP 1.4.0、jsonschema 4.26.0、httpx 0.28.1；依赖见 requirements.lock。
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests -q`：24 passed，9 subtests passed，16.54 秒；[JUnit 原始结果](validation/pytest.xml)。
- `ruff check --select F`：通过。生产模块与测试经过格式整理；CLI help 实际可运行。
- 真实文件摄取、哈希损坏拒绝、证据引用、资产筛选、缺失空间字段拒绝、MCAP 写入/重读通过。
- DAG 依赖、真实缺失文件失败后的 fallback、原后置条件验证、暂停/恢复、跨连接资源原子竞争通过。
- 实际 loopback HTTP 服务执行文件操作；同一 ID 幂等查询、改变请求拒绝、取消后真实部分文件和停止证据通过。
- 真实工作进程被 SIGKILL 后重启 DBOS：原 HTTP 执行 ID 保持一个，服务请求记录保持一个，文件内容最终一致，资源正常释放。
- 实际连接不可达端点：状态保持 unknown，未重发且资源未释放；缺模型配置或模型连接失败不生成默认计划，有界重规划记录实际失败并消费预算。
- 晚到自动修订不能清除用户取消或覆盖更新的操作者 generation；资源别名冲突拒绝；所有终态拒绝空白或非字符串来源证据。
- ROS2 Humble Python 接入和实际 topic 发现通过；发现 /parameter_events 和 /rosout，没有机器人传感器 topic。
- 使用实际文件哈希检查产生的 ROS2 日志验证 rosbag2 SQLite 录制，重新打开后计数 /rosout 为 25；[记录结果](validation/ros-recording.json)。这些是实际软件诊断消息，不是伪传感器数据。该次临时原始 bag 在检查后清理，保留计数和文件哈希。
- 请求不存在的相机 topic 会实际拒绝；本机没有 rosbag2_storage_mcap，不能声明 ROS2 MCAP 插件已安装。

## 审查与纠正

独立代码审查指出并已修正：可运行任务发布后被旧字典覆盖；模型重规划期间取消被清除；资源名称折算冲突少计容量；失败/取消的来源证据检查较弱。随后修正并复查迟到模型结果覆盖新 generation 的并发问题。相关回归已包含在上述测试中。

历史基线为 6 项测试中的 1 failure、5 import errors；这已由实际生产模块解决，不再代表当前状态。

## 没有证明的能力

已有一次实际模型成功响应及两步计划解析/契约接受证据，但模型计划执行、长程计划质量和自动重规划成功路径仍没有外部联调通过证据。没有真实机器人技能服务，因此底盘/机械臂后置条件、物理停止、不可重入补偿、硬件急停、控制端旧执行者隔离没有验收。

没有真实 RGB、深度、点云和多种地图流的高频负载检查；地图重定位失效、自动语义分类/合并、向量记忆及 DimOS memory 集成也未完成。框架具备资产类别与元数据契约、原始记录和证据查询，不将这些未验证算法能力写成已完成。

DBOS 当前采用本地 SQLite，一台机器一个 worker；Postgres 生产部署、多机器人、热升级、跨主机租约和性能上限没有验证。HTTP 控制协议是已有实现接口，机器人具体适配器仍需真实返回证据接入。


## 2026-09-22 应用动作与真实模型闭环

本轮不使用 mock 或仿真。实际输入、模型原始响应和执行结果保存在隔离的 `.runtime/application-validation/` 账本；可版本化摘要及指纹见 `docs/validation/application-layer-2026-09-22.json`。

- 当前环境模型 `qwen3.7-plus`：真实目标分析 → 模型两步计划 → 幂等命令 → DBOS worker → 实际文件归档和 SHA256 核验，通过。
- 真实多轮澄清：模糊目标产生实际问讯；补充真实文件及已核验资产后继续分析，通过。
- 实际文件不存在导致技能失败；真实模型解释引用已存在的任务/步骤，指出错误并保留未知项，任务仍为失败，通过。
- Chromium 实际浏览器：任务 DAG 选中节点 → 会话上下文 → 真实模型解释，通过；1440 与 390 像素宽度检查，无页面脚本错误和横向溢出。
- Chromium 完整路径：创建目标 → 分析 → 生成草稿 → 提交 → 实际 worker 文件执行 → 页面读取 succeeded，独立核对执行结果中的哈希和停止证据，通过。
- 26 tests / 9 subtests passed：`test_application_actions.py`、`test_runtime.py`、`test_contracts_memory.py`、`test_http_execution.py`；包含真实 HTTP、并发幂等、实际进程事务中退出、worker 重启、取消竞争、版本冲突、权限范围及文件损坏。
- UI TypeScript/Vite 构建通过；机械检查未报告新增协作组件问题。

首轮真实分析曾返回 needs_grounding，使“必须 ready 才可规划”的旧假设失败。实现已改为保留待取证需求并要求规划安排真实技能，不把 unknown 改为已知。失败记录保留在 `7da8b966-0d52-42c3-9e90-543860d615b4`，随后重新调用实际模型完成验收。

没有运行包含 ScriptedCaller 或固定模型响应服务的既有模型测试，因此这里不是整个历史测试目录全部通过的声明。真实 ROS2 发现只有 `/parameter_events`、`/rosout`；没有机器人动作或真实传感器现场验收。

## 会话与记忆的实际重规划验收

显式使用环境模型运行 `RUN_LIVE_MODEL_TESTS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests/test_replanning_context_live.py -q -s`：1 passed，73.08s。实际源文件被移除后技能失败；重规划真实输入含提交时人工约束、绑定记忆与失败账本，不含后续未提交消息；真实响应改用备用路径，worker 最终字节哈希一致。没有 mock 或仿真。第一次运行因测试误把任务状态期待为 failed（实际已进入 replanning）失败，原报告保留，修改断言后重新运行完整链路。

相关非 AI 回归 `tests/test_context_memory.py tests/test_application_actions.py tests/test_contracts_memory.py tests/test_runtime.py`：29 passed、9 subtests，8.61s。范围包含实际 SQLite 快照修改拒绝，不代表整仓测试或真机验收。证据见 [replanning-context-live.json](validation/replanning-context-live.json)。

## 历史摘要真实模型验收

`RUN_LIVE_MODEL_TESTS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests/test_session_summary_live.py -q -s`：1 passed，81.57s。使用系统环境模型配置与实际项目协议原文；核对摘要中的实际文件路径、覆盖引用、固定原文约束和近期消息，后续真实计划与 worker 归档/哈希核验通过。实际修改覆盖消息后 ContextBuilder 拒绝旧摘要。没有 mock 或仿真，模型原始输入/响应保存在账本。见 [session-summary-live.json](validation/session-summary-live.json)。

相关 `test_context_memory / test_application_actions / test_contracts_memory / test_runtime` 回归：29 passed、9 subtests，8.59s。不代表完整仓库或真机验收。

## 超预算历史分块及并发修改

`RUN_LIVE_MODEL_TESTS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests/test_session_summary_live.py -q -s`：2 passed，277.58s。普通历史1块，大历史4块；后者先确认全量输入超过实际环境模型配置预算，再逐块核对真实发送的原文、连续字符偏移、来源引用和预算，随后实际模型规划、worker执行及哈希核验通过。

`tests/test_summary_concurrency_live.py` 显式真实模型运行：1 passed，50.34s。另一个 SQLite 连接在实际请求进行时通过 Action 添加操作员消息；首块真实响应被保留，后续调用停止，会话的新版本没有绑定不完整摘要。相关非AI回归29 passed、9 subtests，8.61s。无mock或仿真。完整证据：[chunked-session-summary-live.json](validation/chunked-session-summary-live.json)。

## 共享会话动作的自动预算验收

显式启用实际环境模型，`tests/test_session_summary_live.py -k automatic`：1 passed、2 deselected，162.66s；`tests/test_plan_budget_live.py`：1 passed，87.05s。前者覆盖默认预算拒绝和不可缩减固定内容拒绝（没有模型请求）、开启策略后真实分块摘要/分析/规划/worker 文件核验、预算内不重复整理、重新固定旧消息原文。后者用实际文档预检得到“分析可容纳、规划超预算”的输入，验证真实摘要与规划、新会话版本、旧版本拒绝及实际 worker 最终结果。

相关回归29 passed、9 subtests，8.68s；TypeScript/Vite构建通过。工作台仅同步采用 plan.propose 返回的会话版本，本轮没有新增浏览器验收声明。证据：[automatic-session-budget-live.json](validation/automatic-session-budget-live.json)。未使用mock、仿真或superpowers；尚不代表机器人执行验收。
