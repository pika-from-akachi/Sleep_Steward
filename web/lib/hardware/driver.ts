export interface EnvReading {
  tempC: number;
  humidityPct: number;
  lightLux: number;
  stale?: boolean;
  lightSource?: "measured" | "estimated" | "simulated";
  sampledAt?: string;
}

export interface LightCmd {
  on: boolean;
  brightness: number; // 0-100
  colorTemp?: "warm" | "cool";
}

export type AudioCmd = { trackId: string; loop: boolean } | { stop: true };

/**
 * 硬件抽象层。业务代码只依赖这个接口。
 * 现在:SimDriver(模拟器)。
 * 以后:RdkX5Driver —— RDK X5 上跑一个小 Python 守护进程
 * (Hobot.GPIO / I²C 读 SHT3x / PWM 调灯),本接口经 HTTP 调它,上层零改动。
 */
export interface HardwareDriver {
  readEnvironment(): Promise<EnvReading>;
  setLight(cmd: LightCmd): Promise<void>;
  setClimate(cmd: { targetTempC: number }): Promise<void>;
  playAudio(cmd: AudioCmd): Promise<void>;
  health(): Promise<{ ok: boolean; driver: "sim" | "rdk-x5" }>;
}
