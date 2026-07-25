import { redirect } from "next/navigation";
import HistoryClient from "@/components/HistoryClient";
import { db } from "@/lib/db";
import { getUserId } from "@/lib/session-cookie";

export default async function HistoryPage() {
  const uid = await getUserId();
  if (!uid) redirect("/welcome");

  const [user, sessions, commands] = await Promise.all([
    db.user.findUnique({ where: { id: uid }, select: { nickname: true } }),
    db.sleepSession.findMany({
      where: { userId: uid, status: "ended" },
      orderBy: { startedAt: "desc" },
      include: { profile: { select: { name: true } } },
    }),
    db.voiceCommand.findMany({
      where: { userId: uid },
      orderBy: { createdAt: "desc" },
      take: 50,
    }),
  ]);

  if (!user) redirect("/welcome");

  return (
    <HistoryClient
      nickname={user.nickname}
      sessions={sessions.map((session) => ({
        id: session.id,
        profileName: session.profile.name,
        startedAt: session.startedAt.toISOString(),
        endedAt: session.endedAt?.toISOString() ?? session.startedAt.toISOString(),
        durationMin: Math.max(
          1,
          Math.round(
            ((session.endedAt?.getTime() ?? session.startedAt.getTime()) -
              session.startedAt.getTime()) /
              60_000,
          ),
        ),
      }))}
      commands={commands.map((command) => ({
        id: command.id,
        rawText: command.rawText,
        mode: command.mode,
        parsedJson: command.parsedJson,
        matchedDevice: command.matchedDevice,
        createdAt: command.createdAt.toISOString(),
      }))}
    />
  );
}
