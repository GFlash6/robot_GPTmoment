# 真实 G1 接入契约与当前证据

本文件依据相邻工作区真实设备桥源码和本次实际 ROS 图发现整理；不是设备接入成功报告。未启动状态桥、运动桥、仿真、dry-run 或任何运动指令；未调用模型。源码路径与 SHA256、实际发现结果见 [world-source-discovery.json](validation/world-source-discovery.json)。

## 当前可观察事实

本机当前 ROS 域的三秒发现窗口只列出 /parameter_events 和 /rosout，两者发布者均为本次 robot_agent_source_audit 检查节点；未发现其他节点或 Action。该结论限本机当前发现域及时间窗口，不证明机器人断电，也不排除其他 ROS 域、DDS 网卡或远端网络中存在设备。没有订阅传感器或收到传感器消息。

## 已找到的源码接口

| 来源 | 实际源码约定 | 接入时必须保留的语义 |
|---|---|---|
| ../holoagent_bridge/g1_state_bridge.py | SDK DDS rt/sportmodestate → nav_msgs/Odometry /g1/sport_odom | position、velocity、rpy、yaw_speed 来自收到的 SDK 消息；当前没有实际流证据 |
| 同上 | frame_id=g1_odom，child_frame_id=base_link | 不自动认定 g1_odom 等于 map；需要实际 TF 与地图版本 |
| 同上 | header.stamp 使用桥节点接收处理时的 ROS clock | 是桥接时间，不是已证实的设备采样时间；跨设备时延与时钟误差未知 |
| 同上 | 只赋 position、orientation、linear velocity、angular.z | 默认 covariance 与其他未赋值字段不能被解释为零误差或已测量值 |
| 同上 | rt/lowstate → std_msgs/String /g1/low_state | JSON 包含 tick、mode_pr、mode_machine、imu_rpy；并非带设备时间、robot_id、版本的完整观测契约 |
| 同上 | sport_timeout 后告警并记录 sport_state_stale | 告警不是任务执行前可消费的结构化有效性状态；消费者仍需记录接收时间与失效依据 |
| ../holoagent_bridge/g1_cmd_vel_adapter.py | cmd_vel → SDK SetVelocity；软件停止锁存、限速、超时处理 | SDK 返回码属于命令请求证据，不等于实际到达或静止 |
| 同上 | 关闭时尝试 StopMove，并记录结果 | 不能单独满足框架 quiescent=true 的物理停止证明 |

状态桥启动脚本要求明确 G1_NETWORK_INTERFACE。运动桥有显式运动开关和授权输入，默认 dry-run；本次没有启动任一模式。状态桥没有给每条观测附加可靠设备身份，来源到 robot_id 的映射需要部署配置和实际核对。

## 首次只读接入所需输入

1. 目标设备是否为上述 G1，以及正式 robot_id。
2. 实际连接网卡或服务地址、ROS_DOMAIN_ID、DDS 配置，以及允许订阅的主题。
3. 生产者与物理设备的绑定依据；桥接主机、进程实例及来源配置版本。
4. 位姿/速度的单位、坐标约定、TF 链与地图版本。SDK velocity 表达在哪个坐标系不能只凭消息字段名推断。
5. 设备采样时间是否可用；ROS clock 类型、是否 use_sim_time、时钟同步误差及接收时间记录方式。
6. 每类状态的时效要求，以及设备断流、时间跳变、地图改变时允许的处理方式。

上述信息尚未收到；不将本机默认 ROS 域、默认网卡或默认坐标系写成已经确认的设备配置。

## 实现顺序与验收

第一阶段只读采集：将实际原始消息及来源信息归档，分别记录 source timestamp（若可用）、bridge timestamp、接收 wall/monotonic 时间和采集进程身份；消息缺少采样时间时显式表示未知。拒绝把 covariance 默认零当可信精度，未赋值速度分量不作为独立测量值。

第二阶段世界状态：增加 WorldObservation 和 WorldStateProvider，明确 valid/stale/unavailable/invalid、证据引用与有效性策略；把“最近收到”与“采样仍新鲜”分开。测试必须使用真实流、实际断流/恢复及真实时间/坐标配置，不以构造传感器消息代替现场验收。仅状态桥日志或话题存在不足以标记 valid。

第三阶段只在具备执行契约后接入一个允许的运动技能。当前 cmd_vel 适配器没有本框架的 execution_id 查询、幂等执行、authority/fencing 或最终任务结果协议，不能直接注册成可恢复的 HTTP 技能。需先完成执行身份、旧控制者隔离、断连查询、取消与独立停止观测映射。禁止用 SDK code=0 直接生成 quiescent=true；停止阈值和持续时间由实际设备与任务需求确定。

第四阶段才进行导航/操作任务族闭环：每个阶段使用实际物体/地图/位姿，完成契约绑定可测结果。当前文件任务的成功证据不迁移为运动成功证据。

## 当前交付边界

本次完成接口审阅、来源哈希和实际 ROS 图证据归档，并明确了世界状态模型必须表达的未知项；没有修改相邻工程、创建默认机器人观测或注册运动技能。设备接入仍待实际连接与语义信息，应用层其余软件改进可独立继续。
