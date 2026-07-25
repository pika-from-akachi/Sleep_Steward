import "dotenv/config";
import { PrismaClient } from "@prisma/client";

const db = new PrismaClient();

type UserType = "adult" | "child";

interface UserSeed {
  stableId: string;
  nickname: string;
  userType: UserType;
  childAge: number | null;
}

interface PrefSeed {
  stableId: string;
  name: string;
  tempMin: number;
  tempMax: number;
  humidityMin: number;
  humidityMax: number;
  lightBrightness: number;
  lightColorTemp: "warm" | "cool";
  isDefault: boolean;
}

interface EnvPoint {
  offsetMin: number;
  tempC: number;
  humidityPct: number;
  lightLux: number;
}

interface TriggerPoint {
  offsetMin: number;
  kind: "climate" | "light" | "humidity";
  command: Record<string, unknown>;
  message: string;
}

interface VoicePoint {
  offsetMin: number;
  rawText: string;
  mode: "hardcoded" | "natural";
  parsed: Record<string, unknown>;
  matchedDevice: "setLight" | "setClimate" | "playAudio" | "stopAudio";
}

interface SessionSeed {
  stableId: string;
  daysAgo: number;
  startHour: number;
  startMinute: number;
  durationMin: number;
  env: EnvPoint[];
  triggers: TriggerPoint[];
  voices: VoicePoint[];
}

function localDate(daysAgo: number, hour: number, minute: number) {
  const now = new Date();
  return new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate() - daysAgo,
    hour,
    minute,
    0,
    0,
  );
}

function plusMinutes(date: Date, minutes: number) {
  return new Date(date.getTime() + minutes * 60_000);
}

async function ensureUser(seed: UserSeed) {
  const existing = await db.user.findFirst({
    where: {
      nickname: seed.nickname,
      userType: seed.userType,
      childAge: seed.childAge,
    },
    orderBy: { createdAt: "asc" },
  });

  if (existing) return existing;

  return db.user.upsert({
    where: { id: seed.stableId },
    update: {
      nickname: seed.nickname,
      userType: seed.userType,
      childAge: seed.childAge,
    },
    create: {
      id: seed.stableId,
      nickname: seed.nickname,
      userType: seed.userType,
      childAge: seed.childAge,
    },
  });
}

async function ensurePref(userId: string, seed: PrefSeed) {
  const existing = await db.preferenceProfile.findFirst({
    where: { userId, name: seed.name },
    orderBy: { createdAt: "asc" },
  });
  const data = {
    userId,
    name: seed.name,
    tempMin: seed.tempMin,
    tempMax: seed.tempMax,
    humidityMin: seed.humidityMin,
    humidityMax: seed.humidityMax,
    lightBrightness: seed.lightBrightness,
    lightColorTemp: seed.lightColorTemp,
    isDefault: seed.isDefault,
  };

  if (existing) {
    return db.preferenceProfile.update({
      where: { id: existing.id },
      data,
    });
  }

  return db.preferenceProfile.upsert({
    where: { id: seed.stableId },
    update: data,
    create: { id: seed.stableId, ...data },
  });
}

async function seedSession(
  userId: string,
  profileId: string,
  seed: SessionSeed,
) {
  const startedAt = localDate(
    seed.daysAgo,
    seed.startHour,
    seed.startMinute,
  );
  const endedAt = plusMinutes(startedAt, seed.durationMin);

  await db.sleepSession.upsert({
    where: { id: seed.stableId },
    update: {
      userId,
      profileId,
      startedAt,
      endedAt,
      status: "ended",
      summaryJson: null,
    },
    create: {
      id: seed.stableId,
      userId,
      profileId,
      startedAt,
      endedAt,
      status: "ended",
    },
  });

  for (const [index, point] of seed.env.entries()) {
    const id = `${seed.stableId}-env-${index + 1}`;
    const timestamp = plusMinutes(startedAt, point.offsetMin);
    const payloadJson = JSON.stringify({
      tempC: point.tempC,
      humidityPct: point.humidityPct,
      lightLux: point.lightLux,
    });
    await db.sessionLog.upsert({
      where: { id },
      update: { sessionId: seed.stableId, timestamp, type: "env_reading", payloadJson },
      create: { id, sessionId: seed.stableId, timestamp, type: "env_reading", payloadJson },
    });
  }

  for (const [index, point] of seed.triggers.entries()) {
    const id = `${seed.stableId}-trigger-${index + 1}`;
    const timestamp = plusMinutes(startedAt, point.offsetMin);
    const payloadJson = JSON.stringify({
      kind: point.kind,
      command: point.command,
      message: point.message,
    });
    await db.sessionLog.upsert({
      where: { id },
      update: { sessionId: seed.stableId, timestamp, type: "device_trigger", payloadJson },
      create: { id, sessionId: seed.stableId, timestamp, type: "device_trigger", payloadJson },
    });
  }

  for (const [index, point] of seed.voices.entries()) {
    const id = `${seed.stableId}-voice-${index + 1}`;
    const createdAt = plusMinutes(startedAt, point.offsetMin);
    const data = {
      userId,
      sessionId: seed.stableId,
      rawText: point.rawText,
      mode: point.mode,
      parsedJson: JSON.stringify(point.parsed),
      matchedDevice: point.matchedDevice,
      createdAt,
    };
    await db.voiceCommand.upsert({
      where: { id },
      update: data,
      create: { id, ...data },
    });
  }
}

const adultSessions: SessionSeed[] = [
  {
    stableId: "demo-adult-session-1",
    daysAgo: 1,
    startHour: 23,
    startMinute: 5,
    durationMin: 460,
    env: [
      { offsetMin: 0, tempC: 26.4, humidityPct: 38, lightLux: 420 },
      { offsetMin: 8, tempC: 25.8, humidityPct: 41, lightLux: 35 },
      { offsetMin: 70, tempC: 24.8, humidityPct: 46, lightLux: 18 },
      { offsetMin: 230, tempC: 23.9, humidityPct: 50, lightLux: 10 },
      { offsetMin: 450, tempC: 24.1, humidityPct: 49, lightLux: 24 },
    ],
    triggers: [
      {
        offsetMin: 2,
        kind: "climate",
        command: { targetTempC: 23.5 },
        message: "检测到偏热，已降温至 23.5℃",
      },
      {
        offsetMin: 3,
        kind: "light",
        command: { on: true, brightness: 15, colorTemp: "warm" },
        message: "光线偏亮，已调暗灯光",
      },
      {
        offsetMin: 5,
        kind: "humidity",
        command: { targetHumidityPct: 50 },
        message: "空气偏干，已调整湿度",
      },
    ],
    voices: [
      {
        offsetMin: 4,
        rawText: "关灯",
        mode: "hardcoded",
        parsed: { action: "setLight", params: { on: false, brightness: 0 } },
        matchedDevice: "setLight",
      },
    ],
  },
  {
    stableId: "demo-adult-session-2",
    daysAgo: 4,
    startHour: 22,
    startMinute: 48,
    durationMin: 432,
    env: [
      { offsetMin: 0, tempC: 21.2, humidityPct: 52, lightLux: 160 },
      { offsetMin: 12, tempC: 22.1, humidityPct: 51, lightLux: 24 },
      { offsetMin: 90, tempC: 23.2, humidityPct: 50, lightLux: 12 },
      { offsetMin: 250, tempC: 23.5, humidityPct: 49, lightLux: 8 },
      { offsetMin: 420, tempC: 23.4, humidityPct: 50, lightLux: 20 },
    ],
    triggers: [
      {
        offsetMin: 2,
        kind: "climate",
        command: { targetTempC: 23.5 },
        message: "检测到偏冷，已升温至 23.5℃",
      },
      {
        offsetMin: 4,
        kind: "light",
        command: { on: true, brightness: 12, colorTemp: "warm" },
        message: "已将灯光调至入睡亮度",
      },
    ],
    voices: [
      {
        offsetMin: 18,
        rawText: "把房间调暖一点",
        mode: "natural",
        parsed: { action: "setClimate", params: { targetTempC: 24 } },
        matchedDevice: "setClimate",
      },
    ],
  },
  {
    stableId: "demo-adult-session-3",
    daysAgo: 9,
    startHour: 23,
    startMinute: 18,
    durationMin: 405,
    env: [
      { offsetMin: 0, tempC: 24.8, humidityPct: 64, lightLux: 90 },
      { offsetMin: 25, tempC: 24.3, humidityPct: 59, lightLux: 16 },
      { offsetMin: 120, tempC: 23.8, humidityPct: 55, lightLux: 9 },
      { offsetMin: 260, tempC: 23.6, humidityPct: 53, lightLux: 8 },
      { offsetMin: 396, tempC: 23.7, humidityPct: 52, lightLux: 18 },
    ],
    triggers: [
      {
        offsetMin: 3,
        kind: "humidity",
        command: { targetHumidityPct: 52 },
        message: "湿度偏高，已开始调节",
      },
    ],
    voices: [],
  },
];

const childSessions: SessionSeed[] = [
  {
    stableId: "demo-child-session-1",
    daysAgo: 1,
    startHour: 20,
    startMinute: 45,
    durationMin: 610,
    env: [
      { offsetMin: 0, tempC: 27.1, humidityPct: 41, lightLux: 260 },
      { offsetMin: 10, tempC: 26.2, humidityPct: 45, lightLux: 42 },
      { offsetMin: 100, tempC: 25.2, humidityPct: 50, lightLux: 18 },
      { offsetMin: 320, tempC: 24.9, humidityPct: 52, lightLux: 12 },
      { offsetMin: 600, tempC: 25.0, humidityPct: 52, lightLux: 22 },
    ],
    triggers: [
      {
        offsetMin: 2,
        kind: "climate",
        command: { targetTempC: 25 },
        message: "检测到偏热，已降温至 25℃",
      },
      {
        offsetMin: 3,
        kind: "light",
        command: { on: true, brightness: 8, colorTemp: "warm" },
        message: "已把灯光调成柔和夜灯",
      },
      {
        offsetMin: 5,
        kind: "humidity",
        command: { targetHumidityPct: 52 },
        message: "空气偏干，已调整湿度",
      },
    ],
    voices: [
      {
        offsetMin: 4,
        rawText: "开夜灯",
        mode: "hardcoded",
        parsed: {
          action: "setLight",
          params: { on: true, brightness: 12, colorTemp: "warm" },
        },
        matchedDevice: "setLight",
      },
    ],
  },
  {
    stableId: "demo-child-session-2",
    daysAgo: 5,
    startHour: 13,
    startMinute: 10,
    durationMin: 92,
    env: [
      { offsetMin: 0, tempC: 26.8, humidityPct: 47, lightLux: 310 },
      { offsetMin: 5, tempC: 26.2, humidityPct: 48, lightLux: 82 },
      { offsetMin: 30, tempC: 25.6, humidityPct: 50, lightLux: 32 },
      { offsetMin: 60, tempC: 25.2, humidityPct: 51, lightLux: 28 },
      { offsetMin: 88, tempC: 25.4, humidityPct: 50, lightLux: 46 },
    ],
    triggers: [
      {
        offsetMin: 2,
        kind: "light",
        command: { on: true, brightness: 25, colorTemp: "warm" },
        message: "午后光线偏亮，已拉低灯光",
      },
    ],
    voices: [
      {
        offsetMin: 7,
        rawText: "播放轻柔一点的声音",
        mode: "natural",
        parsed: { action: "playAudio", params: { trackId: "lullaby", loop: true } },
        matchedDevice: "playAudio",
      },
    ],
  },
  {
    stableId: "demo-child-session-3",
    daysAgo: 10,
    startHour: 21,
    startMinute: 2,
    durationMin: 575,
    env: [
      { offsetMin: 0, tempC: 23.5, humidityPct: 44, lightLux: 120 },
      { offsetMin: 8, tempC: 24.1, humidityPct: 47, lightLux: 26 },
      { offsetMin: 90, tempC: 24.8, humidityPct: 50, lightLux: 14 },
      { offsetMin: 300, tempC: 25.1, humidityPct: 51, lightLux: 10 },
      { offsetMin: 565, tempC: 25.0, humidityPct: 50, lightLux: 20 },
    ],
    triggers: [
      {
        offsetMin: 2,
        kind: "climate",
        command: { targetTempC: 25 },
        message: "检测到偏冷，已升温至 25℃",
      },
      {
        offsetMin: 3,
        kind: "light",
        command: { on: true, brightness: 8, colorTemp: "warm" },
        message: "已把灯光调至夜间亮度",
      },
    ],
    voices: [],
  },
];

async function main() {
  const adult = await ensureUser({
    stableId: "demo-adult-xiaoming",
    nickname: "小明",
    userType: "adult",
    childAge: null,
  });
  const child = await ensureUser({
    stableId: "demo-child-lele",
    nickname: "乐乐",
    userType: "child",
    childAge: 3,
  });

  const adultDefault = await ensurePref(adult.id, {
    stableId: "demo-adult-default",
    name: "标准助眠",
    tempMin: 22,
    tempMax: 25,
    humidityMin: 40,
    humidityMax: 60,
    lightBrightness: 20,
    lightColorTemp: "warm",
    isDefault: true,
  });
  await ensurePref(adult.id, {
    stableId: "demo-adult-summer",
    name: "夏季低温模式",
    tempMin: 20,
    tempMax: 23,
    humidityMin: 40,
    humidityMax: 55,
    lightBrightness: 15,
    lightColorTemp: "cool",
    isDefault: false,
  });

  const childDefault = await ensurePref(child.id, {
    stableId: "demo-child-default",
    name: "宝宝舒睡",
    tempMin: 24,
    tempMax: 26,
    humidityMin: 45,
    humidityMax: 60,
    lightBrightness: 15,
    lightColorTemp: "warm",
    isDefault: true,
  });
  await ensurePref(child.id, {
    stableId: "demo-child-night",
    name: "夜间安睡",
    tempMin: 23,
    tempMax: 25,
    humidityMin: 45,
    humidityMax: 60,
    lightBrightness: 8,
    lightColorTemp: "warm",
    isDefault: false,
  });

  for (const session of adultSessions) {
    await seedSession(adult.id, adultDefault.id, session);
  }
  for (const session of childSessions) {
    await seedSession(child.id, childDefault.id, session);
  }

  console.log("样板数据已就绪：成人模式输入“小明”；儿童模式输入“乐乐”、年龄 3。");
}

main()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await db.$disconnect();
  });
