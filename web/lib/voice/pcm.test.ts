import { describe, expect, it } from "vitest";
import { downsampleTo16Khz, floatSamplesToPcm16 } from "@/lib/voice/pcm";

describe("downsampleTo16Khz", () => {
  it("将 48kHz 单声道按区间平均为 16kHz", () => {
    const samples = new Float32Array([0, 0.3, 0.6, -0.6, -0.3, 0]);

    expect(Array.from(downsampleTo16Khz(samples, 48000))).toEqual([
      expect.closeTo(0.3),
      expect.closeTo(-0.3),
    ]);
  });
});

describe("floatSamplesToPcm16", () => {
  it("限制幅度并编码为小端有符号 PCM", () => {
    const bytes = floatSamplesToPcm16(new Float32Array([-2, 0, 2]));
    const view = new DataView(bytes.buffer);

    expect(view.getInt16(0, true)).toBe(-32768);
    expect(view.getInt16(2, true)).toBe(0);
    expect(view.getInt16(4, true)).toBe(32767);
  });
});
