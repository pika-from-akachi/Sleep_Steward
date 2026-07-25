import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { getDriver } from "@/lib/hardware";
import { getUserId } from "@/lib/session-cookie";

/**
 * 点击式硬件调度:应用睡眠方案 / 直接控灯控温。
 * action 白名单:applyProfile | setLight | setClimate
 */
export async function POST(req: Request) {
  const uid = await getUserId();
  if (!uid) return NextResponse.json({ error: "未登录" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const driver = getDriver();

  if (body?.action === "applyProfile") {
    const profile = await db.preferenceProfile.findUnique({ where: { id: body.profileId } });
    if (!profile || profile.userId !== uid) {
      return NextResponse.json({ error: "方案不存在" }, { status: 404 });
    }
    const target = Math.round(((profile.tempMin + profile.tempMax) / 2) * 10) / 10;
    await driver.setClimate({ targetTempC: target });
    await driver.setLight({
      on: profile.lightBrightness > 0,
      brightness: profile.lightBrightness,
      colorTemp: profile.lightColorTemp === "cool" ? "cool" : "warm",
    });
    return NextResponse.json({
      message: `已应用「${profile.name}」:目标 ${target}℃,灯光 ${profile.lightBrightness}%`,
    });
  }

  if (body?.action === "setLight") {
    await driver.setLight({
      on: !!body.params?.on,
      brightness: Number(body.params?.brightness) || 0,
      colorTemp: body.params?.colorTemp === "cool" ? "cool" : "warm",
    });
    return NextResponse.json({ message: "灯光已调整" });
  }

  if (body?.action === "setClimate") {
    const t = Number(body.params?.targetTempC);
    if (!Number.isFinite(t)) return NextResponse.json({ error: "温度无效" }, { status: 400 });
    await driver.setClimate({ targetTempC: t });
    return NextResponse.json({ message: `目标温度已设为 ${t}℃` });
  }

  return NextResponse.json({ error: "不支持的指令" }, { status: 400 });
}
