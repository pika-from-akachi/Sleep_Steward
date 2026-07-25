"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Music2 } from "lucide-react";

/**
 * 程序化助眠声音:Web Audio 实时合成,无音频文件、可离线。
 * 呈现为顶部导航右侧的圆形按钮 + 下拉选曲菜单;播放中按钮亮月色。
 * 成人:白噪 / 海浪 / 冥想钟磬;儿童:摇篮轻音 / 白噪(spec:儿童剔除冥想)。
 */
type TrackId = "noise" | "waves" | "bell" | "lullaby";

const TRACKS: Record<TrackId, { name: string; note: string }> = {
  noise: { name: "静谧白噪", note: "均匀的沙沙声" },
  waves: { name: "海浪轻语", note: "缓慢的潮汐起伏" },
  bell: { name: "冥想钟磬", note: "悠长的泛音" },
  lullaby: { name: "摇篮轻音", note: "柔和的和声" },
};

/* 与 TopNav 胶囊同一套壳样式与尺寸(弦月位 BTN + 16) */
const BTN_SIZE = 68;
const shellStyle: React.CSSProperties = {
  borderRadius: 999,
  border: "1px solid var(--hair)",
  background: "rgba(14, 15, 36, 0.55)",
  boxShadow: "0 10px 40px rgba(0,0,0,0.35)",
  backdropFilter: "blur(20px)",
  WebkitBackdropFilter: "blur(20px)",
};

function makeNoiseBuffer(ctx: AudioContext) {
  const buf = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
  const data = buf.getChannelData(0);
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
  return buf;
}

export default function SleepAudio({ userType = "adult" }: { userType?: "adult" | "child" }) {
  const [open, setOpen] = useState(false);
  const [playing, setPlaying] = useState<TrackId | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const nodesRef = useRef<AudioNode[]>([]);

  const available: TrackId[] =
    userType === "child" ? ["lullaby", "noise"] : ["noise", "waves", "bell"];

  function stop() {
    for (const n of nodesRef.current) {
      try {
        if (n instanceof AudioScheduledSourceNode) n.stop();
        n.disconnect();
      } catch {}
    }
    nodesRef.current = [];
    setPlaying(null);
  }

  useEffect(() => () => { stop(); ctxRef.current?.close(); }, []);

  /* 点击菜单外部收起 */
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    addEventListener("pointerdown", onDown);
    return () => removeEventListener("pointerdown", onDown);
  }, [open]);

  function play(id: TrackId) {
    if (playing === id) return stop();
    stop();
    const ctx = (ctxRef.current ??= new AudioContext());
    if (ctx.state === "suspended") ctx.resume();
    const master = ctx.createGain();
    master.gain.value = 0.001;
    master.gain.exponentialRampToValueAtTime(0.5, ctx.currentTime + 1.5);
    master.connect(ctx.destination);
    const nodes: AudioNode[] = [master];

    if (id === "noise" || id === "waves") {
      const src = ctx.createBufferSource();
      src.buffer = makeNoiseBuffer(ctx);
      src.loop = true;
      const lp = ctx.createBiquadFilter();
      lp.type = "lowpass";
      lp.frequency.value = id === "noise" ? 850 : 480;
      const g = ctx.createGain();
      g.gain.value = 0.32;
      src.connect(lp).connect(g).connect(master);
      if (id === "waves") {
        const lfo = ctx.createOscillator();
        lfo.frequency.value = 0.08;
        const depth = ctx.createGain();
        depth.gain.value = 0.14;
        lfo.connect(depth).connect(g.gain);
        lfo.start();
        nodes.push(lfo, depth);
      }
      src.start();
      nodes.push(src, lp, g);
    } else if (id === "bell") {
      // 悠长钟磬:低频正弦 + 泛音,缓慢颤音
      for (const [freq, vol] of [[196, 0.16], [392, 0.06], [588, 0.028]] as const) {
        const osc = ctx.createOscillator();
        osc.frequency.value = freq;
        const g = ctx.createGain();
        g.gain.value = vol;
        osc.connect(g).connect(master);
        osc.start();
        nodes.push(osc, g);
      }
      const trem = ctx.createOscillator();
      trem.frequency.value = 0.15;
      const tg = ctx.createGain();
      tg.gain.value = 0.12;
      trem.connect(tg).connect(master.gain);
      trem.start();
      nodes.push(trem, tg);
    } else {
      // 摇篮轻音:柔和大三和弦 + 慢揉音
      for (const [freq, vol] of [[262, 0.1], [330, 0.07], [392, 0.06], [524, 0.03]] as const) {
        const osc = ctx.createOscillator();
        osc.type = "triangle";
        osc.frequency.value = freq;
        const vib = ctx.createOscillator();
        vib.frequency.value = 0.4;
        const vg = ctx.createGain();
        vg.gain.value = 1.6;
        vib.connect(vg).connect(osc.frequency);
        vib.start();
        const g = ctx.createGain();
        g.gain.value = vol;
        osc.connect(g).connect(master);
        osc.start();
        nodes.push(osc, vib, vg, g);
      }
    }

    nodesRef.current = nodes;
    setPlaying(id);
  }

  return (
    <div ref={rootRef} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="助眠声音"
        title="助眠声音"
        aria-expanded={open}
        className={playing ? "text-moon" : "text-cream-dim hover:text-cream"}
        style={{
          ...shellStyle,
          width: BTN_SIZE,
          height: BTN_SIZE,
          display: "grid",
          placeItems: "center",
          cursor: "pointer",
          transition: "color 0.2s",
        }}
      >
        <Music2 size={23} strokeWidth={1.5} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            style={{
              ...shellStyle,
              borderRadius: 18,
              position: "absolute",
              right: 0,
              top: BTN_SIZE + 10,
              width: 244,
              padding: 8,
            }}
          >
            <p className="px-3 pb-1.5 pt-2 text-[10.5px] tracking-[0.28em] text-cream-dim">
              助眠声音
            </p>
            {available.map((id) => (
              <button
                key={id}
                onClick={() => play(id)}
                className={`flex w-full items-baseline justify-between rounded-xl px-3 py-2.5 text-left text-[13px] transition-colors ${
                  playing === id ? "bg-moon/15 text-moon" : "text-cream hover:bg-white/[0.06]"
                }`}
              >
                <span>{TRACKS[id].name}</span>
                <span className={`ml-3 text-[11px] ${playing === id ? "text-moon" : "text-cream-dim"}`}>
                  {playing === id ? "播放中" : TRACKS[id].note}
                </span>
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
