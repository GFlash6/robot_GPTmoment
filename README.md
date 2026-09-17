# 机器人 Agent 框架

第一版已实现可运行的任务与证据管理链路。DBOS 管理持久工作流；协调层管理任务 DAG、多资源控制权、真实结果、取消与恢复；MCAP/rosbag2 和资产目录管理观测记录与可追溯记忆。Momo 已正式注册，唯一项目图为 `.momo/momo-workspace.json`。

当前验证包括真实文件操作、实际 HTTP 服务、DBOS 工作进程被杀后的恢复、ROS2 诊断消息录制，以及 `qwen3.8-max` 返回且通过契约校验的实际两步计划。该计划未执行，没有机器人运动完成的验收声明。详细记录见 [VALIDATION.md](docs/VALIDATION.md)。

当前工程情况统一维护在 [工程状态](docs/PROJECT_STATUS.md)，按模块和细项区分已完成、进行中与未完成；后续构建顺序见 [分阶段路线](docs/BUILD_ROADMAP.md)，[问题台账](docs/OPEN_QUESTIONS.md)保存待决问题和所需证据。第一版可运行，完整框架仍需完善。

## 安装与检查

可视化模型测试：启动独立网关后打开 `http://127.0.0.1:8767`，进入「模型记录 → 真实问答测试」，即可手动向 `qwen3.8-max` 提问。API Key 从服务端环境读取，支持实际回答、耗时、预期答案匹配和历史记录。启动命令见 [模型测试 UI](docs/MODEL_TEST_UI.md)。

在本目录执行：

```bash
uv venv --python /usr/bin/python3 --system-site-packages .venv
uv pip install --python .venv/bin/python -r requirements.lock -e .
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests -q
.venv/bin/robot-agent --help
```

本机 Python 为 3.10，与 ROS2 Humble 匹配。系统 ROS pytest 插件和安装的 pytest 有接口冲突，所以普通框架测试关闭无关插件自动加载。`requirements.lock` 固定实际安装的 Python 依赖；ROS2 由系统安装提供。运行 ROS 命令前执行 `source /opt/ros/humble/setup.bash`。

## 实际文件任务

以下命令操作本工程已有 README 文件，计划由操作者明确提供；这不是 AI 规划演示。

```bash
.venv/bin/robot-agent init --allow-read "$PWD"
.venv/bin/python - <<'PY'
import json
from pathlib import Path
plan = {
    "steps": [
        {"id": "save", "skill": "file.ingest", "args": {
            "path": str(Path("README.md").resolve()),
            "metadata": {"kind": "document", "source": "operator-selected-file", "encoding": "utf8"}}},
        {"id": "check", "skill": "asset.verify", "deps": ["save"],
         "args": {"asset_id": {"$ref": "save.asset_id"}}}
    ],
    "verification": "check"
}
Path(".runtime/file-plan.json").write_text(json.dumps(plan))
PY
.venv/bin/robot-agent submit .runtime/file-plan.json --robot r1
.venv/bin/robot-agent run
```

`submit` 输出真实 task ID；`status`、`events`、`pause`、`cancel`、`resume` 和 `preempt` 接受该 ID。`run --until` 后附 task ID 可等待一个任务到安全终态。停止 worker 不等于停止远端机器人；重启继续查询原执行。`pause/cancel` 返回的是请求记录，只有任务到 paused/canceled 才完成对应流程。

## 模型、技能与恢复

- `plan`：使用真实模型配置生成并校验计划。`agent`：用真实响应提交目标任务，可设置 `--max-replans` 有界自动重规划；之后由 `run` 执行。
- 模型配置文件字段：`endpoint` 为实际完整 Chat Completions 兼容 URL，`model` 为服务实际模型名，`token_env` 为可选鉴权环境变量名，`timeout` 为请求超时。工程没有预填服务或默认回答。
- `register` 注册一个 JSON 技能契约；`capacity` 配置 `robot_id/resource` 容量。参数/输出 schema、后置条件、资源、取消能力、重入能力和 verifier 标记来自注册配置，不能由模型修改。
- `serve-skills` 启动 loopback HTTP 数据技能服务；内置 `file.ingest`、`asset.verify`、分块 `file.copy` 都操作实际文件。机器人端实现 [技能协议](docs/SKILL_PROTOCOL.md) 后以 HTTP 适配接入。
- `replan` 接受人工新计划，或真实模型配置与目标；只允许旧动作已经停止的任务修订，历史计划和结果保留。自动修订不覆盖同时到达的用户取消。
- 副作用可重入性不确定时禁止自动恢复。内置 file.copy 不覆写既有目标，取消后保留部分文件，禁止直接重入。

## 观测与记忆

`ingest` 保存真实文件和元数据；支持 RGB、深度、点云、点云地图、占据地图、体素地图、标定、坐标变换、文档和录制文件。空间资产必须有 robot_id、frame_id、clock_domain 和 timestamp_ns；RGB/深度引用实际 calibration 资产；地图有版本。父资产必须存在并通过哈希检查。

`assets` 按类别、机器人、frame、时间和版本筛选；`remember/search` 管理有实际资产证据的语义条目。它是结构化及文本记忆目录，没有冒充向量检索或自动对象合并。`record-file` 写实际字节到 MCAP；`inspect-recording` 读取消息信息。

`ros-topics` 发现实际 ROS2 topics；`record-ros` 调用本机 rosbag2 录制指定 topics，重新打开记录统计实际消息并生成哈希清单。缺失 topic、缺失插件、零消息或未正常结束均报错。本机只安装 rosbag2 SQLite 存储插件，因此默认 sqlite3；选择 mcap 需要先安装对应插件，不能把独立 Python MCAP 库当作已安装 ROS 插件。

## 流程可视化 UI

独立 React / TypeScript 前端通过只读 `/api/v1` 查询运行账本。支持总览、任务 DAG、节点输入与实际结果、fallback 尝试、停止证据、计划历史、事件时间线、资源占用、资产记忆及模型原始响应。页面每两秒刷新；断连保留上次数据并标记过期。API 已连接不代表 worker 或机器人在线。

在本目录构建和启动，`--root` 指向实际 worker 使用的运行目录：

```bash
npm ci --prefix ui
npm run build --prefix ui
.venv/bin/robot-agent-observer --root .runtime --static ui/dist --port 8765
```

打开 <http://127.0.0.1:8765>。账本不存在会显示读取错误，观察服务不会创建账本或派发任务。UI 与 worker 可分别关闭。此版只读，不提供任务控制按钮。

开发时分别运行观察服务和 `npm run dev --prefix ui`，访问 <http://127.0.0.1:5174>，Vite 将 `/api` 代理到 8765。前端也可独立部署到静态服务器，配置方法见 [UI_API.md](docs/UI_API.md)。

浏览器验证使用独立账本内**实际执行的文件操作**，没有模型或机器人返回数据。首次准备及验证：

```bash
.venv/bin/python ui/tests-data.py .runtime/ui-validation
cd ui
npx playwright install chromium
npm run test:browser
```

已有验证账本可直接重复浏览器检查；准备脚本拒绝覆盖既有验证记录。查看这组实际记录时，用 `--root .runtime/ui-validation` 启动观察服务。测试结果、截图及限制见 [UI_VALIDATION.md](docs/UI_VALIDATION.md)。

## 项目材料

- [架构与状态语义](docs/ARCHITECTURE.md)
- [完整目标架构、接口、状态机与案例](docs/DETAILED_ARCHITECTURE.md)
- [当前 Agent 任务拆分流程图](docs/TASK_DECOMPOSITION_FLOW.md)
- [模块待完善问题](docs/OPEN_QUESTIONS.md)
- [开源研究与复用矩阵](docs/research/REPORT.md)
- [Momo 工作日志](.momo/lifecycle/robot-agent-framework/WORKLOG.md)

本版仍需真实模型长程规划与执行闭环、机器人技能、控制端隔离旧执行者、硬件急停及实际多模态流验收。DimOS memory、向量库、场景图和分布式资源调度尚未集成；不把调研候选写成已交付功能。
