# Jev 参考示例

三个独立场景共用一个 HTTP 调用函数，使用项目已有的 `httpx`，不需要安装 TypeSafe SDK。
所有输入均为明确标注的演示数据；模型响应来自实际 API。脚本不派发技能、不写运行账本。

| 场景 | 原语 | 对应框架位置 |
| --- | --- | --- |
| `goal` | Noul + Choice | 使用 `GoalContext`，区分目标歧义、用户澄清和感知补充 |
| `context` | Score | 使用 `ContextFragment`，给可选上下文排序，保留必需片段及矛盾证据 |
| `skill` | Choice + Noul | 为单个子目标选择技能候选，并展示低置信度时不作推荐 |

## 运行

在仓库根目录、已经安装本项目的 `.venv` 中执行。密钥从当前进程的 `JEV_API_KEY` 读取；不要把密钥写进脚本或命令参数。

```bash
# 不调用 API，查看三个请求的状态和问题
.venv/bin/python examples/jev/reference_examples.py all --dry-run

# 分别调用，每个场景一次请求
.venv/bin/python examples/jev/reference_examples.py goal
.venv/bin/python examples/jev/reference_examples.py context
.venv/bin/python examples/jev/reference_examples.py skill

# 一次运行三个场景，共三次请求，消耗 API 配额
.venv/bin/python examples/jev/reference_examples.py all
```

如果变量只在 `~/.bashrc` 中配置，非交互进程可能看不到它。可从正常终端运行，或：

```bash
bash -ic '.venv/bin/python examples/jev/reference_examples.py all'
```

脚本默认固定 `jev-1.13.0`；可用 `--model jev-latest` 切换，实际服务版本在输出的 `response.model` 中。
输出包括原始结构化答案、概率、置信度、usage、端到端耗时及代码生成的解释。
`--dry-run` 不会输出伪造的模型答案。

## 如何改成自己的场景

修改三个 `*_example()` 函数中的 `state` 和 `questions`：

- `state` 放待判断的数据；`instructions` 写完整问题，并指出字段路径。问题 ID 仅用于匹配返回值。
- `Choice.criteria` 放有限候选，保留 `none` 或 `unknown`，避免强迫模型从不适用项中选择。
- `Score.criteria` 放有明确含义的有序等级；`score` 不是物理量或成功概率。
- 同一个 state 上的独立问题放进同一请求。相互依赖的问题需要分两次请求。
- 中文示例保留中文输入、采用英文问题；这不保证中文准确率，需要用本项目真实数据评估。

`interpret()` 演示代码如何消费答案，不代表模型生成的推理解释。技能选择中的 0.8 阈值未经校准，不能用于机器人执行授权。
上下文例子只输出排序；正式接入时可以在 `ContextAllocator` 前使用该排序，但保留 `required`、`authority` 和证据语义。
技能目录为内置能力的描述性子集，并非实时注册结果；正式使用应从 Runtime 的注册目录构造候选。
目标例子不自动更新 `GoalContext.disposition`，也没有把模型判断当作实际传感器证据。

HTTP 请求只发送到官方固定域名，超时 30 秒，不跟随重定向，不自动重试。
401 表示鉴权问题；429/529 请稍后重试。示例会检查答案类型、问题 ID、候选及概率范围；生产接入还需完整审计、预算、任务版本检查和经实测校准的策略。

## 官方资料

- [HTTP API](https://docs.typesafe.ai/api)
- [模型版本与限制](https://docs.typesafe.ai/models)
- [置信度](https://docs.typesafe.ai/confidence)
- [已知局限](https://docs.typesafe.ai/model-jaggedness/jev-1.13)

## 本次真实调用记录（2026-09-22）

通过交互式 shell 继承 `JEV_API_KEY`，实际调用 `jev-1.13.0`，三个响应均通过脚本结构检查。
以下是本次 API 返回的摘要，不是固定预期值；输入仍为演示数据，不代表机器人实测。

| 场景 | 返回摘要 | 耗时 | 输入 / 输出 token |
| --- | --- | --- | --- |
| goal | 歧义 Noul=0.94；目标选择 ask_user（confidence=0.97）；用户位置 sense（confidence=1.0） | 2857 ms | 789 / 114 |
| context | 两条相互矛盾的位置记录均得 2.0 分，无关咖啡机记录得 0.0 分；满分为 2 | 2992 ms | 1039 / 53 |
| skill | file.copy（confidence=0.99）；适用性 Noul=0.92 | 1232 ms | 648 / 67 |

总计 2476 个输入 token、234 个输出 token。单次调用数据不是性能基准，也不能证明阈值已校准。
另已完成 dry-run、Python 编译检查，以及离线结构检查：缺失答案拒绝、必需上下文保留、低置信度不推荐技能。
