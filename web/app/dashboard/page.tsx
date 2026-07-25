import { redirect } from "next/navigation";
import { getUserId } from "@/lib/session-cookie";
import { db } from "@/lib/db";
import DashboardClient from "@/components/DashboardClient";

export default async function DashboardPage() {
  const uid = await getUserId();
  if (!uid) redirect("/welcome");

  const user = await db.user.findUnique({
    where: { id: uid },
    include: { prefs: { orderBy: [{ isDefault: "desc" }, { createdAt: "asc" }] } },
  });
  if (!user) redirect("/welcome");

  const activeSession = await db.sleepSession.findFirst({
    where: { userId: uid, status: "active" },
  });
  if (activeSession) redirect("/sleeping");

  return (
    <DashboardClient
      nickname={user.nickname}
      userType={user.userType as "adult" | "child"}
      prefs={user.prefs.map((p) => ({
        id: p.id,
        name: p.name,
        tempMin: p.tempMin,
        tempMax: p.tempMax,
        humidityMin: p.humidityMin,
        humidityMax: p.humidityMax,
        lightBrightness: p.lightBrightness,
        lightColorTemp: p.lightColorTemp as "warm" | "cool",
        isDefault: p.isDefault,
      }))}
    />
  );
}
