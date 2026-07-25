"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import NightSky from "@/components/NightSky";
import VoiceInput from "@/components/VoiceInput";

interface TickEnv {
  tempC: number;
  humidityPct: number;
  lightLux: number;
  stale?: boolean;
  lightSource?: "measured" | "estimated" | "simulated";
}

export default function SleepingClient({
  sessionId,
  startedAt,
  profileName,
}: {
  sessionId: string;
  startedAt: string;
  profileName: string;
}) {
  const router = useRouter();
  const [elapsed, setElapsed] = useState("00:00:00");
  const [env, setEnv] = useState<TickEnv | null>(null);
  const [notices, setNotices] = useState<{ id: number; text: string }[]>([]);
  const [ending, setEnding] = useState(false);
  const failCount = useRef(0);
  const noticeId = useRef(0);

  /* 计时器 */
  useEffect(() => {
    const start = new Date(startedAt).getTime();
    const id = setInterval(() => {
      const s = Math.max(0, Math.floor((Date.now() - start) / 1000));
      const hh = String(Math.floor(s / 3600)).padStart(2, "0");
      const mm = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
      const ss = String(s % 60).padStart(2, "0");
      setElapsed(`${hh}:${mm}:${ss}`);
    }, 1000);
    return () => clearInterval(id);
  }, [startedAt]);

  const pushNotice = useCallback((text: string) => {
    const id = ++noticeId.current;
    setNotices((n) => [...n.slice(-2), { id, text }]);
    setTimeout(() => setNotices((n) => n.filter((x) => x.id !== id)), 6000);
  }, []);

  /* 每 5 秒巡检 */
  useEffect(() => {
    let stopped = false;
    async function tick() {
      try {
        const res = await fetch("/api/tick", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sessionId }),
        });
        if (!res.ok) throw new Error();
        const data = await res.json();
        if (stopped) return;
        failCount.current = 0;
        setEnv(data.env);
        for (const msg of data.messages ?? []) pushNotice(msg);
      } catch {
        failCount.current++;
        if (failCount.current === 3) pushNotice("硬件连接中断,正在重试");
      }
    }
    tick();
    const id = setInterval(tick, 5000);
    return () => {
      stopped = true;
      clearInterval(id);
    };
  }, [sessionId, pushNotice]);

  async function endSleep() {
    setEnding(true);
    const res = await fetch("/api/session", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionId }),
    });
    if (res.ok) router.push(`/report/${sessionId}`);
    else {
      setEnding(false);
      pushNotice("结束失败,请再试一次");
    }
  }

  return (
    <main className="relative flex min-h-screen flex-col items-center overflow-hidden">
      <NightSky blur={12} />

      {/* 自动调节提示 */}
      <div
        aria-live="polite"
        className="fixed right-4 top-5 z-20 flex w-[54vw] min-w-[180px] max-w-sm flex-col items-end gap-2 sm:right-7 sm:top-7"
      >
        <AnimatePresence>
          {notices.map((n) => (
            <motion.div
              key={n.id}
              initial={{ opacity: 0, y: -12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="glass max-w-full rounded-full px-5 py-2.5 text-center text-[12.5px] text-cream"
            >
              {n.text}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      <div className="relative z-10 flex min-h-screen w-full max-w-xl flex-col items-center justify-center px-7 py-12 text-center [@media(max-height:640px)]:py-5">
        <div className="glass flex w-full flex-col items-center rounded-3xl px-6 py-8 [@media(max-height:640px)]:py-5">
        <p className="text-[12px] tracking-[0.34em] text-cream-dim">睡眠进行中 · {profileName}</p>

        <div className="serif mt-4 text-[64px] font-semibold tracking-[0.06em] [font-variant-numeric:tabular-nums] [text-shadow:0_2px_40px_rgba(10,10,30,.7)] [@media(max-height:640px)]:mt-1 [@media(max-height:640px)]:text-[52px] md:text-[76px]">
          {elapsed}
        </div>

        <p className="mt-2 text-[13px] tracking-[0.14em] text-cream-dim [@media(max-height:640px)]:mt-0">
          {env
            ? `${env.tempC.toFixed(1)}℃ · ${Math.round(env.humidityPct)}% · ${Math.round(env.lightLux)} lux${env.lightSource === "estimated" ? "（估算）" : ""}${env.stale ? " · 上次有效读数" : ""}`
            : "正在感知环境"}
        </p>

        <div className="mt-9 w-full max-w-sm [@media(max-height:640px)]:mt-4">
          <VoiceInput sessionId={sessionId} compact />
        </div>

        <button
          onClick={endSleep}
          disabled={ending}
          className="mt-10 w-full max-w-sm rounded-2xl border border-hair py-4 text-[14px] tracking-[0.5em] text-cream-dim transition-colors [text-indent:0.5em] hover:border-moon/40 hover:text-cream disabled:opacity-60 [@media(max-height:640px)]:mt-4 [@media(max-height:640px)]:py-3"
        >
          {ending ? "正在整理本次睡眠" : "结 束 睡 眠"}
        </button>
        </div>
      </div>
    </main>
  );
}
