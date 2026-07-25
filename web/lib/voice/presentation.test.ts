import { describe, expect, it } from "vitest";
import { voiceSourceLabel } from "./presentation";

describe("voiceSourceLabel", () => {
  it("labels deterministic local commands", () => {
    expect(voiceSourceLabel({ mode: "hardcoded" })).toBe("本地指令");
  });

  it("labels successful natural-language commands", () => {
    expect(voiceSourceLabel({ mode: "natural" })).toBe("StepFun 智能理解");
  });

  it("prioritizes the model fallback state", () => {
    expect(voiceSourceLabel({ mode: "natural", fallback: true })).toBe("模型未配置或暂不可用");
  });

  it("returns no label for unknown responses", () => {
    expect(voiceSourceLabel({})).toBeNull();
  });
});
