import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { getUserId } from "@/lib/session-cookie";
import { summarizeSession } from "@/lib/report/summarize";

/** 开始睡眠:结束遗留的 active 会话,按所选偏好建新会话 */
export async function POST(req: Request) {
  const uid = await getUserId();
  if (!uid) return NextResponse.json({ error: "未登录" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  let profileId: string | undefined = body?.profileId;

  if (!profileId) {
    const def = await db.preferenceProfile.findFirst({
      where: { userId: uid, isDefault: true },
    });
    if (!def) return NextResponse.json({ error: "没有可用的睡眠偏好" }, { status: 400 });
    profileId = def.id;
  }

  const profile = await db.preferenceProfile.findUnique({
    where: { id: profileId },
    select: { userId: true },
  });
  if (!profile || profile.userId !== uid) {
    return NextResponse.json({ error: "睡眠方案不存在" }, { status: 404 });
  }

  await db.sleepSession.updateMany({
    where: { userId: uid, status: "active" },
    data: { status: "ended", endedAt: new Date() },
  });

  const session = await db.sleepSession.create({
    data: { userId: uid, profileId, status: "active" },
  });

  return NextResponse.json({ sessionId: session.id });
}

/** 结束睡眠:补齐 endedAt,汇总全量数据 */
export async function PATCH(req: Request) {
  const uid = await getUserId();
  if (!uid) return NextResponse.json({ error: "未登录" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const sessionId: string | undefined = body?.sessionId;
  if (!sessionId) return NextResponse.json({ error: "缺少 sessionId" }, { status: 400 });

  const session = await db.sleepSession.findUnique({ where: { id: sessionId } });
  if (!session || session.userId !== uid) {
    return NextResponse.json({ error: "会话不存在" }, { status: 404 });
  }

  await db.sleepSession.update({
    where: { id: sessionId },
    data: { status: "ended", endedAt: new Date() },
  });
  const summary = await summarizeSession(sessionId);

  return NextResponse.json({ sessionId, summary });
}
