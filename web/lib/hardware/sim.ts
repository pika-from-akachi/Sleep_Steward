import type { AudioCmd, EnvReading, HardwareDriver, LightCmd } from "./driver";

/**
 * 传感器/执行器模拟器。
 * - readEnvironment 每次调用时,温度向 targetTempC 收敛 0.5℃,模拟执行器生效过程
 * - injectEnv 供 demo「造场」:手动把房间调冷/调热/调湿
 * - 灯光亮度按 lux ≈ 2 + brightness*10 映射,与 decideAdjustments 的阈值一致
 */
export class SimDriver implements HardwareDriver {
  private tempC = 25.5;
  private humidityPct = 55;
  private lightLux = 120;
  private targetTempC: number | null = null;
  private light: LightCmd = { on: true, brightness: 12, colorTemp: "warm" };
  private lastAudio: AudioCmd | null = null;

  async readEnvironment(): Promise<EnvReading> {
    if (this.targetTempC !== null && this.tempC !== this.targetTempC) {
      const step = Math.min(0.5, Math.abs(this.targetTempC - this.tempC));
      this.tempC += this.tempC < this.targetTempC ? step : -step;
      this.tempC = Math.round(this.tempC * 100) / 100;
    }
    return { tempC: this.tempC, humidityPct: this.humidityPct, lightLux: this.lightLux };
  }

  async setLight(cmd: LightCmd): Promise<void> {
    this.light = { colorTemp: "warm", ...cmd };
    this.lightLux = cmd.on ? 2 + cmd.brightness * 10 : 2;
  }

  async setClimate(cmd: { targetTempC: number }): Promise<void> {
    this.targetTempC = cmd.targetTempC;
  }

  async playAudio(cmd: AudioCmd): Promise<void> {
    this.lastAudio = cmd;
  }

  async health(): Promise<{ ok: boolean; driver: "sim" }> {
    return { ok: true, driver: "sim" };
  }

  /* ---- demo / 状态查询(非 HardwareDriver 接口)---- */

  injectEnv(partial: Partial<EnvReading>): void {
    if (partial.tempC !== undefined) this.tempC = partial.tempC;
    if (partial.humidityPct !== undefined) this.humidityPct = partial.humidityPct;
    if (partial.lightLux !== undefined) this.lightLux = partial.lightLux;
  }

  get lightState(): LightCmd {
    return { ...this.light };
  }

  get climateTarget(): number | null {
    return this.targetTempC;
  }

  get audioState(): AudioCmd | null {
    return this.lastAudio;
  }
}
