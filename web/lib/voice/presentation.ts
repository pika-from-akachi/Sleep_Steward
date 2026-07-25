interface VoiceResponsePresentation {
  mode?: unknown;
  fallback?: unknown;
}

export function voiceSourceLabel(response: VoiceResponsePresentation): string | null {
  if (response.fallback === true) return "模型未配置或暂不可用";
  if (response.mode === "hardcoded") return "本地指令";
  if (response.mode === "natural") return "StepFun 智能理解";
  return null;
}
