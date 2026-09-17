# 框架第一版 Implementation Plan

> For agentic workers: 使用 superpowers:executing-plans 在当前已确认目录逐项实施，不启动子代理。

**Goal:** 实现可运行的单机器人任务、资源、恢复打断与证据记忆框架。
**Architecture:** DBOS 持久执行加机器人契约协调层，MCAP 原始记录，py_trees 结果条件链；具体设计见 ARCHITECTURE.md。
**Tech Stack:** Python 3.10、DBOS、py_trees、MCAP、jsonschema、httpx、SQLite。
**Spec:** docs/ARCHITECTURE.md。

## Global Constraints

不使用模拟 AI/机器人结果；接口缺失报真实错误。单机器人多任务多资源，保留 robot_id。只写本项目目录。初始失败测试属于待实现功能，用户已授权继续实现。工作区保持当前目录，避免移动已注册 Momo 根。

## 任务与检查

- [x] 契约和资产：contracts.py 定义 ContractError、validate_plan、check_result；store.py 定义 Store；memory.py 定义 Memory；运行现有 tests/test_contracts_memory.py 观察缺模块失败，完成真实文件入库、证据引用、资源事务后复跑。
- [x] 记录格式：recording.py 用 MCAP Writer/Reader；新增 test_recording.py 用实际文档文件字节写入并重新读取，逐字段比较时间、编码和内容。
- [x] 技能和任务：skills.py 接入真实本地文件操作和 HTTP 协议；runtime.py 维护派发前身份、查询、资源、fallback 与暂停。test_runtime.py 用真实文件的失败路径/成功路径验证恢复，拒绝用 mock 来证明机器人行为。
- [x] 持久工作流：durable.py 以 DBOS.step 调用 Runtime.tick，以 DBOS.sleep 持久等待；验证实际工作流数据库和重启后任务查询。已持久化执行 ID 不再重派。
- [x] 规划与 CLI：planner.py 保存实际模型响应并做严格校验；cli.py 提供 init、register、submit、run、status、pause/cancel/resume、replan、memory 和 record 入口。缺模型配置检查必须失败，不返回固定计划。
- [x] 审查与记录：运行 pytest、CLI 实际数据流程、依赖锁定；在 VALIDATION.md 记录通过项目与真实模型/机器人未验证项。更新 Momo 对象、证据和生命周期，保留未解决关系提案。

执行检查：`.venv/bin/python -m pytest tests -q`；安装：`uv pip install --python .venv/bin/python -e .`。测试完成后固定实际安装版本，不把上游 HEAD 研究能力当发布版能力。

本轮实现及软件检查完成，外部 AI/机器人成功路径未验收。后续不继续用本清单冒充整项目完成，按 OPEN_QUESTIONS.md 的现场接口和模块缺口推进。
