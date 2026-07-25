import { NextResponse } from "next/server";
import { runTick } from "@/lib/loop/run-tick";
import { getUserId } from "@/lib/session-cookie";

export async function POST(req: Request) {
  const uid = await getUserId();
  if (!uid) return NextResponse.json({ error: "未登录" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const sessionId: string | undefined = body?.sessionId;
  if (!sessionId) return NextResponse.json({ error: "缺少 sessionId" }, { status: 400 });

  try {
    const result = await runTick(sessionId);
    return NextResponse.json(result);
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "巡检失败" },
      { status: 500 },
    );
  }
}
