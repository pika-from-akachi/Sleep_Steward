import { NextResponse } from "next/server";
import { getDriver, SimDriver } from "@/lib/hardware";

/** 演示造场:手动把模拟环境调冷/调热/调湿/调亮 */
export async function POST(req: Request) {
  const driver = getDriver();
  if (!(driver instanceof SimDriver)) {
    return NextResponse.json({ error: "当前驱动不支持造场" }, { status: 400 });
  }
  const body = await req.json().catch(() => ({}));
  driver.injectEnv({
    tempC: typeof body?.tempC === "number" ? body.tempC : undefined,
    humidityPct: typeof body?.humidityPct === "number" ? body.humidityPct : undefined,
    lightLux: typeof body?.lightLux === "number" ? body.lightLux : undefined,
  });
  const env = await driver.readEnvironment();
  return NextResponse.json({ env });
}
