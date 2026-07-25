import type { HardwareDriver } from "@/lib/hardware";

const TRACK_IDS = ["noise", "waves", "bell", "lullaby"] as const;
type TrackId = (typeof TRACK_IDS)[number];

export type ParsedCommand =
  | {
      action: "setLight";
      params: { on: boolean; brightness: number; colorTemp?: "warm" | "cool" };
    }
  | {
      action: "setClimate";
      params: { targetTempC: number } | { deltaC: number };
    }
  | {
      action: "playAudio";
      params: { trackId: TrackId; loop: boolean };
    }
  | {
      action: "stopAudio";
      params: Record<string, never>;
    };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasOnlyKeys(value: Record<string, unknown>, allowed: string[]) {
  return Object.keys(value).every((key) => allowed.includes(key));
}

function finiteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/**
 * LLM 输出属于不可信输入：动作与参数逐项收窄后，才能进入 HAL。
 */
export function validateParsedCommand(value: unknown): ParsedCommand {
  if (!isRecord(value) || !hasOnlyKeys(value, ["action", "params"])) {
    throw new Error("指令结构无效");
  }
  if (!isRecord(value.params)) throw new Error("指令参数无效");
  const params = value.params;

  if (value.action === "setLight") {
    if (!hasOnlyKeys(params, ["on", "brightness", "colorTemp"])) {
      throw new Error("灯光参数无效");
    }
    if (typeof params.on !== "boolean") {
      throw new Error("灯光参数越界");
    }
    const brightness =
      params.brightness === undefined ? (params.on ? 18 : 0) : params.brightness;
    if (!finiteNumber(brightness) || brightness < 0 || brightness > 100) {
      throw new Error("灯光参数越界");
    }
    if (
      params.colorTemp !== undefined &&
      params.colorTemp !== "warm" &&
      params.colorTemp !== "cool"
    ) {
      throw new Error("灯光色温无效");
    }
    return {
      action: "setLight",
      params: {
        on: params.on,
        brightness: Math.round(brightness),
        ...(params.colorTemp ? { colorTemp: params.colorTemp } : {}),
      },
    };
  }

  if (value.action === "setClimate") {
    if (!hasOnlyKeys(params, ["targetTempC", "deltaC"])) {
      throw new Error("温度参数无效");
    }
    if (finiteNumber(params.targetTempC) && params.deltaC === undefined) {
      if (params.targetTempC < 16 || params.targetTempC > 30) {
        throw new Error("目标温度越界");
      }
      return {
        action: "setClimate",
        params: { targetTempC: Math.round(params.targetTempC * 10) / 10 },
      };
    }
    if (finiteNumber(params.deltaC) && params.targetTempC === undefined) {
      if (params.deltaC === 0 || Math.abs(params.deltaC) > 3) {
        throw new Error("温度调整幅度越界");
      }
      return {
        action: "setClimate",
        params: { deltaC: Math.round(params.deltaC * 10) / 10 },
      };
    }
    throw new Error("温度参数无效");
  }

  if (value.action === "playAudio") {
    if (!hasOnlyKeys(params, ["trackId", "loop"])) {
      throw new Error("音频参数无效");
    }
    if (
      typeof params.trackId !== "string" ||
      !TRACK_IDS.includes(params.trackId as TrackId) ||
      typeof params.loop !== "boolean"
    ) {
      throw new Error("音频参数无效");
    }
    return {
      action: "playAudio",
      params: { trackId: params.trackId as TrackId, loop: params.loop },
    };
  }

  if (value.action === "stopAudio") {
    if (Object.keys(params).length > 0) throw new Error("停止音频无需参数");
    return { action: "stopAudio", params: {} };
  }

  throw new Error("动作不在白名单内");
}

export async function executeParsedCommand(
  command: ParsedCommand,
  driver: HardwareDriver,
) {
  if (command.action === "setLight") {
    await driver.setLight(command.params);
    return command.params.on
      ? `灯光已调整至 ${command.params.brightness}%`
      : "灯光已关闭";
  }
  if (command.action === "setClimate") {
    const targetTempC =
      "targetTempC" in command.params
        ? command.params.targetTempC
        : Math.min(
            30,
            Math.max(
              16,
              Math.round(
                ((await driver.readEnvironment()).tempC + command.params.deltaC) * 10,
              ) / 10,
            ),
          );
    await driver.setClimate({ targetTempC });
    return `目标温度已设为 ${targetTempC}℃`;
  }
  if (command.action === "playAudio") {
    await driver.playAudio(command.params);
    return "助眠声音已开始播放";
  }
  await driver.playAudio({ stop: true });
  return "助眠声音已停止";
}
