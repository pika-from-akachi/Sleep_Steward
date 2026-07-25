import { describe, expect, it } from "vitest";
import {
  getMetricSlots,
  metricProgress,
  readMetric,
  type GaugeEnvironment,
} from "./environment-metrics";

const LIVE_ENV: GaugeEnvironment = {
  tempC: 26.9,
  humidityPct: 65.2,
  lightLux: 2,
};

describe("environment metrics", () => {
  it("keeps the active metric centered and the remaining metrics ordered", () => {
    expect(getMetricSlots("temp")).toEqual({
      left: "humidity",
      center: "temp",
      right: "light",
    });
    expect(getMetricSlots("humidity")).toEqual({
      left: "temp",
      center: "humidity",
      right: "light",
    });
    expect(getMetricSlots("light")).toEqual({
      left: "temp",
      center: "light",
      right: "humidity",
    });
  });

  it("formats each live reading independently", () => {
    expect(readMetric("temp", LIVE_ENV)).toBe("26.9");
    expect(readMetric("humidity", LIVE_ENV)).toBe("65");
    expect(readMetric("light", LIVE_ENV)).toBe("2");
  });

  it("uses a stable placeholder when hardware has no reading", () => {
    expect(readMetric("temp", null)).toBe("--");
    expect(readMetric("humidity", null)).toBe("--");
    expect(readMetric("light", null)).toBe("--");
  });

  it("clamps progress to the metric display range", () => {
    expect(metricProgress("humidity", 55)).toBeCloseTo(0.5);
    expect(metricProgress("temp", -20)).toBe(0);
    expect(metricProgress("light", 900)).toBe(1);
    expect(metricProgress("light", null)).toBe(0);
  });
});
