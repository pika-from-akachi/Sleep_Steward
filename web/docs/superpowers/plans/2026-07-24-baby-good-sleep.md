# 宝宝爱睡觉 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭一个响应式全栈网站,演示「睡前指令 → 硬件联动 → 睡眠中主动调节 → 数据归档 → 复盘」的完整睡眠闭环(黑客松 demo)。

**Architecture:** Next.js 全栈单体,API routes 即后端;业务层只依赖 `HardwareDriver` 接口,当前用 `SimDriver` 模拟、未来换 `RdkX5Driver` 不改上层;SQLite 本地库存全部数据;睡眠中前端每 5 秒调 `/api/tick`,后端读环境→比对偏好→自动调节→写日志。

**Tech Stack:** Next.js(App Router)+ TypeScript + Tailwind CSS v4 + lucide + Framer Motion + Three.js + Recharts + Prisma v6 + SQLite + StepFun API(OpenAI 兼容)。

> **执行状态(2026-07-24)**:Task 1–9 已完成并验证(含偏差:shadcn 弃用改自研组件;Prisma 固定 v6;新增 Three.js「月息」夜景与 Web Audio 合成助眠声音;报告页已随 Task 5 一并建出)。Task 7 的六条快捷指令与无 Key 降级可直接使用;StepFun 自然语言路径已接好,配置 `STEPFUN_API_KEY` 后启用。

## Global Constraints

- Node 版本:Node 20 LTS 或更高。
- 框架:Next.js App Router(非 Pages Router);普通 Node 服务运行(`next start`),不部署到 Serverless。
- 数据库:SQLite 本地文件 `prisma/dev.db`,通过 Prisma 访问。禁止引入 Supabase / 云数据库。
- 密钥:StepFun key 只经服务器环境变量 `STEPFUN_API_KEY` 读取,禁止出现在前端代码或提交进 git。
- UI:蓝色系高级感,克制留白,用 lucide 线性图标,**产品界面不堆 emoji**。语言:界面文案中文。
- 硬件命令白名单(动作集固定):`setLight` / `setClimate` / `playAudio` / `stopAudio`。StepFun 只能从该集合选。
- 硬编码指令词表(必须秒执行、不走 LLM):关灯、开灯、调高温度、调低温度、开夜灯、关夜灯。
- 范围外(不做):机械臂;完整账号体系(密码/找回/第三方);多租户;真实空调执行器控制。
- 每个 Task 结束都 commit;测试用 Vitest。

---

### Task 1: 项目地基与欢迎页

**Files:**
- Create: `package.json`, `next.config.mjs`, `tsconfig.json`, `tailwind.config.ts`, `app/globals.css`, `app/layout.tsx`, `app/page.tsx`
- Create: `prisma/schema.prisma`, `lib/db.ts`
- Create: `vitest.config.ts`

**Interfaces:**
- Produces: Prisma client `db` (default export of `lib/db.ts`); 数据表 `User` / `PreferenceProfile` / `SleepSession` / `SessionLog` / `VoiceCommand`。

- [ ] **Step 1: 初始化 Next.js + Tailwind + shadcn + Prisma + Vitest**

```bash
npx create-next-app@latest . --typescript --tailwind --app --eslint --src-dir=false --import-alias "@/*" --no-turbopack
npm i @prisma/client && npm i -D prisma vitest @vitejs/plugin-react
npm i framer-motion recharts lucide-react date-fns
npx prisma init --datasource-provider sqlite
npx shadcn@latest init -d
```

- [ ] **Step 2: 写 Prisma schema**

`prisma/schema.prisma`(在 generator/datasource 之后追加):

```prisma
model User {
  id        String   @id @default(cuid())
  nickname  String
  userType  String   // "adult" | "child"
  childAge  Int?
  createdAt DateTime @default(now())
  prefs     PreferenceProfile[]
  sessions  SleepSession[]
  commands  VoiceCommand[]
}

model PreferenceProfile {
  id             String   @id @default(cuid())
  userId         String
  name           String
  tempMin        Float
  tempMax        Float
  humidityMin    Float
  humidityMax    Float
  lightBrightness Int     // 0-100
  lightColorTemp String   // "warm" | "cool"
  isDefault      Boolean  @default(false)
  createdAt      DateTime @default(now())
  user           User     @relation(fields: [userId], references: [id])
  sessions       SleepSession[]
}

model SleepSession {
  id          String   @id @default(cuid())
  userId      String
  profileId   String
  startedAt   DateTime @default(now())
  endedAt     DateTime?
  status      String   // "active" | "ended"
  summaryJson String?  // JSON string
  user        User     @relation(fields: [userId], references: [id])
  profile     PreferenceProfile @relation(fields: [profileId], references: [id])
  logs        SessionLog[]
}

model SessionLog {
  id          String   @id @default(cuid())
  sessionId   String
  timestamp   DateTime @default(now())
  type        String   // env_reading | device_trigger | command | voice | error
  payloadJson String   // JSON string
  session     SleepSession @relation(fields: [sessionId], references: [id])
}

model VoiceCommand {
  id           String   @id @default(cuid())
  userId       String
  sessionId    String?
  rawText      String
  mode         String   // "hardcoded" | "natural"
  parsedJson   String   // JSON string
  matchedDevice String?
  createdAt    DateTime @default(now())
  user         User     @relation(fields: [userId], references: [id])
}
```

- [ ] **Step 3: 生成库 + 建 db.ts**

Run: `npx prisma migrate dev --name init`
`lib/db.ts`:

```ts
import { PrismaClient } from "@prisma/client";
const globalForPrisma = globalThis as unknown as { prisma?: PrismaClient };
export const db = globalForPrisma.prisma ?? new PrismaClient();
if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = db;
export default db;
```

- [ ] **Step 4: 写欢迎页(选成人/儿童 + 昵称 → 一键进入)**

`app/page.tsx`:客户端表单,单选 adult/child(child 显示年龄输入),昵称输入,「开始」按钮 POST `/api/auth`(下个 task 建),成功后 `router.push("/dashboard")`。样式:全屏蓝色渐变背景 + 居中卡片 + slogan「宝宝爱睡觉 · 你的主动式睡眠搭子」。此步先放按钮占位,提交逻辑接 Task 2。

- [ ] **Step 5: 验证 + 提交**

Run: `npm run dev`,浏览器打开 `/`,确认欢迎页渲染、能选身份、SQLite 迁移生成 `prisma/dev.db`。

```bash
git add -A && git commit -m "feat: project scaffold, prisma schema, welcome page"
```

---

### Task 2: 轻量登录 + 预填默认偏好

**Files:**
- Create: `app/api/auth/route.ts`, `lib/defaults.ts`, `lib/session-cookie.ts`

**Interfaces:**
- Consumes: `db` from `lib/db.ts`。
- Produces: `POST /api/auth` body `{ nickname, userType, childAge? }` → 建 User + 一条 `isDefault` 偏好,写 httpOnly cookie `uid`,返回 `{ userId }`;`getUserId(): Promise<string|null>` from `lib/session-cookie.ts`;`defaultPrefFor(userType): {...}` from `lib/defaults.ts`。

- [ ] **Step 1: 写默认偏好函数**

`lib/defaults.ts`:

```ts
export function defaultPrefFor(userType: "adult" | "child") {
  return userType === "child"
    ? { name: "宝宝舒睡", tempMin: 24, tempMax: 26, humidityMin: 45, humidityMax: 60, lightBrightness: 15, lightColorTemp: "warm", isDefault: true }
    : { name: "标准助眠", tempMin: 22, tempMax: 25, humidityMin: 40, humidityMax: 60, lightBrightness: 20, lightColorTemp: "warm", isDefault: true };
}
```

- [ ] **Step 2: 写 cookie 助手**

`lib/session-cookie.ts`:用 `next/headers` 的 `cookies()` 读写 `uid`(httpOnly, path "/")。导出 `setUserCookie(uid)` 与 `getUserId()`。

- [ ] **Step 3: 写 auth 路由**

`app/api/auth/route.ts`:`POST` 校验 body(nickname 非空,userType ∈ {adult,child}),`db.user.create` + `db.preferenceProfile.create(defaultPrefFor(...))`,`setUserCookie`,返回 `{ userId }`。

- [ ] **Step 4: 接通欢迎页提交**

改 `app/page.tsx` 提交逻辑真调 `/api/auth`。

- [ ] **Step 5: 验证 + 提交**

浏览器走「填昵称→进入」,确认 DB 里出现 user + 一条默认 pref,cookie 已写。

```bash
git add -A && git commit -m "feat: lightweight auth + default preference seeding"
```

---

### Task 3: 硬件抽象层 + 模拟器(核心枢纽)

**Files:**
- Create: `lib/hardware/driver.ts`(接口)、`lib/hardware/sim.ts`(SimDriver)、`lib/hardware/index.ts`(单例工厂)
- Test: `lib/hardware/sim.test.ts`

**Interfaces:**
- Produces: `HardwareDriver` 接口(见 spec §5);`getDriver(): HardwareDriver` 返回进程内单例 SimDriver;SimDriver 额外方法 `injectEnv(partial)` 供 demo 造场。

- [ ] **Step 1: 写接口**

`lib/hardware/driver.ts`:

```ts
export interface EnvReading { tempC: number; humidityPct: number; lightLux: number }
export interface LightCmd { on: boolean; brightness: number; colorTemp?: "warm" | "cool" }
export interface HardwareDriver {
  readEnvironment(): Promise<EnvReading>;
  setLight(cmd: LightCmd): Promise<void>;
  setClimate(cmd: { targetTempC: number }): Promise<void>;
  playAudio(cmd: { trackId: string; loop: boolean } | { stop: true }): Promise<void>;
  health(): Promise<{ ok: boolean; driver: "sim" | "rdk-x5" }>;
}
```

- [ ] **Step 2: 写失败测试**

`lib/hardware/sim.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { SimDriver } from "./sim";

describe("SimDriver", () => {
  it("readEnvironment returns current virtual state", async () => {
    const d = new SimDriver();
    const env = await d.readEnvironment();
    expect(env.tempC).toBeGreaterThan(0);
  });
  it("setClimate moves virtual temperature toward target over reads", async () => {
    const d = new SimDriver();
    d.injectEnv({ tempC: 18 });
    await d.setClimate({ targetTempC: 24 });
    const a = (await d.readEnvironment()).tempC;
    const b = (await d.readEnvironment()).tempC;
    expect(b).toBeGreaterThan(a); // 向目标收敛
  });
  it("injectEnv lets demo force a cold room", async () => {
    const d = new SimDriver();
    d.injectEnv({ tempC: 15 });
    expect((await d.readEnvironment()).tempC).toBe(15);
  });
});
```

- [ ] **Step 3: 运行确认失败**

Run: `npx vitest run lib/hardware/sim.test.ts` → FAIL(SimDriver 未定义)。

- [ ] **Step 4: 实现 SimDriver**

`lib/hardware/sim.ts`:维护 `{ tempC, humidityPct, lightLux, targetTempC, light }` 状态。`readEnvironment` 每次调用时若 `tempC` 偏离 `targetTempC` 则朝目标步进 0.5℃(模拟执行器生效),返回当前值。`setClimate` 设 `targetTempC`。`setLight` 改灯态并按 brightness 反映到 `lightLux`。`injectEnv(partial)` 直接覆盖状态字段。`playAudio` 仅返回。`health` 返回 `{ ok:true, driver:"sim" }`。

- [ ] **Step 5: 运行确认通过 + 单例工厂**

Run: `npx vitest run lib/hardware/sim.test.ts` → PASS。写 `lib/hardware/index.ts`:模块级单例 `getDriver()`(用 `globalThis` 缓存,避免 dev 热重载多实例)。

```bash
git add -A && git commit -m "feat: hardware abstraction layer + simulator driver"
```

---

### Task 4: 闭环判断纯函数 decideAdjustments(产品心脏)

**Files:**
- Create: `lib/loop/decide.ts`
- Test: `lib/loop/decide.test.ts`

**Interfaces:**
- Consumes: `EnvReading` from `lib/hardware/driver.ts`。
- Produces: `decideAdjustments(env: EnvReading, prefs: Thresholds): Adjustment[]`,其中 `Thresholds = { tempMin, tempMax, humidityMin, humidityMax, lightBrightness }`,`Adjustment = { kind: "climate"|"light"; command: object; message: string }`。

- [ ] **Step 1: 写失败测试**

`lib/loop/decide.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { decideAdjustments } from "./decide";
const prefs = { tempMin: 22, tempMax: 25, humidityMin: 40, humidityMax: 60, lightBrightness: 20 };

describe("decideAdjustments", () => {
  it("偏冷时输出升温到区间中值", () => {
    const out = decideAdjustments({ tempC: 18, humidityPct: 50, lightLux: 5 }, prefs);
    const climate = out.find(a => a.kind === "climate");
    expect(climate?.command).toEqual({ targetTempC: 23.5 });
    expect(climate?.message).toContain("升温");
  });
  it("区间内不动作", () => {
    expect(decideAdjustments({ tempC: 23, humidityPct: 50, lightLux: 5 }, prefs)).toHaveLength(0);
  });
  it("滞回:略低于 min(在 0.5℃ 缓冲内)不动作", () => {
    expect(decideAdjustments({ tempC: 21.7, humidityPct: 50, lightLux: 5 }, prefs)).toHaveLength(0);
  });
  it("光照偏亮时调暗", () => {
    const out = decideAdjustments({ tempC: 23, humidityPct: 50, lightLux: 300 }, prefs);
    expect(out.find(a => a.kind === "light")?.message).toContain("调暗");
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `npx vitest run lib/loop/decide.test.ts` → FAIL。

- [ ] **Step 3: 实现**

`lib/loop/decide.ts`:温度低于 `tempMin - 0.5`(滞回缓冲)→ 输出 `{ kind:"climate", command:{ targetTempC:(tempMin+tempMax)/2 }, message:\`检测到偏冷,已升温至 ${(tempMin+tempMax)/2}℃\` }`;高于 `tempMax + 0.5` 类似降温;`lightLux` 换算成感知亮度超过 `lightBrightness` 对应阈值(用固定映射 `lux ≈ brightness*10`,超过则)→ 输出调暗 light 命令。湿度越界预留同理(demo 可仅记消息)。返回数组。

- [ ] **Step 4: 运行确认通过**

Run: `npx vitest run lib/loop/decide.test.ts` → PASS。

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: decideAdjustments loop logic with hysteresis"
```

---

### Task 5: 会话生命周期 + /tick 闭环 + 睡眠中页

**Files:**
- Create: `app/api/session/route.ts`(POST 建会话 / PATCH 结束)、`app/api/tick/route.ts`、`lib/loop/run-tick.ts`、`app/sleeping/page.tsx`
- Test: `lib/loop/run-tick.test.ts`

**Interfaces:**
- Consumes: `getDriver()`, `decideAdjustments`, `db`, `getUserId()`。
- Produces: `POST /api/session` → `{ sessionId }`(用当前用户的 default pref);`PATCH /api/session` body `{ sessionId }` → 写 endedAt/status/summaryJson;`POST /api/tick` body `{ sessionId }` → `{ env, adjustments, messages }`;`runTick(sessionId): Promise<TickResult>` from `lib/loop/run-tick.ts`。

- [ ] **Step 1: 写 runTick 失败测试**

`lib/loop/run-tick.test.ts`:mock `getDriver` 返回一个可 `injectEnv` 的假 driver,建一个内存 session,断言:注入冷环境后 `runTick` 返回含升温 adjustment,且调用了 driver.setClimate,并写入了 device_trigger 日志。(用 Prisma 的 sqlite 内存或临时文件测试库。)

- [ ] **Step 2: 运行确认失败**

Run: `npx vitest run lib/loop/run-tick.test.ts` → FAIL。

- [ ] **Step 3: 实现 runTick**

`lib/loop/run-tick.ts`:读 session→取 profile 阈值→`driver.readEnvironment()`→`decideAdjustments`→对每个 adjustment 调对应 driver 方法 + 写 `SessionLog(type:"device_trigger")`,并写一条 `env_reading` 日志→返回 `{ env, adjustments, messages }`。

- [ ] **Step 4: 实现路由 + 睡眠中页**

`app/api/session/route.ts`、`app/api/tick/route.ts` 薄封装。`app/sleeping/page.tsx`:深蓝夜间 UI,大计时器,`useEffect` 每 5 秒 fetch `/api/tick`;用 Recharts 画温度曲线(累积 tick 数据);收到 adjustment 时用 Framer Motion 弹出轻提示条(文案来自 `messages`);「结束睡眠」PATCH session 后跳 `/report/[id]`。tick 失败静默重试,连续 3 次才提示。

- [ ] **Step 5: 验证 + 提交**

Run vitest 通过;手动:进睡眠中页,靠 Task 6 的造场把温度调冷,确认曲线更新 + 弹「已升温」提示 + DB 有日志。

```bash
git add -A && git commit -m "feat: session lifecycle, tick loop, sleeping page"
```

---

### Task 6: 仪表盘 + 演示造场 + 助眠资源

**Files:**
- Create: `app/dashboard/page.tsx`、`app/api/demo/inject/route.ts`、`components/EnvCards.tsx`、`components/PrefCards.tsx`、`components/SleepAudio.tsx`、`components/DemoPanel.tsx`
- Create: `public/audio/`(放 2-3 段音乐 + 1 段冥想占位音频)

**Interfaces:**
- Consumes: `getDriver().injectEnv`(仅经 `/api/demo/inject` 暴露)、`/api/session`、偏好列表 `/api/prefs`(Task 8)。
- Produces: `POST /api/demo/inject` body `{ tempC?, humidityPct?, lightLux? }` → 调 SimDriver.injectEnv;仪表盘页。

- [ ] **Step 1: 造场 API**

`app/api/demo/inject/route.ts`:`POST` 调 `getDriver()`(断言为 SimDriver)的 `injectEnv`,返回最新 env。

- [ ] **Step 2: 仪表盘页 + 组件**

`app/dashboard/page.tsx`:顶部 `EnvCards`(实时温/湿/灯,带 Framer Motion 数字动效);中部 `PrefCards`(偏好模板卡,点一下 POST 应用→下发 setLight/setClimate);`SleepAudio`(成人:冥想+音乐 tab;儿童:仅音乐,依据 user.userType 过滤);大按钮「开始睡眠」→ `/api/session` → 跳 `/sleeping`;角落 `DemoPanel`(可折叠,滑块调冷/热/湿度,调 `/api/demo/inject`)。

- [ ] **Step 3: 验证 + 提交**

手动:仪表盘显示环境、点偏好卡灯态变化、造场面板能改读数、开始睡眠跳转正常。

```bash
git add -A && git commit -m "feat: dashboard, demo panel, sleep audio"
```

---

### Task 7: 语音指令(硬编码词表 + StepFun 自然语言解析)

**Files:**
- Create: `lib/voice/hardcoded.ts`、`lib/voice/stepfun.ts`、`app/api/voice/parse/route.ts`、`components/VoiceInput.tsx`
- Test: `lib/voice/hardcoded.test.ts`、`lib/voice/stepfun.test.ts`

**Interfaces:**
- Consumes: `getDriver()`, `db`, `STEPFUN_API_KEY`。
- Produces: `matchHardcoded(text): ParsedCommand | null`;`parseWithStepfun(text, capabilities): Promise<ParsedCommand>`;`POST /api/voice/parse` body `{ text, sessionId? }` → 执行 driver + 写 VoiceCommand,返回 `{ mode, parsed, message }`。`ParsedCommand = { action: "setLight"|"setClimate"|"playAudio"|"stopAudio"; params: object }`。

- [ ] **Step 1: 硬编码词表失败测试**

`lib/voice/hardcoded.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { matchHardcoded } from "./hardcoded";
describe("matchHardcoded", () => {
  it("关灯 → setLight off", () => {
    expect(matchHardcoded("关灯")).toEqual({ action: "setLight", params: { on: false, brightness: 0 } });
  });
  it("调高温度 → setClimate +", () => {
    expect(matchHardcoded("调高温度")?.action).toBe("setClimate");
  });
  it("无关文本 → null", () => {
    expect(matchHardcoded("讲个笑话")).toBeNull();
  });
});
```

- [ ] **Step 2: 运行失败 → 实现 hardcoded.ts → 运行通过**

实现固定词表映射(关灯/开灯/调高温度/调低温度/开夜灯/关夜灯 → 对应 ParsedCommand)。Run: `npx vitest run lib/voice/hardcoded.test.ts`。

- [ ] **Step 3: StepFun 解析失败测试(mock fetch)**

`lib/voice/stepfun.test.ts`:mock 全局 `fetch`。测三条:返回合法 JSON `{action,params}` 且 action 在白名单 → 通过;返回非白名单 action → 抛错/回退;fetch 超时(用 `AbortController`,mock reject)→ 抛超时错误。

- [ ] **Step 4: 实现 stepfun.ts**

`lib/voice/stepfun.ts`:调 `https://api.stepfun.com/v1/chat/completions`(OpenAI 兼容),system prompt 给设备能力清单 + 要求「只输出 JSON `{action,params}`,action 必须属于白名单」,`response_format: json_object`,2 秒 `AbortController` 超时。解析后校验 action ∈ 白名单,否则抛错。

- [ ] **Step 5: 实现路由 + VoiceInput 组件 + 提交**

`app/api/voice/parse/route.ts`:先 `matchHardcoded`,命中则 mode="hardcoded";否则 `parseWithStepfun`,mode="natural";失败则返回回退提示 `没太听懂,试试:关灯 / 调高温度 / 开夜灯` 并记未解析。命中则调 driver 执行 + 写 `VoiceCommand`。`components/VoiceInput.tsx`:输入框 + 提交,展示执行结果 toast。

```bash
git add -A && git commit -m "feat: voice commands with hardcoded table + StepFun fallback"
```

---

### Task 8: 报告 + 历史日历 + 偏好管理

**Files:**
- Create: `app/api/prefs/route.ts`(GET/POST/PATCH/DELETE)、`app/api/history/route.ts`(GET)、`app/report/[sessionId]/page.tsx`、`app/history/page.tsx`、`app/preferences/page.tsx`
- Create: `lib/report/summarize.ts`
- Test: `lib/report/summarize.test.ts`

**Interfaces:**
- Consumes: `db`, `getUserId()`, session logs。
- Produces: `summarizeSession(sessionId): Promise<Summary>`(时长、起止、温湿度波动点、灯光调节次数、mock 戒指分期、语音指令数);偏好 CRUD 路由;历史列表路由。

- [ ] **Step 1: summarize 失败测试**

`lib/report/summarize.test.ts`:建一个带若干 env_reading + device_trigger 日志的 session,断言 summary 的 `lightAdjustCount` 等于 light 类 device_trigger 数、`durationMin` 正确、`ringStages` 存在(mock 数据)。

- [ ] **Step 2: 运行失败 → 实现 summarize.ts → 通过**

`lib/report/summarize.ts`:聚合日志算时长/曲线点/调节次数,生成 mock 戒指睡眠分期(基于时长切浅/深/REM 段),写回 `session.summaryJson`。

- [ ] **Step 3: 报告页**

`app/report/[sessionId]/page.tsx`:Recharts 画温湿度波动 + 睡眠分期条;展示语音指令记录;底部「存为新偏好模板」按钮 POST `/api/prefs`(用本次环境均值)。

- [ ] **Step 4: 历史日历 + 偏好页**

`app/history/page.tsx`:日历(date-fns 排月),有记录日期高亮,点击进报告;附「语音指令翻译记录」列表(查 VoiceCommand)。`app/preferences/page.tsx`:列出 profiles,增/删/改表单,调 `/api/prefs`。

- [ ] **Step 5: 验证 + 提交**

手动:结束一次睡眠→看报告→存模板→在偏好页看到→历史日历点回该天。

```bash
git add -A && git commit -m "feat: report, history calendar, preference management"
```

---

### Task 9: 打磨 + 预置演示数据 + 走查

**Files:**
- Create: `prisma/seed.ts`、`README.md`
- Modify: 各页面样式细节

**Interfaces:**
- Produces: `npm run seed` 生成「成人-小明」「儿童-乐乐3岁」两个带历史 session 的样板账号。

- [ ] **Step 1: 种子脚本**

`prisma/seed.ts`:建 2 个用户 + 各 2 套偏好 + 各 2-3 条已结束 session(带日志),使历史/报告页开箱有数据。`package.json` 加 `"seed": "tsx prisma/seed.ts"`。

- [ ] **Step 2: UI 打磨**

统一蓝色系(定义 CSS 变量:主色、深夜背景),Framer Motion 页面过渡,检查移动端自适应(dashboard 卡片单列、睡眠中页大字),确认全站无多余 emoji、图标用 lucide。

- [ ] **Step 3: README + demo 脚本**

`README.md`:如何 `npm run dev`、设 `STEPFUN_API_KEY`、`npm run seed`、演示话术(先造场调冷→进睡眠中看自动升温→说自然语言指令)。

- [ ] **Step 4: 全流程走查 + 提交**

手动跑一遍五阶段闭环;`npx vitest run` 全绿。

```bash
git add -A && git commit -m "chore: seed data, UI polish, demo README"
```
