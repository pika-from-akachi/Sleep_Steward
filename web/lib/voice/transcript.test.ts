import { describe, expect, it } from "vitest";
import { finalSpeechTranscript, type SpeechRecognitionResultLike } from "./transcript";

function result(transcript: string, isFinal: boolean): SpeechRecognitionResultLike {
  return Object.assign([{ transcript }], { isFinal });
}

describe("finalSpeechTranscript", () => {
  it("joins trimmed final transcript segments", () => {
    expect(
      finalSpeechTranscript([
        result(" 请帮我 ", true),
        result("打开温馨灯 ", true),
      ]),
    ).toBe("请帮我 打开温馨灯");
  });

  it("ignores interim transcript segments", () => {
    expect(
      finalSpeechTranscript([
        result("请帮我打开", false),
        result("请帮我打开温馨灯", true),
      ]),
    ).toBe("请帮我打开温馨灯");
  });

  it("returns an empty string for blank final results", () => {
    expect(finalSpeechTranscript([result("   ", true)])).toBe("");
  });
});
