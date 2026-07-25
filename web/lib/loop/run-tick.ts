import { db } from "@/lib/db";
import { getDriver } from "@/lib/hardware";
import type { EnvReading, HardwareDriver } from "@/lib/hardware/driver";
import { decideAdjustments, type Adjustment, type Thresholds } from "./decide";

export interface TickResult {
  env: EnvReading;
  adjustments: Adjustment[];
  messages: string[];
}

/**
 * 睡眠中每 ~5 秒执行一轮:读环境 → 比对偏好 → 自动调节 → 全程留痕。
 * driverOverride 仅测试用。
 */
export async function runTick(sessionId: string, driverOverride?: HardwareDriver): Promise<TickResult> {
  const driver = driverOverride ?? getDriver();
  const session = await db.sleepSession.findUnique({
    where: { id: sessionId },
    include: { profile: true },
  });
  if (!session || session.status !== "active") {
    throw new Error("会话不存在或已结束");
  }

  const env = await driver.readEnvironment();
  await db.sessionLog.create({
    data: { sessionId, type: "env_reading", payloadJson: JSON.stringify(env) },
  });

  const prefs: Thresholds = {
    tempMin: session.profile.tempMin,
    tempMax: session.profile.tempMax,
    humidityMin: session.profile.humidityMin,
    humidityMax: session.profile.humidityMax,
    lightBrightness: session.profile.lightBrightness,
  };
  const adjustments = decideAdjustments(env, prefs);

  // 去抖:2 分钟内完全相同的调节动作不重复留痕、不重复提示
  // (执行器指令幂等,照常下发;避免恢复期间每 5 秒刷一条「已升温」)
  const recentTriggers = await db.sessionLog.findMany({
    where: {
      sessionId,
      type: "device_trigger",
      timestamp: { gt: new Date(Date.now() - 120_000) },
    },
    orderBy: { timestamp: "desc" },
  });
  const lastCommandByKind = new Map<string, string>();
  for (const log of recentTriggers) {
    const p = JSON.parse(log.payloadJson);
    if (!lastCommandByKind.has(p.kind)) lastCommandByKind.set(p.kind, JSON.stringify(p.command));
  }

  const announced: Adjustment[] = [];
  for (const adj of adjustments) {
    if (adj.kind === "climate") {
      await driver.setClimate({ targetTempC: adj.command.targetTempC as number });
    } else if (adj.kind === "light") {
      await driver.setLight({
        on: true,
        brightness: session.profile.lightBrightness,
        colorTemp: session.profile.lightColorTemp === "cool" ? "cool" : "warm",
      });
    }
    // humidity:执行器未定,只留痕(接口已在 spec 预留)
    const isRepeat = lastCommandByKind.get(adj.kind) === JSON.stringify(adj.command);
    if (!isRepeat) {
      await db.sessionLog.create({
        data: { sessionId, type: "device_trigger", payloadJson: JSON.stringify(adj) },
      });
      announced.push(adj);
    }
  }

  return { env, adjustments: announced, messages: announced.map((a) => a.message) };
}
