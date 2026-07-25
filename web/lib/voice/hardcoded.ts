import type { ParsedCommand } from "@/lib/voice/command";

const COMMANDS: Record<string, ParsedCommand> = {
  关灯: { action: "setLight", params: { on: false, brightness: 0 } },
  开灯: {
    action: "setLight",
    params: { on: true, brightness: 30, colorTemp: "warm" },
  },
  调高温度: { action: "setClimate", params: { deltaC: 1 } },
  调低温度: { action: "setClimate", params: { deltaC: -1 } },
  开夜灯: {
    action: "setLight",
    params: { on: true, brightness: 12, colorTemp: "warm" },
  },
  关夜灯: { action: "setLight", params: { on: false, brightness: 0 } },
};

export function matchHardcoded(text: string): ParsedCommand | null {
  const normalized = text.trim().replace(/[，,。！!？?\s]+/g, "");
  const exact = COMMANDS[normalized];
  if (exact) return exact;

  const commandText = normalized.replace(
    /^(?:请你|请|麻烦你|麻烦)?(?:帮我)?/,
    "",
  );
  if (/^(?:打开|开启|开)(?:一下)?(?:温馨灯|暖灯|暖光)$/.test(commandText)) {
    return {
      action: "setLight",
      params: { on: true, brightness: 18, colorTemp: "warm" },
    };
  }
  if (/^(?:打开|开启|开)(?:一下)?(?:睡眠灯|夜灯)$/.test(commandText)) {
    return {
      action: "setLight",
      params: { on: true, brightness: 12, colorTemp: "warm" },
    };
  }
  return null;
}
