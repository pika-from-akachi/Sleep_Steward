<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# 宝宝爱睡觉 · 项目约定

AdventureX 黑客松 demo:主动式睡眠搭子(响应式全栈网站)。机械臂是团队另一条硬件线,不进本项目。
需求、架构、决策的权威文档在 docs/(见文末指针表),本文件只放规则与速查。

## 命令

- `npm run dev` — 开发服务(localhost:3000)
- `npm run test` — vitest(模拟器 + 闭环判断,改相关代码后必须全绿)
- `npx tsc --noEmit` — 类型检查
- `npx prisma migrate dev --name <名>` — 改 schema 后建迁移
- `npm run seed` — 种子数据(prisma/seed.ts 尚未创建,创建后生效)

## 结构速查

- `lib/hardware/` — 硬件抽象层。业务代码只准依赖 `HardwareDriver` 接口;`SimDriver` 具体类只允许出现在 lib/hardware 内部与 `/api/env`、`/api/demo/inject` 两个路由
- `lib/loop/decide.ts` — 自动调节判断纯函数(产品心脏,带滞回;改它必须跑测试)
- `lib/loop/run-tick.ts` — 睡眠中每 5 秒巡检:读环境 → 判断 → 执行 → 留痕(2 分钟内相同动作去抖)
- `app/api/` — auth / env / command / demo/inject / session / tick / prefs
- `components/NightSky.tsx` — Three.js 程序化月夜背景(月息视觉核心,无贴图可离线)
- `components/SleepAudio.tsx` — Web Audio 实时合成助眠声音(无音频文件)
- `prisma/schema.prisma` — 5 张表:User / PreferenceProfile / SleepSession / SessionLog / VoiceCommand

## 红线

- 不接云数据库:SQLite 本地文件(prisma/dev.db),禁止引入 Supabase 等
- StepFun key 只走服务器环境变量 `STEPFUN_API_KEY`,不进代码、不进前端
- 产品 UI 不用 emoji;图标一律 lucide 线性图标
- 视觉遵循「月息」方向:暖夜配色 token 在 app/globals.css(--night-* / --cream / --moon),标题与关键数字用 `.serif`(宋体);温暖为主、科技感不得压过温暖
- Prisma 固定 v6(v7 移除 schema 内 datasource url,是 breaking 改动,勿升级)
- 硬件指令动作白名单:setLight / setClimate / playAudio / stopAudio,StepFun 只能从中选
- 演示走本机 `npm run dev`;git push 等用户发话,不自动执行

## 深入文档

| 主题 | 文件 |
|---|---|
| 需求与设计(权威) | docs/superpowers/specs/2026-07-24-baby-good-sleep-design.md |
| 实现计划与执行状态 | docs/superpowers/plans/2026-07-24-baby-good-sleep.md |
| 视觉素材生成 briefs | docs/asset-briefs/ |
