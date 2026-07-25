"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown } from "lucide-react";
import EnvGauge from "@/components/EnvGauge";
import NightSky from "@/components/NightSky";
import TopNav from "@/components/TopNav";
import VoiceInput from "@/components/VoiceInput";

export interface PrefItem {
  id: string;
  name: string;
  tempMin: number;
  tempMax: number;
  humidityMin: number;
  humidityMax: number;
  lightBrightness: number;
  lightColorTemp: "warm" | "cool";
  isDefault: boolean;
}

interface EnvState {
  tempC: number;
  humidityPct: number;
  lightLux: number;
  stale?: boolean;
  lightSource?: "measured" | "estimated" | "simulated";
}

interface HardwareHealth {
  ok: boolean;
  driver: "sim" | "rdk-x5";
}

export default function DashboardClient({
  nickname,
  userType,
  prefs,
}: {
  nickname: string;
  userType: "adult" | "child";
  prefs: PrefItem[];
}) {
  const router = useRouter();
  const [env, setEnv] = useState<EnvState | null>(null);
  const [hardwareHealth, setHardwareHealth] = useState<HardwareHealth | null>(null);
  const [activePref, setActivePref] = useState(prefs.find((p) => p.isDefault)?.id ?? prefs[0]?.id);
  const [toast, setToast] = useState("");
  const [starting, setStarting] = useState(false);
  const [demoOpen, setDemoOpen] = useState(false);
  const [prefsOpen, setPrefsOpen] = useState(false);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activePrefItem = prefs.find((p) => p.id === activePref);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), 4200);
  }, []);

  const refreshEnv = useCallback(async () => {
    try {
      const res = await fetch("/api/env");
      if (res.ok) {
        const data = await res.json();
        setEnv(data.env);
        setHardwareHealth(data.health);
      }
    } catch {}
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(refreshEnv, 0);
    const id = setInterval(refreshEnv, 4000);
    return () => {
      clearTimeout(initial);
      clearInterval(id);
    };
  }, [refreshEnv]);

  async function applyPref(id: string) {
    setActivePref(id);
    const res = await fetch("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "applyProfile", profileId: id }),
    });
    const data = await res.json().catch(() => ({}));
    showToast(res.ok ? data.message : data.error || "指令未成功,请重试");
    refreshEnv();
  }

  async function startSleep() {
    setStarting(true);
    const res = await fetch("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profileId: activePref }),
    });
    if (res.ok) router.push("/sleeping");
    else {
      setStarting(false);
      showToast("开启失败,请重试");
    }
  }

  async function inject(field: "tempC" | "humidityPct" | "lightLux", value: number) {
    await fetch("/api/demo/inject", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [field]: value }),
    });
    refreshEnv();
  }

  return (
    <main className="relative min-h-screen overflow-x-hidden px-5">
      <NightSky blur={12} />
      <TopNav userType={userType} />

      <div className="mx-auto mb-32 mt-28 w-full max-w-2xl px-2 py-10 md:mt-32 md:px-4">
        {/* 问候 */}
        <h1 className="serif text-[30px] font-semibold tracking-[0.04em]">晚上好,{nickname}</h1>
        <p className="mt-1.5 text-[12.5px] text-cream-dim">
          {userType === "child" ? "儿童模式" : "成人模式"} · 系统正在守护这间卧室
        </p>
        {hardwareHealth && (
          <p
            aria-live="polite"
            className={`mt-2 text-[11.5px] ${hardwareHealth.ok ? "text-cream-dim" : "text-[#efb0a8]"}`}
          >
            {hardwareHealth.driver === "sim"
              ? "模拟环境"
              : hardwareHealth.ok
                ? "RDK X5 实机在线"
                : "RDK X5 硬件离线"}
            {env?.stale ? " · 正在显示最后有效读数" : ""}
            {env?.lightSource === "estimated" ? " · 光照为灯态估算" : ""}
          </p>
        )}

        {/* 实时环境:单圆仪表,下方切换 温度 / 湿度 / 光照 */}
        <div className="mt-10">
          <EnvGauge env={env} />
        </div>

        {/* 睡眠方案:默认只露当前方案,右侧下拉换方案 */}
        <p className="mb-2 mt-9 text-[11px] tracking-[0.28em] text-cream-dim">睡眠方案</p>
        <div className="glass overflow-hidden rounded-2xl">
          <button
            onClick={() => setPrefsOpen((v) => !v)}
            aria-expanded={prefsOpen}
            className="flex w-full items-center justify-between px-5 py-4 text-left transition-colors hover:bg-white/[0.03]"
          >
            <span className="text-[14px]">
              <span className="mr-2 align-[3px] text-[8px] text-moon">●</span>
              {activePrefItem ? activePrefItem.name : "选择方案"}
            </span>
            <span className="flex items-center gap-2.5 text-[12px] text-cream-dim">
              {activePrefItem && (
                <>
                  {activePrefItem.tempMin}–{activePrefItem.tempMax}℃ ·{" "}
                  {activePrefItem.lightColorTemp === "warm" ? "暖光" : "冷光"}{" "}
                  {activePrefItem.lightBrightness}% · 使用中
                </>
              )}
              <ChevronDown
                size={15}
                className={`transition-transform duration-200 ${prefsOpen ? "rotate-180" : ""}`}
              />
            </span>
          </button>
          <AnimatePresence initial={false}>
            {prefsOpen && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.25, ease: "easeOut" }}
                className="overflow-hidden"
              >
                {prefs
                  .filter((p) => p.id !== activePref)
                  .map((p) => (
                    <button
                      key={p.id}
                      onClick={() => {
                        setPrefsOpen(false);
                        applyPref(p.id);
                      }}
                      className="flex w-full items-baseline justify-between border-t border-dashed border-hair px-5 py-3.5 text-left transition-colors hover:bg-white/[0.03]"
                    >
                      <span className="text-[14px]">{p.name}</span>
                      <span className="text-[12px] text-cream-dim">
                        {p.tempMin}–{p.tempMax}℃ · {p.lightColorTemp === "warm" ? "暖光" : "冷光"}{" "}
                        {p.lightBrightness}%
                      </span>
                    </button>
                  ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* 语音指令 */}
        <div className="mt-9">
          <VoiceInput />
        </div>

        {/* 开始睡眠 */}
        <button
          onClick={startSleep}
          disabled={starting}
          className="btn-moon mt-12 w-full rounded-2xl py-4.5 text-[15px] font-semibold tracking-[0.5em] [text-indent:0.5em] disabled:opacity-70"
          style={{ paddingTop: 17, paddingBottom: 17 }}
        >
          {starting ? "正在开启" : "开 始 睡 眠"}
        </button>
        <p className="mt-3.5 text-center text-[11.5px] tracking-[0.1em] text-cream-dim">
          进入后系统每 5 秒巡检一次,自动守护环境
        </p>
      </div>

      {/* 演示造场面板 */}
      {hardwareHealth?.driver === "sim" && (
      <div className="fixed bottom-5 right-5 z-20">
        <AnimatePresence>
          {demoOpen && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 12 }}
              className="glass mb-3 w-72 rounded-2xl p-5"
            >
              <p className="mb-4 text-[11px] tracking-[0.24em] text-cream-dim">演示造场 · 模拟环境突变</p>
              {env && (
                <>
                  <DemoSlider label="温度" min={12} max={34} step={0.5} unit="℃"
                    value={env.tempC} onCommit={(v) => inject("tempC", v)} />
                  <DemoSlider label="湿度" min={20} max={90} step={1} unit="%"
                    value={env.humidityPct} onCommit={(v) => inject("humidityPct", v)} />
                  <DemoSlider label="光照" min={0} max={600} step={10} unit="lux"
                    value={env.lightLux} onCommit={(v) => inject("lightLux", v)} />
                </>
              )}
              <p className="mt-2 text-[11px] leading-relaxed text-cream-dim">
                把温度拉低试试 —— 开始睡眠后,系统会自动发现并升温。
              </p>
            </motion.div>
          )}
        </AnimatePresence>
        <button
          onClick={() => setDemoOpen((v) => !v)}
          className="glass ml-auto block rounded-full px-4 py-2 text-[12px] tracking-[0.2em] text-cream-dim transition-colors hover:text-cream"
        >
          {demoOpen ? "收起" : "演示"}
        </button>
      </div>
      )}

      {/* 轻提示 */}
      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: -14 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -14 }}
            className="glass fixed left-1/2 top-24 z-50 -translate-x-1/2 rounded-full px-6 py-3 text-[13px] text-cream"
          >
            {toast}
          </motion.div>
        )}
      </AnimatePresence>
    </main>
  );
}

function DemoSlider({
  label, min, max, step, unit, value, onCommit,
}: {
  label: string; min: number; max: number; step: number; unit: string;
  value: number; onCommit: (v: number) => void;
}) {
  const [local, setLocal] = useState(value);
  const dragging = useRef(false);

  useEffect(() => {
    if (!dragging.current) setLocal(value);
  }, [value]);

  return (
    <div className="mb-3.5">
      <div className="mb-1 flex justify-between text-[12px]">
        <span className="text-cream-dim">{label}</span>
        <span className="[font-variant-numeric:tabular-nums]">{local}{unit}</span>
      </div>
      <input
        type="range"
        min={min} max={max} step={step} value={local}
        onChange={(e) => { dragging.current = true; setLocal(Number(e.target.value)); }}
        onPointerUp={() => { dragging.current = false; onCommit(local); }}
        onKeyUp={(e) => { if (e.key === "ArrowLeft" || e.key === "ArrowRight") onCommit(local); }}
        className="w-full accent-[#eed9a4]"
      />
    </div>
  );
}
