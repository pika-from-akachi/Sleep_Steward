import { describe, expect, it } from "vitest";
import { createDriver, RdkX5Driver, SimDriver } from "./index";

describe("createDriver", () => {
  it("selects the RDK X5 driver only when explicitly configured", () => {
    const driver = createDriver({
      HARDWARE_DRIVER: "rdk-x5",
      RDK_X5_AGENT_URL: "http://192.168.128.10:8765",
    });

    expect(driver).toBeInstanceOf(RdkX5Driver);
  });

  it("keeps the simulator as the safe default", () => {
    expect(createDriver({})).toBeInstanceOf(SimDriver);
  });

  it("rejects real-hardware mode without an agent URL", () => {
    expect(() => createDriver({ HARDWARE_DRIVER: "rdk-x5" })).toThrow(
      "RDK_X5_AGENT_URL",
    );
  });
});
