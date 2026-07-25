# 宝宝爱睡觉 · 你的主动式睡眠搭子

AdventureX 黑客松作品:睡前一键布置卧室环境,睡眠中系统每 5 秒自动巡检温湿度与光照、
偏离偏好即自动调节,醒来生成完整睡眠报告。硬件层当前为模拟器,接口已为 RDK X5 预留。

## 快速开始

```bash
npm install
npx prisma migrate dev   # 初始化 SQLite(prisma/dev.db)
npm run seed             # 写入小明 / 乐乐样板账号与历史记录
npm run dev              # http://localhost:3000
```

可选:语音自然语言解析需要在项目根 `.env` 添加 `STEPFUN_API_KEY=<你的 key>`。
未配置时六条快捷指令仍可立即执行,其他说法会安全降级。模型默认
`step-3.5-flash`,也可用服务器变量 `STEPFUN_MODEL` 覆盖。

样板账号可从欢迎页直接取回:

- 成人模式:昵称「小明」
- 儿童模式:昵称「乐乐」,年龄 3

## 演示动线(评委版)

1. 欢迎页选身份、输昵称,「入夜」一键进入(自动预置 4 套睡眠方案)
2. 仪表盘右下角「演示」面板,把温度拉到 15℃(模拟环境突变)
3. 「开始睡眠」→ 数秒内看系统自动弹出「检测到偏冷,已升温至 23.5℃」,温度曲线回升
4. 「结束睡眠」→ 查看睡眠报告(时长、调节次数、温湿度曲线、睡眠分期)

## 验证

```bash
npm run test      # 模拟器 + 自动调节判断的单元测试
npx tsc --noEmit  # 类型检查
```

## 部署

本项目包含 Next.js 服务端路由和 SQLite，不能部署到仅支持静态文件的
GitHub Pages。推荐使用 Railway：GitHub 负责多人协作与版本管理，Railway
监听 `master` 分支并自动部署通过 CI 的提交。

生产地址：<https://baby-good-sleep-production.up.railway.app>

首次配置：

1. 在 Railway 选择 `Deploy from GitHub repo`，连接本仓库。
2. 给 Web Service 挂载一个 Volume，挂载路径设为 `/data`。
3. 添加环境变量 `DATABASE_URL=file:/data/prod.db`。
4. 如需自然语言语音解析，再添加 Secret `STEPFUN_API_KEY`。
5. 在 Networking 中生成公开域名。
6. 确认部署分支为 `master`，开启 `Wait for CI`。

仓库内的 `railway.json` 会在首次启动时创建 SQLite 文件，并在每次启动时
自动执行数据库迁移和幂等种子数据，
`.github/workflows/ci.yml` 会在推送和 Pull Request 时运行测试、类型检查与
生产构建。SQLite Volume 只支持单实例运行，足够本次黑客松 demo 使用。

## 文档

- 设计 spec(权威):`docs/superpowers/specs/2026-07-24-baby-good-sleep-design.md`
- 实现计划与执行状态:`docs/superpowers/plans/2026-07-24-baby-good-sleep.md`
- AI 协作约定:`AGENTS.md`
