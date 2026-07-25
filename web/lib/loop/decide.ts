import type { EnvReading } from "@/lib/hardware/driver";

export interface Thresholds {
  tempMin: number;
  tempMax: number;
  humidityMin: number;
  humidityMax: number;
  lightBrightness: number; // 0-100,期望的灯光亮度
}

export interface Adjustment {
  kind: "climate" | "light" | "humidity";
  command: Record<string, number | boolean | string>;
  message: string;
}

/** 滞回缓冲:略过区间边界的小波动,避免执行器反复横跳 */
const HYSTERESIS_C = 0.5;
/** 灯光亮度 → 环境照度映射(与 SimDriver 一致):lux ≈ 2 + brightness*10 */
const LUX_PER_BRIGHTNESS = 10;
/** 照度超出期望值的容忍量 */
const LUX_TOLERANCE = 50;

/**
 * 主动式闭环的判断核心:纯函数,读环境 + 偏好阈值,输出要执行的调节动作。
 * 不碰硬件、不碰数据库,便于测试。
 */
export function decideAdjustments(env: EnvReading, prefs: Thresholds): Adjustment[] {
  const out: Adjustment[] = [];
  const midTemp = Math.round(((prefs.tempMin + prefs.tempMax) / 2) * 10) / 10;

  if (env.tempC < prefs.tempMin - HYSTERESIS_C) {
    out.push({
      kind: "climate",
      command: { targetTempC: midTemp },
      message: `检测到偏冷,已升温至 ${midTemp}℃`,
    });
  } else if (env.tempC > prefs.tempMax + HYSTERESIS_C) {
    out.push({
      kind: "climate",
      command: { targetTempC: midTemp },
      message: `检测到偏热,已降温至 ${midTemp}℃`,
    });
  }

  const midHumidity = Math.round((prefs.humidityMin + prefs.humidityMax) / 2);
  if (env.humidityPct < prefs.humidityMin) {
    out.push({
      kind: "humidity",
      command: { targetHumidityPct: midHumidity },
      message: `空气偏干,已开启加湿至 ${midHumidity}%`,
    });
  } else if (env.humidityPct > prefs.humidityMax) {
    out.push({
      kind: "humidity",
      command: { targetHumidityPct: midHumidity },
      message: `湿度偏高,已开启除湿至 ${midHumidity}%`,
    });
  }

  const luxLimit = 2 + prefs.lightBrightness * LUX_PER_BRIGHTNESS + LUX_TOLERANCE;
  if (env.lightLux > luxLimit) {
    out.push({
      kind: "light",
      command: { brightness: prefs.lightBrightness },
      message: `光照偏亮,已调暗至 ${prefs.lightBrightness}%`,
    });
  }

  return out;
}
