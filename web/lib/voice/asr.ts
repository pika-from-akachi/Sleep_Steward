const STEPFUN_ASR_URL = "https://api.stepfun.com/v1/audio/asr/sse";

export type StepFunAsrErrorCode =
  | "missing_key"
  | "timeout"
  | "invalid_audio"
  | "upstream";

export class StepFunAsrError extends Error {
  constructor(
    public readonly code: StepFunAsrErrorCode,
    message: string,
    options?: ErrorOptions,
  ) {
    super(message, options);
    this.name = "StepFunAsrError";
  }
}

function timeoutMs() {
  const configured = Number(process.env.STEPFUN_ASR_TIMEOUT_MS);
  return Number.isFinite(configured)
    ? Math.min(30_000, Math.max(5_000, configured))
    : 15_000;
}

export function parseStepfunAsrEvents(body: string): string {
  let finalText = "";

  for (const line of body.split(/\r?\n/)) {
    if (!line.startsWith("data:")) continue;
    const raw = line.slice(5).trim();
    if (!raw || raw === "[DONE]") continue;

    let event: unknown;
    try {
      event = JSON.parse(raw);
    } catch {
      continue;
    }
    if (!event || typeof event !== "object") continue;

    const payload = event as Record<string, unknown>;
    if (payload.type === "error") {
      throw new StepFunAsrError(
        "invalid_audio",
        typeof payload.message === "string" ? payload.message : "语音识别失败",
      );
    }
    if (
      payload.type === "transcript.text.done" &&
      typeof payload.text === "string"
    ) {
      finalText = payload.text.trim();
    }
  }

  if (!finalText) {
    throw new StepFunAsrError("invalid_audio", "没有识别到有效语音");
  }
  return finalText;
}

export async function transcribeWithStepfun(audioData: string): Promise<string> {
  const apiKey = process.env.STEPFUN_API_KEY?.trim();
  if (!apiKey) throw new StepFunAsrError("missing_key", "StepFun API Key 未配置");

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs());
  try {
    const response = await fetch(STEPFUN_ASR_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        audio: {
          data: audioData,
          input: {
            transcription: {
              language: "zh",
              model: process.env.STEPFUN_ASR_MODEL || "stepaudio-2.5-asr",
              enable_itn: true,
              hotwords: [
                "睡眠灯",
                "温馨灯",
                "夜灯",
                "关灯",
                "调高温度",
                "调低温度",
              ],
            },
            format: {
              type: "pcm",
              codec: "pcm_s16le",
              rate: 16000,
              bits: 16,
              channel: 1,
            },
          },
        },
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new StepFunAsrError("upstream", `StepFun ASR 返回 ${response.status}`);
    }
    return parseStepfunAsrEvents(await response.text());
  } catch (error) {
    if (error instanceof StepFunAsrError) throw error;
    if (error instanceof Error && error.name === "AbortError") {
      throw new StepFunAsrError("timeout", "语音识别超时", { cause: error });
    }
    throw new StepFunAsrError("upstream", "语音识别服务暂不可用", { cause: error });
  } finally {
    clearTimeout(timer);
  }
}
