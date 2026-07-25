import {
  validateParsedCommand,
  type ParsedCommand,
} from "@/lib/voice/command";

export const VOICE_CAPABILITIES = [
  "setLight: params { on:boolean, brightness:0-100, colorTemp?:warm|cool }",
  "setClimate: params { targetTempC:16-30 }",
  "playAudio: params { trackId:noise|waves|bell|lullaby, loop:boolean }",
  "stopAudio: params {}",
] as const;

const DEFAULT_STEPFUN_TIMEOUT_MS = 8_000;

function stepfunTimeoutMs(): number {
  const configured = Number(process.env.STEPFUN_TIMEOUT_MS);
  return Number.isFinite(configured) && configured >= 1_000 && configured <= 30_000
    ? configured
    : DEFAULT_STEPFUN_TIMEOUT_MS;
}

export class StepFunError extends Error {
  constructor(
    public readonly code:
      | "missing_key"
      | "timeout"
      | "upstream"
      | "invalid_response",
    message: string,
  ) {
    super(message);
    this.name = "StepFunError";
  }
}

export async function parseWithStepfun(
  text: string,
  capabilities: readonly string[] = VOICE_CAPABILITIES,
): Promise<ParsedCommand> {
  const apiKey = process.env.STEPFUN_API_KEY;
  if (!apiKey) {
    throw new StepFunError("missing_key", "StepFun API Key 未配置");
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), stepfunTimeoutMs());

  try {
    const response = await fetch("https://api.stepfun.com/v1/chat/completions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      signal: controller.signal,
      body: JSON.stringify({
        model: process.env.STEPFUN_MODEL || "step-3.5-flash",
        temperature: 0,
        response_format: { type: "json_object" },
        messages: [
          {
            role: "system",
            content: [
              "你是卧室设备指令翻译器。",
              "只输出 JSON 对象 {\"action\":\"...\",\"params\":{...}}。",
              "action 与参数必须严格从以下服务端能力中选择，不得创造新动作：",
              ...capabilities,
              "setLight 开灯必须给 brightness；柔和、温馨或夜间场景使用 18，普通开灯使用 30，关灯使用 0。",
              "无法确定时也不要解释，只输出最接近且安全的动作。",
            ].join("\n"),
          },
          { role: "user", content: text },
        ],
      }),
    });

    if (!response.ok) {
      throw new StepFunError("upstream", `StepFun 返回 ${response.status}`);
    }

    const payload = (await response.json()) as {
      choices?: Array<{ message?: { content?: string } }>;
    };
    const content = payload.choices?.[0]?.message?.content;
    if (!content) throw new StepFunError("invalid_response", "StepFun 返回内容为空");

    try {
      return validateParsedCommand(JSON.parse(content));
    } catch (error) {
      if (error instanceof StepFunError) throw error;
      throw new StepFunError("invalid_response", "StepFun 返回了无效指令");
    }
  } catch (error) {
    if (error instanceof StepFunError) throw error;
    if (
      error instanceof DOMException
        ? error.name === "AbortError"
        : error instanceof Error && error.name === "AbortError"
    ) {
      throw new StepFunError("timeout", "StepFun 请求超时");
    }
    throw new StepFunError("upstream", "StepFun 请求失败");
  } finally {
    clearTimeout(timeout);
  }
}
