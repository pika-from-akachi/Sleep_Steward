import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { getUserId } from "@/lib/session-cookie";

interface PrefValues {
  name: string;
  tempMin: number;
  tempMax: number;
  humidityMin: number;
  humidityMax: number;
  lightBrightness: number;
  lightColorTemp: string;
}

function finiteNumber(value: unknown, fallback: number) {
  if (value === undefined || value === null || value === "") return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : Number.NaN;
}

function parsePrefInput(
  body: Record<string, unknown>,
  fallback: PrefValues,
): { data: PrefValues } | { error: string } {
  const name =
    typeof body.name === "string" && body.name.trim()
      ? body.name.trim()
      : fallback.name;
  const tempMin = finiteNumber(body.tempMin, fallback.tempMin);
  const tempMax = finiteNumber(body.tempMax, fallback.tempMax);
  const humidityMin = finiteNumber(body.humidityMin, fallback.humidityMin);
  const humidityMax = finiteNumber(body.humidityMax, fallback.humidityMax);
  const rawBrightness = finiteNumber(body.lightBrightness, fallback.lightBrightness);
  const lightBrightness = Math.round(rawBrightness);
  const lightColorTemp =
    body.lightColorTemp === undefined
      ? fallback.lightColorTemp
      : body.lightColorTemp === "warm" || body.lightColorTemp === "cool"
        ? body.lightColorTemp
        : "";

  if (!name) return { error: "名称不能为空" };
  if (
    ![tempMin, tempMax, humidityMin, humidityMax, lightBrightness].every(Number.isFinite)
  ) {
    return { error: "方案参数必须是有效数字" };
  }
  if (tempMin < 12 || tempMax > 35 || tempMin >= tempMax) {
    return { error: "温度范围需在 12–35℃ 之间，且最低值小于最高值" };
  }
  if (humidityMin < 20 || humidityMax > 90 || humidityMin >= humidityMax) {
    return { error: "湿度范围需在 20–90% 之间，且最低值小于最高值" };
  }
  if (lightBrightness < 0 || lightBrightness > 100) {
    return { error: "灯光亮度需在 0–100% 之间" };
  }
  if (!lightColorTemp) return { error: "灯光色温无效" };

  return {
    data: {
      name,
      tempMin,
      tempMax,
      humidityMin,
      humidityMax,
      lightBrightness,
      lightColorTemp,
    },
  };
}

export async function GET() {
  const uid = await getUserId();
  if (!uid) return NextResponse.json({ error: "未登录" }, { status: 401 });
  const prefs = await db.preferenceProfile.findMany({
    where: { userId: uid },
    orderBy: [{ isDefault: "desc" }, { createdAt: "asc" }],
  });
  return NextResponse.json({ prefs });
}

/** 新建偏好模板(含「把本次环境存为模板」) */
export async function POST(req: Request) {
  const uid = await getUserId();
  if (!uid) return NextResponse.json({ error: "未登录" }, { status: 401 });
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  const parsed = parsePrefInput(body, {
    name: "",
    tempMin: 22,
    tempMax: 25,
    humidityMin: 40,
    humidityMax: 60,
    lightBrightness: 15,
    lightColorTemp: "warm",
  });
  if ("error" in parsed) {
    return NextResponse.json({ error: parsed.error }, { status: 400 });
  }

  const pref = await db.preferenceProfile.create({
    data: {
      userId: uid,
      ...parsed.data,
      isDefault: false,
    },
  });
  return NextResponse.json({ pref });
}

export async function PATCH(req: Request) {
  const uid = await getUserId();
  if (!uid) return NextResponse.json({ error: "未登录" }, { status: 401 });
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  const id = typeof body.id === "string" ? body.id : "";
  const existing = id
    ? await db.preferenceProfile.findUnique({ where: { id } })
    : null;
  if (!existing || existing.userId !== uid) {
    return NextResponse.json({ error: "方案不存在" }, { status: 404 });
  }
  const parsed = parsePrefInput(body, existing);
  if ("error" in parsed) {
    return NextResponse.json({ error: parsed.error }, { status: 400 });
  }
  const pref = await db.preferenceProfile.update({
    where: { id: existing.id },
    data: parsed.data,
  });
  return NextResponse.json({ pref });
}

export async function DELETE(req: Request) {
  const uid = await getUserId();
  if (!uid) return NextResponse.json({ error: "未登录" }, { status: 401 });
  const { searchParams } = new URL(req.url);
  const id = searchParams.get("id");
  const existing = id ? await db.preferenceProfile.findUnique({ where: { id } }) : null;
  if (!existing || existing.userId !== uid) {
    return NextResponse.json({ error: "方案不存在" }, { status: 404 });
  }
  if (existing.isDefault) {
    return NextResponse.json({ error: "默认方案不可删除" }, { status: 400 });
  }
  const used = await db.sleepSession.count({ where: { profileId: existing.id } });
  if (used > 0) {
    return NextResponse.json({ error: "方案已被睡眠记录引用,暂不可删除" }, { status: 400 });
  }
  await db.preferenceProfile.delete({ where: { id: existing.id } });
  return NextResponse.json({ ok: true });
}
