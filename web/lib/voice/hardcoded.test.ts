import { describe, expect, it } from "vitest";
import { matchHardcoded } from "@/lib/voice/hardcoded";

describe("matchHardcoded", () => {
  it("关灯立即映射为关闭灯光", () => {
    expect(matchHardcoded("关灯")).toEqual({
      action: "setLight",
      params: { on: false, brightness: 0 },
    });
  });

  it.each([
    ["开灯", "setLight"],
    ["调高温度", "setClimate"],
    ["调低温度", "setClimate"],
    ["开夜灯", "setLight"],
    ["关夜灯", "setLight"],
  ])("%s 命中快捷动作", (text, action) => {
    expect(matchHardcoded(text)?.action).toBe(action);
  });

  it("自然语言不被宽松关键词误命中", () => {
    expect(matchHardcoded("帮我把灯光调柔和一些")).toBeNull();
  });

  it.each([
    "请帮我打开温馨灯",
    "麻烦你帮我开一下暖灯",
    "开启暖光",
  ])("%s 安全映射为低亮暖光", (text) => {
    expect(matchHardcoded(text)).toEqual({
      action: "setLight",
      params: { on: true, brightness: 18, colorTemp: "warm" },
    });
  });

  it("打开睡眠灯映射为更低亮度的暖夜灯", () => {
    expect(matchHardcoded("请打开睡眠灯")).toEqual({
      action: "setLight",
      params: { on: true, brightness: 12, colorTemp: "warm" },
    });
  });
});
