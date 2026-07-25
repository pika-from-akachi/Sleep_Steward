import { describe, expect, it, vi } from "vitest";
import { HardwareUnavailableError, RdkX5Driver } from "./rdk-x5";

const AGENT_READING = {
  tempC: 26.2,
  humidityPct: 63.5,
  lightLux: 122,
  lightSource: "estimated",
  stale: false,
  sampledAt: "2026-07-25T00:00:00Z",
};

function fakeFetch(
  implementation: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>,
): typeof fetch {
  return implementation as typeof fetch;
}

describe("RdkX5Driver", () => {
  it("maps a complete environment response from the board agent", async () => {
    const driver = new RdkX5Driver({
      baseUrl: "http://rdk:8765/",
      fetchFn: fakeFetch(async () => Response.json(AGENT_READING)),
    });

    await expect(driver.readEnvironment()).resolves.toEqual(AGENT_READING);
  });

  it("normalizes a light command before sending it to the board", async () => {
    let receivedUrl = "";
    let receivedInit: RequestInit | undefined;
    const driver = new RdkX5Driver({
      baseUrl: "http://rdk:8765",
      fetchFn: fakeFetch(async (url, init) => {
        receivedUrl = String(url);
        receivedInit = init;
        return Response.json({ ok: true });
      }),
    });

    await driver.setLight({ on: true, brightness: 120, colorTemp: "warm" });

    expect(receivedUrl).toBe("http://rdk:8765/light");
    expect(receivedInit?.method).toBe("POST");
    expect(JSON.parse(String(receivedInit?.body))).toEqual({
      on: true,
      brightness: 100,
      colorTemp: "warm",
    });
  });

  it("returns the last valid reading as stale after a transient failure", async () => {
    let offline = false;
    const driver = new RdkX5Driver({
      baseUrl: "http://rdk:8765",
      fetchFn: fakeFetch(async () => {
        if (offline) throw new TypeError("offline");
        return Response.json(AGENT_READING);
      }),
    });
    await driver.readEnvironment();
    offline = true;

    await expect(driver.readEnvironment()).resolves.toEqual({
      ...AGENT_READING,
      stale: true,
    });
  });

  it("throws a typed error when hardware is unavailable before any valid reading", async () => {
    const driver = new RdkX5Driver({
      baseUrl: "http://rdk:8765",
      fetchFn: fakeFetch(async () => {
        throw new TypeError("offline");
      }),
    });

    await expect(driver.readEnvironment()).rejects.toBeInstanceOf(HardwareUnavailableError);
  });

  it("rejects malformed sensor payloads instead of presenting them as real data", async () => {
    const driver = new RdkX5Driver({
      baseUrl: "http://rdk:8765",
      fetchFn: fakeFetch(async () => Response.json({ ...AGENT_READING, tempC: "hot" })),
    });

    await expect(driver.readEnvironment()).rejects.toBeInstanceOf(HardwareUnavailableError);
  });

  it("reports the real driver as offline when the health endpoint fails", async () => {
    const driver = new RdkX5Driver({
      baseUrl: "http://rdk:8765",
      fetchFn: fakeFetch(async () => {
        throw new TypeError("offline");
      }),
    });

    await expect(driver.health()).resolves.toEqual({ ok: false, driver: "rdk-x5" });
  });

  it("honors an unhealthy response from the board agent", async () => {
    const driver = new RdkX5Driver({
      baseUrl: "http://rdk:8765",
      fetchFn: fakeFetch(async () => Response.json({ ok: false, sensorOk: false })),
    });

    await expect(driver.health()).resolves.toEqual({ ok: false, driver: "rdk-x5" });
  });

  it("does not call the board for unsupported climate and audio compatibility state", async () => {
    const fetchFn = vi.fn(async () => Response.json({ ok: true }));
    const driver = new RdkX5Driver({
      baseUrl: "http://rdk:8765",
      fetchFn: fetchFn as unknown as typeof fetch,
    });

    await driver.setClimate({ targetTempC: 24 });
    await driver.playAudio({ trackId: "noise", loop: true });

    expect(driver.climateTarget).toBe(24);
    expect(driver.audioState).toEqual({ trackId: "noise", loop: true });
    expect(fetchFn).not.toHaveBeenCalled();
  });
});
