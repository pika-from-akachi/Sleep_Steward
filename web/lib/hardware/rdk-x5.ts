import type { AudioCmd, EnvReading, HardwareDriver, LightCmd } from "./driver";

interface RdkX5DriverOptions {
  baseUrl: string;
  fetchFn?: typeof fetch;
  timeoutMs?: number;
}

export class HardwareUnavailableError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "HardwareUnavailableError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function finiteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function parseEnvironment(value: unknown): EnvReading {
  if (
    !isRecord(value) ||
    !finiteNumber(value.tempC) ||
    !finiteNumber(value.humidityPct) ||
    !finiteNumber(value.lightLux) ||
    value.lightSource !== "estimated" ||
    typeof value.stale !== "boolean" ||
    typeof value.sampledAt !== "string"
  ) {
    throw new TypeError("RDK X5 返回了无效的环境数据");
  }

  return {
    tempC: value.tempC,
    humidityPct: value.humidityPct,
    lightLux: value.lightLux,
    lightSource: value.lightSource,
    stale: value.stale,
    sampledAt: value.sampledAt,
  };
}

export class RdkX5Driver implements HardwareDriver {
  private readonly baseUrl: string;
  private readonly fetchFn: typeof fetch;
  private readonly timeoutMs: number;
  private lastReading: EnvReading | null = null;
  private targetTempC: number | null = null;
  private lastAudio: AudioCmd | null = null;

  constructor(options: RdkX5DriverOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.fetchFn = options.fetchFn ?? fetch;
    this.timeoutMs = options.timeoutMs ?? 3_000;
  }

  async readEnvironment(): Promise<EnvReading> {
    try {
      const response = await this.request("/environment");
      const reading = parseEnvironment(await response.json());
      this.lastReading = reading;
      return reading;
    } catch (error) {
      if (this.lastReading) return { ...this.lastReading, stale: true };
      throw new HardwareUnavailableError("RDK X5 环境传感器不可用", { cause: error });
    }
  }

  async setLight(cmd: LightCmd): Promise<void> {
    const brightness = Number.isFinite(cmd.brightness)
      ? Math.min(100, Math.max(0, cmd.brightness))
      : 0;
    await this.request("/light", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        on: cmd.on,
        brightness,
        colorTemp: cmd.colorTemp === "cool" ? "cool" : "warm",
      }),
    });
  }

  async setClimate(cmd: { targetTempC: number }): Promise<void> {
    this.targetTempC = cmd.targetTempC;
  }

  async playAudio(cmd: AudioCmd): Promise<void> {
    this.lastAudio = cmd;
  }

  async health(): Promise<{ ok: boolean; driver: "rdk-x5" }> {
    try {
      const response = await this.request("/health");
      const payload: unknown = await response.json();
      return { ok: isRecord(payload) && payload.ok === true, driver: "rdk-x5" };
    } catch {
      return { ok: false, driver: "rdk-x5" };
    }
  }

  get climateTarget(): number | null {
    return this.targetTempC;
  }

  get audioState(): AudioCmd | null {
    return this.lastAudio;
  }

  private async request(path: string, init: RequestInit = {}): Promise<Response> {
    const response = await this.fetchFn(`${this.baseUrl}${path}`, {
      ...init,
      signal: AbortSignal.timeout(this.timeoutMs),
    });
    if (!response.ok) {
      throw new HardwareUnavailableError(`RDK X5 硬件服务返回 ${response.status}`);
    }
    return response;
  }
}
