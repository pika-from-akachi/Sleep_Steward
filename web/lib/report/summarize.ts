import { db } from "@/lib/db";

export interface RingStage {
  stage: "浅睡" | "深睡" | "快速眼动";
  minutes: number;
}

export interface EnvPoint {
  t: string; // ISO 时间
  tempC: number;
  humidityPct: number;
}

export interface SessionSummary {
  durationMin: number;
  startedAt: string;
  endedAt: string;
  envSeries: EnvPoint[];
  climateAdjustCount: number;
  lightAdjustCount: number;
  humidityAdjustCount: number;
  voiceCount: number;
  ringStages: RingStage[]; // 戒指睡眠分期(模拟数据源,spec 决策)
}

/** 结束睡眠时汇总本次全量数据,写回 session.summaryJson 并返回。 */
export async function summarizeSession(sessionId: string): Promise<SessionSummary> {
  const session = await db.sleepSession.findUnique({
    where: { id: sessionId },
    include: { logs: { orderBy: { timestamp: "asc" } } },
  });
  if (!session) throw new Error("会话不存在");

  const endedAt = session.endedAt ?? new Date();
  const durationMin = Math.max(1, Math.round((endedAt.getTime() - session.startedAt.getTime()) / 60000));

  const envSeries: EnvPoint[] = [];
  let climateAdjustCount = 0;
  let lightAdjustCount = 0;
  let humidityAdjustCount = 0;

  for (const log of session.logs) {
    const payload = JSON.parse(log.payloadJson);
    if (log.type === "env_reading") {
      envSeries.push({
        t: log.timestamp.toISOString(),
        tempC: payload.tempC,
        humidityPct: payload.humidityPct,
      });
    } else if (log.type === "device_trigger") {
      if (payload.kind === "climate") climateAdjustCount++;
      else if (payload.kind === "light") lightAdjustCount++;
      else if (payload.kind === "humidity") humidityAdjustCount++;
    }
  }

  const voiceCount = await db.voiceCommand.count({ where: { sessionId } });

  // 戒指睡眠分期:按时长比例切分(浅睡 50% / 深睡 30% / REM 20%)
  const ringStages: RingStage[] = [
    { stage: "浅睡", minutes: Math.round(durationMin * 0.5) },
    { stage: "深睡", minutes: Math.round(durationMin * 0.3) },
    { stage: "快速眼动", minutes: Math.round(durationMin * 0.2) },
  ];

  const summary: SessionSummary = {
    durationMin,
    startedAt: session.startedAt.toISOString(),
    endedAt: endedAt.toISOString(),
    envSeries,
    climateAdjustCount,
    lightAdjustCount,
    humidityAdjustCount,
    voiceCount,
    ringStages,
  };

  await db.sleepSession.update({
    where: { id: sessionId },
    data: { summaryJson: JSON.stringify(summary) },
  });

  return summary;
}
