import { afterEach, describe, expect, it, vi } from "vitest";
import { parseWithStepfun, StepFunError } from "@/lib/voice/stepfun";
import { validateParsedCommand } from "@/lib/voice/command";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("validateParsedCommand", () => {
  it("接受白名单内的合法动作", () => {
    expect(
      validateParsedCommand({
        action: "setClimate",
        params: { targetTempC: 24 },
      }),
    ).toEqual({ action: "setClimate", params: { targetTempC: 24 } });
  });

  it("拒绝非白名单动作和越界参数", () => {
    expect(() =>
      validateParsedCommand({ action: "openCurtain", params: {} }),
    ).toThrow("白名单");
    expect(() =>
      validateParsedCommand({
        action: "setClimate",
        params: { targetTempC: 80 },
      }),
    ).toThrow("越界");
  });

  it("灯光模型结果缺少亮度时使用安全默认值", () => {
    expect(
      validateParsedCommand({
        action: "setLight",
        params: { on: true, colorTemp: "warm" },
      }),
    ).toEqual({
      action: "setLight",
      params: { on: true, brightness: 18, colorTemp: "warm" },
    });
    expect(
      validateParsedCommand({ action: "setLight", params: { on: false } }),
    ).toEqual({
      action: "setLight",
      params: { on: false, brightness: 0 },
    });
  });
});

describe("parseWithStepfun", () => {
  it("无 Key 时直接降级且不发起请求", async () => {
    vi.stubEnv("STEPFUN_API_KEY", "");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(parseWithStepfun("灯光柔和一点")).rejects.toMatchObject({
      code: "missing_key",
    } satisfies Partial<StepFunError>);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("解析并校验合法 JSON", async () => {
    vi.stubEnv("STEPFUN_API_KEY", "test-key");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            choices: [
              {
                message: {
                  content: JSON.stringify({
                    action: "setLight",
                    params: { on: true, brightness: 18, colorTemp: "warm" },
                  }),
                },
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await expect(parseWithStepfun("留一点暖光")).resolves.toEqual({
      action: "setLight",
      params: { on: true, brightness: 18, colorTemp: "warm" },
    });
  });

  it("超时后返回可识别错误", async () => {
    vi.useFakeTimers();
    vi.stubEnv("STEPFUN_API_KEY", "test-key");
    let aborted = false;
    vi.stubGlobal(
      "fetch",
      vi.fn((_url, init?: RequestInit) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            aborted = true;
            const error = new Error("aborted");
            error.name = "AbortError";
            reject(error);
          });
        }),
      ),
    );

    const outcome = parseWithStepfun("把环境调舒服一点").catch((error) => error);
    await vi.advanceTimersByTimeAsync(7_999);
    expect(aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    await expect(outcome).resolves.toMatchObject({
      code: "timeout",
    } satisfies Partial<StepFunError>);
  });
});
