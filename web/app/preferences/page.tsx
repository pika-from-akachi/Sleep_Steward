import { redirect } from "next/navigation";
import PreferencesClient from "@/components/PreferencesClient";
import { db } from "@/lib/db";
import { getUserId } from "@/lib/session-cookie";

export default async function PreferencesPage() {
  const uid = await getUserId();
  if (!uid) redirect("/welcome");

  const user = await db.user.findUnique({
    where: { id: uid },
    include: {
      prefs: { orderBy: [{ isDefault: "desc" }, { createdAt: "asc" }] },
    },
  });
  if (!user) redirect("/welcome");

  return (
    <PreferencesClient
      nickname={user.nickname}
      initialPrefs={user.prefs.map((pref) => ({
        id: pref.id,
        name: pref.name,
        tempMin: pref.tempMin,
        tempMax: pref.tempMax,
        humidityMin: pref.humidityMin,
        humidityMax: pref.humidityMax,
        lightBrightness: pref.lightBrightness,
        lightColorTemp: pref.lightColorTemp === "cool" ? "cool" : "warm",
        isDefault: pref.isDefault,
      }))}
    />
  );
}
