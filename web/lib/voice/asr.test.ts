import { afterEach, describe, expect, it, vi } from "vitest";
import {
  parseStepfunAsrEvents,
  StepFunAsrError,
  transcribeWithStepfun,
} from "@/lib/voice/asr";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("parseStepfunAsrEvents", () => {
  it("返回 done 事件中的最终文字", () => {
    const body = [
      'data: {"type":"transcript.text.delta","delta":"请帮我"}',
      "",
      'data: {"type":"transcript.text.done","text":"请帮我打开睡眠灯"}',
      "",
    ].join("\n");

    expect(parseStepfunAsrEvents(body)).toBe("请帮我打开睡眠灯");
  });

  it("将错误事件转换为可识别错误", () => {
    const body = 'data: {"type":"error","message":"bad audio"}\n\n';

    expect(() => parseStepfunAsrEvents(body)).toThrowError(
      expect.objectContaining({ code: "invalid_audio" }),
    );
  });
});

describe("transcribeWithStepfun", () => {
  it("使用 16kHz PCM 调用 StepFun ASR", async () => {
    vi.stubEnv("STEPFUN_API_KEY", "test-key");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        'data: {"type":"transcript.text.done","text":"打开睡眠灯"}\n\n',
        { status: 200, headers: { "Content-Type": "text/event-stream" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(transcribeWithStepfun("AQI=")).resolves.toBe("打开睡眠灯");
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.stepfun.com/v1/audio/asr/sse",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer test-key",
          Accept: "text/event-stream",
        }),
      }),
    );
    const request = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(request.audio.input.format).toEqual({
      type: "pcm",
      codec: "pcm_s16le",
      rate: 16000,
      bits: 16,
      channel: 1,
    });
  });

  it("无 Key 时不发送音频", async () => {
    vi.stubEnv("STEPFUN_API_KEY", "");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(transcribeWithStepfun("AQI=")).rejects.toMatchObject({
      code: "missing_key",
    } satisfies Partial<StepFunAsrError>);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
