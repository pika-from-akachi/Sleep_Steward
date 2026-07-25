import { redirect } from "next/navigation";
import { db } from "@/lib/db";
import { getUserId } from "@/lib/session-cookie";
import { summarizeSession, type SessionSummary } from "@/lib/report/summarize";
import ReportClient from "@/components/ReportClient";

export default async function ReportPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  const uid = await getUserId();
  if (!uid) redirect("/welcome");

  const session = await db.sleepSession.findUnique({
    where: { id: sessionId },
    include: { profile: true },
  });
  if (!session || session.userId !== uid) redirect("/dashboard");
  if (session.status === "active") redirect("/sleeping");

  const summary: SessionSummary = session.summaryJson
    ? JSON.parse(session.summaryJson)
    : await summarizeSession(sessionId);

  const voices = await db.voiceCommand.findMany({
    where: { sessionId, userId: uid },
    orderBy: { createdAt: "asc" },
  });

  return (
    <ReportClient
      summary={summary}
      profileName={session.profile.name}
      voices={voices.map((v) => ({
        rawText: v.rawText,
        mode: v.mode as "hardcoded" | "natural",
        parsedJson: v.parsedJson,
        at: v.createdAt.toISOString(),
      }))}
    />
  );
}
