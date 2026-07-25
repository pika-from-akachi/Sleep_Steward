import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { getDriver } from "@/lib/hardware";
import { getUserId } from "@/lib/session-cookie";
import {
  executeParsedCommand,
  type ParsedCommand,
} from "@/lib/voice/command";
import { matchHardcoded } from "@/lib/voice/hardcoded";
import { parseWithStepfun, StepFunError } from "@/lib/voice/stepfun";

const FALLBACK_MESSAGE =
  "没太听懂，试试：关灯 / 调高温度 / 开夜灯";

export async function POST(req: Request) {
  const uid = await getUserId();
  if (!uid) return NextResponse.json({ error: "未登录" }, { status: 401 });

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  const text = typeof body.text === "string" ? body.text.trim() : "";
  const sessionId =
    typeof body.sessionId === "string" && body.sessionId
      ? body.sessionId
      : null;

  if (!text) return NextResponse.json({ error: "指令不能为空" }, { status: 400 });
  if (text.length > 200) {
    return NextResponse.json({ error: "指令请控制在 200 字以内" }, { status: 400 });
  }

  if (sessionId) {
    const session = await db.sleepSession.findUnique({
      where: { id: sessionId },
      select: { userId: true, status: true },
    });
    if (!session || session.userId !== uid || session.status !== "active") {
      return NextResponse.json({ error: "睡眠会话不存在" }, { status: 404 });
    }
  }

  let mode: "hardcoded" | "natural" = "hardcoded";
  let parsed: ParsedCommand | null = matchHardcoded(text);

  if (!parsed) {
    mode = "natural";
    try {
      parsed = await parseWithStepfun(text);
    } catch (error) {
      const reason = error instanceof StepFunError ? error.code : "upstream";
      await db.voiceCommand.create({
        data: {
          userId: uid,
          sessionId,
          rawText: text,
          mode,
          parsedJson: JSON.stringify({ status: "unparsed", reason }),
          matchedDevice: null,
        },
      });
      return NextResponse.json({
        mode,
        parsed: null,
        message: FALLBACK_MESSAGE,
        fallback: true,
      });
    }
  }

  try {
    const message = await executeParsedCommand(parsed, getDriver());
    await db.voiceCommand.create({
      data: {
        userId: uid,
        sessionId,
        rawText: text,
        mode,
        parsedJson: JSON.stringify(parsed),
        matchedDevice: parsed.action,
      },
    });
    return NextResponse.json({ mode, parsed, message });
  } catch {
    await db.voiceCommand.create({
      data: {
        userId: uid,
        sessionId,
        rawText: text,
        mode,
        parsedJson: JSON.stringify({
          ...parsed,
          status: "execution_failed",
        }),
        matchedDevice: parsed.action,
      },
    });
    return NextResponse.json(
      { error: "指令未成功，已记录并可重试" },
      { status: 502 },
    );
  }
}
