import { redirect } from "next/navigation";
import { db } from "@/lib/db";
import { getUserId } from "@/lib/session-cookie";
import SleepingClient from "@/components/SleepingClient";

export default async function SleepingPage() {
  const uid = await getUserId();
  if (!uid) redirect("/welcome");

  const session = await db.sleepSession.findFirst({
    where: { userId: uid, status: "active" },
    orderBy: { startedAt: "desc" },
    include: { profile: true },
  });
  if (!session) redirect("/dashboard");

  return (
    <SleepingClient
      sessionId={session.id}
      startedAt={session.startedAt.toISOString()}
      profileName={session.profile.name}
    />
  );
}
