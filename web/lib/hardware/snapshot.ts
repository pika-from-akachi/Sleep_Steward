import type { EnvReading, HardwareDriver, LightCmd } from "./driver";
import { RdkX5Driver } from "./rdk-x5";
import { SimDriver } from "./sim";

export interface HardwareSnapshot {
  env: EnvReading | null;
  health: { ok: boolean; driver: "sim" | "rdk-x5" };
  light: LightCmd | null;
  targetTempC: number | null;
}

async function safeHealth(
  driver: HardwareDriver,
): Promise<HardwareSnapshot["health"]> {
  try {
    return await driver.health();
  } catch {
    return {
      ok: false,
      driver: driver instanceof SimDriver ? "sim" : "rdk-x5",
    };
  }
}

export async function readHardwareSnapshot(
  driver: HardwareDriver,
): Promise<HardwareSnapshot> {
  let env: EnvReading | null = null;
  try {
    env = await driver.readEnvironment();
  } catch {
    env = null;
  }

  if (env === null) {
    return {
      env: null,
      health: {
        ok: false,
        driver: driver instanceof SimDriver ? "sim" : "rdk-x5",
      },
      light: null,
      targetTempC: null,
    };
  }

  return {
    env,
    health: await safeHealth(driver),
    light: driver instanceof SimDriver ? driver.lightState : null,
    targetTempC:
      driver instanceof SimDriver || driver instanceof RdkX5Driver
        ? driver.climateTarget
        : null,
  };
}
