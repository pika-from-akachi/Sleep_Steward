# RDK X5 实机接入设计

> 状态：待用户书面审阅
> 目标：在保留 `SimDriver` 回退能力的前提下，让网站读取真实 DHT11，并控制 RDK X5 上的多色 LED；StepFun 继续通过现有白名单指令控制同一套硬件接口。

## 1. 第一阶段范围

- 接入 DHT11 的真实温度、湿度读数。
- 控制白、黄、蓝、红四颗 LED 的开关和 0-100 亮度。
- 保留现有 `setLight` 协议：`warm` 映射为黄灯 + 红灯，`cool` 映射为蓝灯 + 白灯。
- 没有光照传感器时，`lightLux` 明确标记为估算值，由当前灯态推导，仅用于界面展示和 demo 闭环。
- StepFun 使用现有 `STEPFUN_API_KEY` 服务端环境变量和动作白名单，不新增可执行动作。
- `setClimate` 暂时只记录目标温度，不宣称控制真实空调。

第一阶段不接入 MAX30102 自动巡检。心率测量需要用户持续按压约 25 秒，后续应做成独立的“开始测量”流程，不能阻塞每 5 秒运行的环境闭环。

## 2. 接入方式选型

### 方案 A：板端常驻 HTTP 服务（采用）

RDK X5 运行一个轻量 Python 硬件服务，负责 GPIO、DHT11 和灯效状态；Next.js 的 `RdkX5Driver` 通过局域网 HTTP 调用。SSH 只用于首次部署和诊断。

优点：采样开销低、状态连续、错误可观测、不会因每次 SSH 握手拖慢页面。代价是板端多一个受 systemd 管理的小服务。

### 方案 B：每次通过 SSH 执行硬件命令

实现文件少，但每 4-5 秒都要建 SSH 连接，容易受密钥、握手超时和网络抖动影响，不适合作为网站运行时协议。

### 方案 C：Next.js 直接部署到 RDK X5

Node 可直接调用本机硬件脚本，但会把网站部署、数据库和 GPIO 生命周期绑在一台 4 GB 板子上。本阶段演示环境仍以 Mac 运行网站，因此暂不采用。

## 3. 组件边界

### 板端 `hardware-agent`

- `GET /health`：返回服务、DHT11 和 LED 状态。
- `GET /environment`：返回 `tempC`、`humidityPct`、`lightLux`、`lightSource` 和采样时间。
- `POST /light`：接收 `{ on, brightness, colorTemp }`，校验后更新灯效。
- DHT11 失败时保留最后一次有效读数，并返回 `stale: true`；没有历史值时返回明确错误。
- LED 使用软件 PWM。HTTP 请求只更新目标状态，常驻灯效循环负责平滑过渡，请求线程不执行长时间呼吸循环。

### 网站端 `RdkX5Driver`

- 实现现有 `HardwareDriver`，业务层不感知真实硬件或模拟器。
- `readEnvironment()` 调 `/environment`，设置 3 秒超时。
- `setLight()` 调 `/light`，亮度统一限制在 0-100。
- `health()` 调 `/health`，返回 `driver: "rdk-x5"`。
- `setClimate()` 与 `playAudio()` 保持无硬件副作用，只维护兼容状态。
- `HARDWARE_DRIVER=rdk-x5` 时启用；未配置时继续使用 `SimDriver`。

### API 与界面

- `/api/env` 同时返回环境值、驱动健康状态及光照数据来源。
- 真实驱动离线时 API 返回可展示的降级状态，不让页面白屏。
- 演示造场接口仅对 `SimDriver` 开放。
- 现有点击指令、硬编码语音和 StepFun 自然语言都继续调用 `HardwareDriver`，不写硬件分支。

## 4. 已确认 Pin 映射

| 模块 | 物理 Pin | 用途 |
|---|---:|---|
| DHT11 | 1 | 3.3V |
| DHT11 | 9 | GND |
| DHT11 | 11 | DATA |
| 白色 LED | 13 | GPIO 输出 |
| 黄色 LED | 15 | GPIO 输出 |
| 蓝色 LED | 18 | GPIO 输出 |
| 红色 LED | 22 | GPIO 输出 |
| LED 公共地 | 20 | GND |

MAX30102 保持现有接线：Pin 17 为 3.3V、Pin 14 为 GND、Pin 3 为 SDA、Pin 5 为 SCL，第一阶段不改变也不轮询。

## 5. 灯光语义

- `on: false`：四灯关闭。
- `warm`：黄色为主，红色为辅；白色和蓝色关闭。适合睡前和夜灯。
- `cool`：蓝色为主，白色为辅；黄色和红色关闭。仅用于演示或清醒场景。
- `brightness`：控制总占空比。低于 20 时使用平滑 PWM，避免直接全亮。

睡眠默认不做持续明显闪烁。暖睡眠灯使用稳定低亮或非常缓慢的呼吸变化；红灯不采用快速“心跳双闪”，避免形成注意刺激。

## 6. 配置与安全

网站端环境变量：

```dotenv
HARDWARE_DRIVER=rdk-x5
RDK_X5_AGENT_URL=http://192.168.128.10:8765
STEPFUN_API_KEY=<仅保存在本机环境中>
```

- StepFun 密钥、SSH 密码和硬件服务令牌不得提交到 Git。
- SSH 自动化必须以 `ssh -o BatchMode=yes rdkx5 'echo ok'` 成功为部署完成条件。
- 板端服务只面向可信局域网；如跨网络访问，再增加令牌和 TLS，不在本次 demo 范围内。

## 7. 错误处理

- RDK X5 离线：网站返回 `health.ok=false` 和清晰提示，保留页面与历史数据可用。
- DHT11 瞬时失败：最多使用最后有效值，并标记 `stale`，不得伪装成实时数据。
- LED 下发失败：返回 502，由现有指令界面提示失败，不更新为成功状态。
- StepFun 超时或无 Key：沿用硬编码指令与现有降级提示。
- `lightLux` 为估算值时始终返回 `lightSource: "estimated"`，不称为传感器实测。

## 8. 测试与验收

- 单元测试：驱动选择、亮度边界、warm/cool 映射、超时、离线和 stale 数据。
- 契约测试：`SimDriver` 与 `RdkX5Driver` 均满足 `HardwareDriver`。
- 板端测试：DHT11 连续读取 20 次；四颗 LED 逐一亮灭；暖光在 5%、10%、20% 下无明显失控闪烁。
- 端到端验收：网页显示真实温湿度；点击“关灯/开夜灯”能在 3 秒内改变实灯；硬编码语音可控灯；配置 StepFun 后自然语言可控灯。
- 故障验收：断开 RDK X5 网络后页面不白屏，并明确显示硬件离线。

## 9. 当前阻塞

2026-07-25 的只读检查中，`ssh -o BatchMode=yes -o ConnectTimeout=5 rdkx5 'printf ok'` 在 SSH banner 交换阶段超时。开始板端部署前，需要 RDK X5 保持开机、接入 `192.168.128.10` 所在网络，并重新通过 BatchMode 验证。
