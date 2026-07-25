import { describe, it, expect } from "vitest";
import { decideAdjustments } from "./decide";

const prefs = { tempMin: 22, tempMax: 25, humidityMin: 40, humidityMax: 60, lightBrightness: 20 };

describe("decideAdjustments", () => {
  it("偏冷时输出升温到区间中值", () => {
    const out = decideAdjustments({ tempC: 18, humidityPct: 50, lightLux: 5 }, prefs);
    const climate = out.find((a) => a.kind === "climate");
    expect(climate?.command).toEqual({ targetTempC: 23.5 });
    expect(climate?.message).toContain("升温");
  });

  it("偏热时输出降温", () => {
    const out = decideAdjustments({ tempC: 28, humidityPct: 50, lightLux: 5 }, prefs);
    expect(out.find((a) => a.kind === "climate")?.message).toContain("降温");
  });

  it("区间内不动作", () => {
    expect(decideAdjustments({ tempC: 23, humidityPct: 50, lightLux: 5 }, prefs)).toHaveLength(0);
  });

  it("滞回:略低于 min(在 0.5℃ 缓冲内)不动作", () => {
    expect(decideAdjustments({ tempC: 21.7, humidityPct: 50, lightLux: 5 }, prefs)).toHaveLength(0);
  });

  it("光照偏亮时调暗", () => {
    const out = decideAdjustments({ tempC: 23, humidityPct: 50, lightLux: 300 }, prefs);
    const light = out.find((a) => a.kind === "light");
    expect(light?.message).toContain("调暗");
    expect(light?.command).toEqual({ brightness: 20 });
  });

  it("湿度越界时输出加湿/除湿", () => {
    const dry = decideAdjustments({ tempC: 23, humidityPct: 30, lightLux: 5 }, prefs);
    expect(dry.find((a) => a.kind === "humidity")?.message).toContain("加湿");
    const wet = decideAdjustments({ tempC: 23, humidityPct: 75, lightLux: 5 }, prefs);
    expect(wet.find((a) => a.kind === "humidity")?.message).toContain("除湿");
  });
});
