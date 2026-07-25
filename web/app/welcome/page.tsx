"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import NightSky from "@/components/NightSky";

type UserType = "adult" | "child";

export default function WelcomePage() {
  const router = useRouter();
  const [userType, setUserType] = useState<UserType>("adult");
  const [nickname, setNickname] = useState("");
  const [childAge, setChildAge] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function start() {
    if (!nickname.trim()) {
      setError("先给自己起个称呼吧");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nickname: nickname.trim(),
          userType,
          childAge: userType === "child" ? Number(childAge) || null : null,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "进入失败,请再试一次");
      }
      router.push("/dashboard");
    } catch (e) {
      setError(e instanceof Error ? e.message : "进入失败,请再试一次");
      setLoading(false);
    }
  }

  return (
    <main className="relative min-h-screen overflow-hidden">
      <NightSky blur={12} />

      <div className="mx-auto flex min-h-screen w-full max-w-[460px] flex-col justify-center px-6 py-10">
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="glass rounded-3xl p-7 md:p-9"
        >
          <div className="mb-16 flex items-center gap-2.5 text-[13px] tracking-[0.32em] text-cream-dim">
            <span className="moon-mark" />
            宝宝爱睡觉
          </div>

          <h1 className="serif text-[40px] font-semibold leading-[1.4] tracking-[0.04em] [text-shadow:0_2px_30px_rgba(10,10,30,.6)] md:text-[44px]">
            今晚,
            <br />
            睡个好觉。
          </h1>
          <p className="mb-11 mt-3.5 text-[13.5px] tracking-[0.12em] text-cream-dim">
            你的主动式睡眠搭子 · 陪你入夜
          </p>

          <div className="glass mb-3 flex overflow-hidden rounded-2xl">
            {(["adult", "child"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setUserType(t)}
                className={`flex-1 py-3.5 text-[13.5px] transition-all ${
                  userType === t ? "bg-moon/15 text-cream" : "text-cream-dim hover:text-cream"
                }`}
              >
                {t === "adult" ? "成人" : "儿童"}
              </button>
            ))}
          </div>

          <input
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && start()}
            placeholder="怎么称呼你?"
            className="glass mb-3 w-full rounded-2xl px-5 py-3.5 text-[13.5px] text-cream outline-none placeholder:text-cream-dim focus:border-moon/45"
          />

          {userType === "child" && (
            <input
              value={childAge}
              onChange={(e) => setChildAge(e.target.value.replace(/\D/g, ""))}
              inputMode="numeric"
              placeholder="宝宝几岁了?"
              className="glass mb-3 w-full rounded-2xl px-5 py-3.5 text-[13.5px] text-cream outline-none placeholder:text-cream-dim focus:border-moon/45"
            />
          )}

          {error && <p className="mb-3 text-[13px] text-[#e8a598]">{error}</p>}

          <button
            onClick={start}
            disabled={loading}
            className="btn-moon mt-3 w-full rounded-2xl py-4 text-[14.5px] font-semibold tracking-[0.55em] [text-indent:0.55em] disabled:opacity-70"
          >
            {loading ? "正在入夜" : "入 夜"}
          </button>

          <p className="mt-4 text-center text-[11.5px] tracking-[0.1em] text-cream-dim">
            无需注册 · 一键进入
          </p>
        </motion.div>
      </div>
    </main>
  );
}
