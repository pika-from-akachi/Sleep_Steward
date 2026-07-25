import { NextResponse } from "next/server";
import { getDriver } from "@/lib/hardware";
import { readHardwareSnapshot } from "@/lib/hardware/snapshot";

/** 仪表盘实时环境:当前读数 + 驱动健康 + 灯态 + 调温目标 */
export async function GET() {
  try {
    return NextResponse.json(await readHardwareSnapshot(getDriver()));
  } catch {
    return NextResponse.json({
      env: null,
      health: {
        ok: false,
        driver: process.env.HARDWARE_DRIVER === "rdk-x5" ? "rdk-x5" : "sim",
      },
      light: null,
      targetTempC: null,
    });
  }
}
