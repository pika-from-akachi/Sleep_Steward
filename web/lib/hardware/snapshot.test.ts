import { describe, expect, it } from "vitest";
import { RdkX5Driver } from "./rdk-x5";
import { readHardwareSnapshot } from "./snapshot";

describe("readHardwareSnapshot", () => {
  it("returns a stable empty environment when real hardware is cold-start offline", async () => {
    let requests = 0;
    const driver = new RdkX5Driver({
      baseUrl: "http://rdk:8765",
      fetchFn: (async () => {
        requests++;
        throw new TypeError("offline");
      }) as typeof fetch,
    });

    await expect(readHardwareSnapshot(driver)).resolves.toEqual({
      env: null,
      health: { ok: false, driver: "rdk-x5" },
      light: null,
      targetTempC: null,
    });
    expect(requests).toBe(1);
  });

  it("keeps an estimated stale reading visible with unhealthy hardware status", async () => {
    let environmentCalls = 0;
    const driver = new RdkX5Driver({
      baseUrl: "http://rdk:8765",
      fetchFn: (async (input: RequestInfo | URL) => {
        const path = String(input);
        if (path.endsWith("/health")) return Response.json({ ok: false });
        environmentCalls++;
        if (environmentCalls > 1) throw new TypeError("offline");
        return Response.json({
          tempC: 26.2,
          humidityPct: 63.5,
          lightLux: 122,
          lightSource: "estimated",
          stale: false,
          sampledAt: "2026-07-25T00:00:00Z",
        });
      }) as typeof fetch,
    });
    await readHardwareSnapshot(driver);

    const snapshot = await readHardwareSnapshot(driver);

    expect(snapshot.env).toMatchObject({ tempC: 26.2, stale: true });
    expect(snapshot.health).toEqual({ ok: false, driver: "rdk-x5" });
  });
});
