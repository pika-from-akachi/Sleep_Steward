import { NextResponse } from "next/server";
import { getUserId } from "@/lib/session-cookie";
import { StepFunAsrError, transcribeWithStepfun } from "@/lib/voice/asr";

const MAX_BASE64_LENGTH = 800_000;

export async function POST(req: Request) {
  const uid = await getUserId();
  if (!uid) return NextResponse.json({ error: "未登录" }, { status: 401 });

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  const audioData = typeof body.audioData === "string" ? body.audioData : "";
  if (
    !audioData ||
    audioData.length > MAX_BASE64_LENGTH ||
    !/^[A-Za-z0-9+/=]+$/.test(audioData)
  ) {
    return NextResponse.json({ error: "录音数据无效" }, { status: 400 });
  }

  try {
    const transcript = await transcribeWithStepfun(audioData);
    return NextResponse.json({ transcript });
  } catch (error) {
    const code = error instanceof StepFunAsrError ? error.code : "upstream";
    const message =
      code === "missing_key"
        ? "语音模型尚未配置"
        : code === "invalid_audio"
          ? "没有听清，请靠近一点再说"
          : code === "timeout"
            ? "语音识别超时，请再试一次"
            : "语音识别暂不可用";
    return NextResponse.json({ error: message, code }, { status: 502 });
  }
}
