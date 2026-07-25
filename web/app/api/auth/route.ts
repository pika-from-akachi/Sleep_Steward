import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { defaultPrefFor, presetPlansFor, type UserType } from "@/lib/defaults";
import { setUserCookie } from "@/lib/session-cookie";

export async function POST(req: Request) {
  const body = await req.json().catch(() => null);
  const nickname = typeof body?.nickname === "string" ? body.nickname.trim() : "";
  const userType = body?.userType as UserType;
  const childAge =
    typeof body?.childAge === "number" ? body.childAge : null;

  if (!nickname) {
    return NextResponse.json({ error: "昵称不能为空" }, { status: 400 });
  }
  if (userType !== "adult" && userType !== "child") {
    return NextResponse.json({ error: "用户类型无效" }, { status: 400 });
  }

  // 轻量账号的“登录”语义：昵称、模式（儿童再含年龄）一致时取回已有账号。
  const existing = await db.user.findFirst({
    where: {
      nickname,
      userType,
      childAge: userType === "child" ? childAge : null,
    },
    orderBy: { createdAt: "asc" },
  });
  if (existing) {
    await setUserCookie(existing.id);
    return NextResponse.json({ userId: existing.id, existing: true });
  }

  const user = await db.user.create({
    data: {
      nickname,
      userType,
      childAge: userType === "child" ? childAge : null,
    },
  });

  // 预填默认偏好 + 内置可选方案预设
  const seeds = [defaultPrefFor(userType), ...presetPlansFor(userType)];
  await db.preferenceProfile.createMany({
    data: seeds.map((s) => ({ ...s, userId: user.id })),
  });

  await setUserCookie(user.id);

  return NextResponse.json({ userId: user.id });
}
