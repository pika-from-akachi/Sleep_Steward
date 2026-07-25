import type { HardwareDriver } from "./driver";
import { RdkX5Driver } from "./rdk-x5";
import { SimDriver } from "./sim";

const g = globalThis as unknown as { __hardwareDriver?: HardwareDriver };

interface HardwareEnvironment {
  HARDWARE_DRIVER?: string;
  RDK_X5_AGENT_URL?: string;
}

/** 进程内单例(globalThis 缓存,避免 dev 热重载产生多个模拟器实例)。 */
export function getDriver(): HardwareDriver {
  if (!g.__hardwareDriver) g.__hardwareDriver = createDriver();
  return g.__hardwareDriver;
}

export function createDriver(
  env: HardwareEnvironment = {
    HARDWARE_DRIVER: process.env.HARDWARE_DRIVER,
    RDK_X5_AGENT_URL: process.env.RDK_X5_AGENT_URL,
  },
): HardwareDriver {
  if (env.HARDWARE_DRIVER !== "rdk-x5") return new SimDriver();
  if (!env.RDK_X5_AGENT_URL) {
    throw new Error("RDK_X5_AGENT_URL is required when HARDWARE_DRIVER=rdk-x5");
  }
  return new RdkX5Driver({ baseUrl: env.RDK_X5_AGENT_URL });
}

export { RdkX5Driver, SimDriver };
export type { HardwareDriver, EnvReading, LightCmd } from "./driver";
