# 宝宝爱睡觉 · 你的主动式睡眠搭子 — 设计文档

> 状态:设计已确认(2026-07-24),待进入实现计划
> 场景:AdventureX 黑客松 demo

## 1. 背景与定位

一个响应式全栈网站,做「主动式睡眠生态」软件闭环:用户睡眠数据管理 + 自然语言/点击式硬件外设调度 + 睡眠辅助功能。

**定位:黑客松 demo**。目标是把「睡前指令 → 硬件联动 → 睡眠中主动调节 → 数据归档 → 复盘」这个完整闭环跑通并演示得漂亮,追求快速落地 + 视觉高级。不追求完整账号体系、大规模多用户、云部署。

**范围边界**:机械臂盖被子是另一条独立硬件线,**不在本软件范围内**。本软件专注睡眠生态,不涉及机械臂场景。

**双用户模式**:成人(冥想 + 音乐)与儿童(仅轻音乐)。

**硬件现状**:温湿度传感器 / LED / 扬声器 / 睡眠戒指均未采购,「后续会连接」。因此当前用模拟器 + 硬件抽象层,把接口提前定死,以后接 RDK X5 真硬件不改上层。

## 2. 关键决策记录

| 决策点 | 结论 | 理由 |
|---|---|---|
| 项目定位 | 黑客松 demo,快 + 好看 | 参加 AdventureX,机械臂另做,软件独立 |
| 硬件方案 | 模拟器 + 可手动造场(HAL) | 硬件未到位,但要让「主动式自动调节」在评委面前真跑起来 |
| 目标用户 | 双模式:成人 + 儿童 | 名字叫"宝宝"但含成人冥想,一个产品兼顾两类人,故事更丰富 |
| 入口/onboarding | 一键进入 + 预填默认偏好 | 不用强制向导拦住用户,立刻看到好看的主界面 |
| 技术栈 | Next.js 全栈单体 + SQLite | 一个代码库一次部署;UI 生态成熟;闭环可真跑;能跑在 RDK X5 |
| LLM | StepFun(阶跃星辰),OpenAI 兼容 | 后端解析自然语言指令 |
| 数据库 | SQLite 本地文件 | demo 无需云库,零配置、随项目走 |
| 戒指睡眠分期 | 作为模拟数据存进 session 汇总 | 丰富报告页,不引入真硬件依赖 |
| UI 风格 | 蓝色系高级感,克制,**不堆 emoji** | 高级感靠留白/层次/线性图标/克制动效 |
| 视觉方向(2026-07-24 定稿) | 「月息」暖夜:Three.js 呼吸月球 + 眨眼星空 + 贴地萤火,宋体承题,全站唯月独暖 | 用户否掉模板化方案后共创确定;产品是陪伴型,温暖为主、科技感不得压过温暖 |

## 3. 技术栈

- **框架**:Next.js(App Router)+ TypeScript,前后端同一项目(API routes 即后端)
- **UI**:Tailwind CSS(v4)+ lucide 图标 + Framer Motion(动效)。原计划的 shadcn/ui 因与 Tailwind v4 + Next 16 兼容摩擦弃用,组件自研
- **3D 场景**:Three.js 程序化月夜背景(着色器生成月球/星空/萤火,无贴图、可离线),见 components/NightSky.tsx
- **图表**:Recharts
- **数据库**:SQLite 本地文件,Prisma **固定 v6**(v7 移除 schema 内 datasource url,breaking)
- **LLM**:StepFun API(OpenAI 兼容),key 放服务器环境变量,不进前端/代码
- **运行**:普通 Node 服务(`next start`),可跑在笔记本或 RDK X5 的 ARM Linux

## 4. 架构与分层

```
┌─────────────────────────────────────────────────────┐
│  前端页面 (Next.js + React + Tailwind + shadcn/ui)     │
│  欢迎页 · 仪表盘 · 睡眠中 · 睡眠报告 · 历史日历 · 我的偏好  │
└───────────────┬─────────────────────────────────────┘
                │ 调用后端 API (同一项目内)
┌───────────────┴─────────────────────────────────────┐
│  后端 API 路由 (Next.js API routes)                    │
│  /session · /tick · /command · /voice/parse           │
│  /prefs · /history · /auth                             │
└──────┬───────────────────────┬───────────────┬───────┘
       │                       │               │
┌──────┴──────┐   ┌────────────┴─────┐  ┌──────┴───────┐
│  业务逻辑层   │   │  硬件抽象层 HAL   │  │ StepFun 客户端  │
│ 会话/阈值判断 │──▶│ HardwareDriver接口│  └──────────────┘
│ 偏好/报告汇总 │   │  ├ SimDriver(现在) │
└──────┬──────┘   │  └ RdkX5Driver(以后)│
       │          └──────────────────┘
┌──────┴──────────────────────────────┐
│  数据层 SQLite (本地 .db 文件)          │
└─────────────────────────────────────┘
```

**HAL 是设计枢纽**:业务层只依赖 `HardwareDriver` 接口。现在背后是 `SimDriver`(维护虚拟温湿度/灯光状态,支持 demo 手动造场);以后接 RDK X5 只加 `RdkX5Driver`,上层零改动。

**Node↔硬件桥接**:RDK X5 的 GPIO 控制是 Python(`Hobot.GPIO`,树莓派 `RPi.GPIO` 兼容),后端是 Node。真接硬件时,板子上跑一个极小的 Python 硬件守护进程(暴露 localhost 读传感器/控 GPIO/播音频),`RdkX5Driver` 用 HTTP 调它。Python 归 Python、Node 归 Node。

## 5. 硬件抽象层接口(现在定死)

```ts
interface HardwareDriver {
  readEnvironment(): Promise<{ tempC: number; humidityPct: number; lightLux: number }>
  //  Sim: 读虚拟状态 | RDK: I²C 读 SHT3x 温湿度 + 光敏
  setLight(cmd: { on: boolean; brightness: number /*0-100*/; colorTemp?: 'warm'|'cool' }): Promise<void>
  //  Sim: 改虚拟灯态 | RDK: GPIO/PWM 调占空比控亮度
  setClimate(cmd: { targetTempC: number }): Promise<void>
  //  Sim: 虚拟温度向目标收敛 | RDK: GPIO 继电器/红外触发空调·加热器(★需外部执行器,后续)
  playAudio(cmd: { trackId: string; loop: boolean } | { stop: true }): Promise<void>
  //  Sim: 记日志(音频实际在浏览器播) | RDK: 可选走板载扬声器
  health(): Promise<{ ok: boolean; driver: 'sim' | 'rdk-x5' }>
}
```

**RDK X5 接口事实**(来自官方文档):40 针排针 3.3V 逻辑;温湿度走 I²C;LED 走 GPIO/PWM(PWM 做亮度渐变);扬声器走 I²S + ES8326B 音频芯片;GPIO 库 `Hobot.GPIO`。

**诚实约束**:RDK X5 自身无法凭空升/降温,`setClimate` 真实场景是触发外接空调/加热器(继电器或红外),该执行器尚未确定。接口已预留,模拟器负责演示,以后接执行器不改上层。

## 6. 数据模型(SQLite,5 张表)

**users** — `id` · `nickname` · `user_type`(adult/child)· `child_age`(可空)· `created_at`
> 轻量登录只认昵称,无密码。`user_type` 决定内容库是否给冥想。

**preference_profiles** — `id` · `user_id` · `name` · `temp_min`/`temp_max` · `humidity_min`/`humidity_max` · `light_brightness`(0-100)· `light_color_temp`(warm/cool)· `is_default` · `created_at`
> 支持一个用户多套模板。阶段5 增删改、阶段4 存为新模板均落此表。一键进入时预填一条 `is_default`。

**sleep_sessions** — `id` · `user_id` · `profile_id` · `started_at` · `ended_at` · `status`(active/ended)· `summary_json`(睡眠时长、灯光调节次数、戒指睡眠分期数据等)
> 阶段2「开始睡眠」建条,阶段4「结束睡眠」补 `ended_at` + `summary_json`。

**session_logs** — `id` · `session_id` · `timestamp` · `type`(env_reading / device_trigger / command / voice / error)· `payload_json`
> 阶段3 全程日志。报告页的温湿度曲线、触发记录由此计算。一张表靠 `type` 区分,不拆多张。

**voice_commands** — `id` · `user_id` · `session_id`(可空)· `raw_text` · `mode`(hardcoded/natural)· `parsed_json` · `matched_device` · `created_at`
> 阶段5「查看自然语言原始翻译记录」独立成表,展示 StepFun 解析能力。

## 7. 页面与用户流程

**① 欢迎页 `/`(阶段1)** — 蓝色高级封面 + slogan;选成人/儿童(儿童填年龄)+ 输昵称 → 建/取 user + 预填默认偏好 → 直接进仪表盘(不拦向导)。

**② 仪表盘 `/dashboard`(阶段2 · 高频核心)** — 顶部实时环境卡片(温/湿/灯);中部睡眠方案卡片(点一下应用偏好并下发硬件);语音指令区(硬编码词秒执行 / 自然语言走 StepFun);助眠资源(成人:冥想+音乐;儿童:仅轻音乐,浏览器播放);大按钮「开始睡眠」建 session;角落可开关「演示控制」(造场:手动调冷/热/湿度)。

**③ 睡眠中 `/sleeping`(阶段3 · 主动闭环主舞台)** — 深蓝夜间界面 + 大计时器;实时曲线随 `/tick` 每 ~5 秒更新;自动调节时轻提示(如「检测到偏冷,已升温至 24℃」);「结束睡眠」补齐汇总 → 报告页。

**④ 睡眠报告 `/report/[sessionId]`(阶段4)** — 本次汇总(时长、起止、温湿度波动曲线、灯光调节次数、戒指睡眠分期图、语音指令记录);底部「存为新偏好模板」(新增/覆盖)。

**⑤ 历史日历 `/history`(阶段5)** — 日历面板,有记录日期高亮,点击打开当天报告;入口查看所有语音指令翻译记录。

**⑥ 我的偏好 `/preferences`(阶段5)** — 列出多套模板,增/删/改(温湿度区间、灯光)。

## 8. 主动式闭环数据流

**A. `/tick`(睡眠中每 ~5 秒)**
1. `driver.readEnvironment()` 读当前温湿度/光照
2. 取本次 session 偏好阈值
3. 逐项比对并执行:温度<min → `setClimate(舒适中值)`;湿度越界 → 预留除/加湿;光照偏亮 → `setLight(调暗)`
4. 每步写 `session_logs`(env_reading + 触发动作)
5. 返回前端:最新环境 + 本轮是否调节 + 提示文案

> 判断与执行全在后端,前端只定时触发+展示。加**滞回**避免边界反复横跳。Sim→RDK 前端零改动。

**B. `/voice/parse`(语音指令)**
1. 先本地匹配硬编码词表(关灯/调高温度/调低温度/开夜灯/关夜灯)→ 命中直接下发,快稳免费
2. 未命中 → 调 StepFun,给设备能力清单,要求只输出结构化 JSON `{ action, params }`
3. 校验 JSON 合法 + action 在白名单 → 下发 driver
4. 全程写 `voice_commands`(原话 + 解析结果)

> StepFun 被约束为「从固定动作集选 + 填参」,结果可控可执行。

## 9. 错误处理(demo 防翻车重点)

- **StepFun 超时/挂**:2 秒超时 → 回退提示「没太听懂,试试:关灯 / 调高温度 / 开夜灯」,记为未解析,绝不白屏。
- **传感器未接/读数异常**:`SimDriver` 永远有值;`RdkX5Driver` 读失败返回上次有效值 + 降级标记,`health()` 反映;界面显示「传感器离线,使用模拟数据」不崩。
- **指令下发失败**:driver 抛错 → 记 `error` 日志 + toast「指令未成功,已重试」,不阻塞会话。
- **`/tick` 偶发失败**:前端静默重试,连续多次才提示。
- **会话状态兜底**:刷新/断线重连靠 `sessions.status=active` 恢复,不丢会话。

## 10. 测试策略

- **闭环判断逻辑**:纯函数 `decideAdjustments(env, prefs)` 单元测试(偏冷升温、边界不抖、区间内不动)—— 产品心脏,必测。
- **StepFun 解析**:Mock 外部 API,测命中硬编码 / 自然语言回退 / 超时降级三路径。
- **HAL 契约**:`SimDriver` 与未来 `RdkX5Driver` 跑同一套接口测试。
- 页面层以手动走查 demo 流程为主(黑客松节奏)。

## 11. 分步搭建节奏(与用户一起做,每步可运行)

1. **地基**:Next.js + Tailwind/shadcn + SQLite/表结构 + 欢迎页一键进仪表盘(空壳)
2. **HAL + 模拟器**:`HardwareDriver` + `SimDriver` + 演示造场 + 仪表盘实时环境
3. **睡眠会话 + 闭环**:开始/结束睡眠、`/tick` 自动调节、日志、睡眠中页(**核心 demo 时刻优先跑通**)
4. **语音指令**:硬编码词表 + StepFun 解析 + 翻译记录
5. **报告 + 历史 + 偏好**:睡眠报告、历史日历、偏好增删改
6. **打磨**:蓝色高级 UI、动效、预置演示数据,走顺 demo

> 每步做完在浏览器可见进展,对齐后再走下一步。核心闭环(第3步)优先;时间紧时 4-6 步按重要性取舍。

## 12. 非目标(明确不做)

- 机械臂盖被子场景(独立硬件线)
- 完整账号体系(密码、找回、第三方登录)
- 云数据库 / 多租户 / 大规模并发
- 真实空调/加热执行器控制(接口预留,执行器未定)
