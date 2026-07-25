import { describe, it, expect } from "vitest";
import { SimDriver } from "./sim";

describe("SimDriver", () => {
  it("readEnvironment returns current virtual state", async () => {
    const d = new SimDriver();
    const env = await d.readEnvironment();
    expect(env.tempC).toBeGreaterThan(0);
    expect(env.humidityPct).toBeGreaterThan(0);
  });

  it("setClimate moves virtual temperature toward target over reads", async () => {
    const d = new SimDriver();
    d.injectEnv({ tempC: 18 });
    await d.setClimate({ targetTempC: 24 });
    const a = (await d.readEnvironment()).tempC;
    const b = (await d.readEnvironment()).tempC;
    expect(a).toBeGreaterThan(18);
    expect(b).toBeGreaterThan(a);
  });

  it("injectEnv lets demo force a cold room", async () => {
    const d = new SimDriver();
    d.injectEnv({ tempC: 15 });
    expect((await d.readEnvironment()).tempC).toBe(15);
  });

  it("setLight updates lux with brightness mapping", async () => {
    const d = new SimDriver();
    await d.setLight({ on: true, brightness: 30 });
    expect((await d.readEnvironment()).lightLux).toBe(302);
    await d.setLight({ on: false, brightness: 0 });
    expect((await d.readEnvironment()).lightLux).toBe(2);
  });

  it("health reports sim driver", async () => {
    const d = new SimDriver();
    expect(await d.health()).toEqual({ ok: true, driver: "sim" });
  });
});
