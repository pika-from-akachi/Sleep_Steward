"use client";

import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Area, AreaChart, CartesianGrid, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import NightSky from "@/components/NightSky";
import TopNav from "@/components/TopNav";
import type { SessionSummary } from "@/lib/report/summarize";

interface VoiceRow {
  rawText: string;
  mode: "hardcoded" | "natural";
  parsedJson: string;
  at: string;
}

function fmtTime(at: string | number) {
  const d = new Date(at);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/* 睡眠分期背景带配色:填充淡、标签亮 */
const STAGE_FILL: Record<string, string> = {
  浅睡: "#7da2e8",
  深睡: "#4a5fa8",
  快速眼动: "#f5dfae",
};
const STAGE_LABEL: Record<string, string> = {
  浅睡: "#a7c0ef",
  深睡: "#8d9fd6",
  快速眼动: "#f5dfae",
};

export default function ReportClient({
  summary,
  profileName,
  voices,
}: {
  summary: SessionSummary;
  profileName: string;
  voices: VoiceRow[];
}) {
  const [toast, setToast] = useState("");
  const [saving, setSaving] = useState(false);

  const chartData = useMemo(
    () =>
      summary.envSeries.map((p) => ({
        t: new Date(p.t).getTime(),
        tempC: p.tempC,
        humidityPct: p.humidityPct,
      })),
    [summary.envSeries],
  );

  const hasEnvData = chartData.length > 1;

  /* 图表时间跨度:有数据用数据首尾,没数据用会话起止(至少撑 5 分钟,保证空图也有轴) */
  const spanStart = hasEnvData ? chartData[0].t : new Date(summary.startedAt).getTime();
  const spanEndRaw = hasEnvData
    ? chartData[chartData.length - 1].t
    : new Date(summary.endedAt).getTime();
  const spanEnd = spanEndRaw > spanStart ? spanEndRaw : spanStart + 5 * 60_000;

  /* 无数据时喂两个空点,让 recharts 照常撑出坐标系 */
  const plotData: { t: number; tempC: number | null; humidityPct: number | null }[] = hasEnvData
    ? chartData
    : [
        { t: spanStart, tempC: null, humidityPct: null },
        { t: spanEnd, tempC: null, humidityPct: null },
      ];

  /* 分期只有各阶段时长,按顺序摊到时间轴上画成背景带;时长全为 0 时按典型比例给预览带 */
  const stageBands = useMemo(() => {
    const total = summary.ringStages.reduce((s, x) => s + x.minutes, 0);
    const weights =
      total > 0
        ? summary.ringStages.map((s) => ({
            stage: s.stage,
            w: s.minutes,
            label: `${s.stage} ${s.minutes} 分`,
          }))
        : summary.ringStages.map((s, i) => ({
            stage: s.stage,
            w: [5, 3, 2][i] ?? 1,
            label: s.stage,
          }));
    const totalW = weights.reduce((s, x) => s + x.w, 0) || 1;
    return weights
      .filter((x) => x.w > 0)
      .map((x, index, visibleWeights) => {
        const precedingWeight = visibleWeights
          .slice(0, index)
          .reduce((sum, item) => sum + item.w, 0);
        const x1 = spanStart + ((spanEnd - spanStart) * precedingWeight) / totalW;
        const x2 = spanStart + ((spanEnd - spanStart) * (precedingWeight + x.w)) / totalW;
        return { stage: x.stage, label: x.label, x1, x2 };
      });
  }, [summary.ringStages, spanStart, spanEnd]);

  const stageAt = (t: number) =>
    stageBands.find((b) => t >= b.x1 && t <= b.x2)?.stage;
  const durationText =
    summary.durationMin >= 60
      ? `${Math.floor(summary.durationMin / 60)} 小时 ${summary.durationMin % 60} 分`
      : `${summary.durationMin} 分钟`;

  async function saveAsPref() {
    setSaving(true);
    const temps = summary.envSeries.map((p) => p.tempC);
    const hums = summary.envSeries.map((p) => p.humidityPct);
    const avgT = temps.length ? temps.reduce((a, b) => a + b, 0) / temps.length : 23.5;
    const avgH = hums.length ? hums.reduce((a, b) => a + b, 0) / hums.length : 50;
    const res = await fetch("/api/prefs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: `本次环境 ${fmtTime(summary.startedAt)}`,
        tempMin: Math.round((avgT - 1.5) * 10) / 10,
        tempMax: Math.round((avgT + 1.5) * 10) / 10,
        humidityMin: Math.max(20, Math.round(avgH - 10)),
        humidityMax: Math.min(90, Math.round(avgH + 10)),
        lightBrightness: 15,
        lightColorTemp: "warm",
      }),
    });
    setSaving(false);
    setToast(res.ok ? "已保存为新的睡眠方案" : "保存失败,请重试");
    setTimeout(() => setToast(""), 4000);
  }

  return (
    <main className="relative min-h-screen overflow-x-hidden px-5">
      <NightSky blur={12} />
      <TopNav />

      <div className="glass mx-auto mb-24 mt-28 w-full max-w-2xl rounded-3xl px-7 py-10 md:mt-32 md:px-10">
        <p className="text-[12px] tracking-[0.34em] text-cream-dim">睡眠报告 · {profileName}</p>
        <h1 className="serif mt-3 text-[34px] font-semibold tracking-[0.04em]">
          这一夜,睡了 {durationText}
        </h1>
        <p className="mt-2 text-[13px] text-cream-dim">
          {fmtTime(summary.startedAt)} 入夜 · {fmtTime(summary.endedAt)} 醒来
        </p>

        {/* 关键数字 */}
        <div className="mt-9 flex border-y border-hair">
          {[
            { label: "升降温调节", value: summary.climateAdjustCount, unit: "次" },
            { label: "灯光调节", value: summary.lightAdjustCount, unit: "次" },
            { label: "湿度调节", value: summary.humidityAdjustCount, unit: "次" },
            { label: "语音指令", value: summary.voiceCount, unit: "条" },
          ].map((s, i) => (
            <div key={s.label} className={`flex-1 py-5 text-center ${i > 0 ? "border-l border-hair" : ""}`}>
              <div className="serif text-[28px] [font-variant-numeric:tabular-nums]">
                {s.value}
                <span className="ml-1 text-[12px] text-cream-dim">{s.unit}</span>
              </div>
              <div className="mt-1 text-[10.5px] tracking-[0.2em] text-cream-dim">{s.label}</div>
            </div>
          ))}
        </div>

        {/* 环境曲线 + 睡眠分期背景带(分期来自睡眠戒指,时长按比例摊上时间轴);无数据也保留坐标系预览 */}
        <>
            <div className="mb-3 mt-10 flex flex-wrap items-baseline justify-between gap-2">
              <p className="text-[11px] tracking-[0.28em] text-cream-dim">
                夜间环境与睡眠分期 · 来自睡眠戒指
              </p>
              <div className="flex items-center gap-4 text-[10.5px] text-cream-dim">
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-[2px] w-4 rounded-full" style={{ background: "#f5dfae" }} />
                  温度
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-[2px] w-4 rounded-full" style={{ background: "#7da2e8" }} />
                  湿度
                </span>
              </div>
            </div>
            <div className="relative h-60 w-full">
              {!hasEnvData && (
                <p className="absolute inset-x-0 top-[45%] z-10 text-center text-[12px] tracking-[0.12em] text-cream-dim">
                  本次睡眠太短,还没攒下环境曲线
                </p>
              )}
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={plotData} margin={{ top: 22, right: 4, left: -14, bottom: 0 }}>
                  <defs>
                    <linearGradient id="rt" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#f5dfae" stopOpacity={0.32} />
                      <stop offset="100%" stopColor="#f5dfae" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="rh" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#7da2e8" stopOpacity={0.22} />
                      <stop offset="100%" stopColor="#7da2e8" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid vertical={false} strokeDasharray="3 7" stroke="rgba(243,234,216,0.08)" />
                  {stageBands.map((b) => (
                    <ReferenceArea
                      key={b.stage}
                      yAxisId="h"
                      x1={b.x1}
                      x2={b.x2}
                      fill={STAGE_FILL[b.stage]}
                      fillOpacity={0.09}
                      stroke="rgba(243,234,216,0.10)"
                      strokeOpacity={1}
                      label={{
                        value: b.label,
                        position: "insideTop",
                        fill: STAGE_LABEL[b.stage],
                        fontSize: 10.5,
                        offset: 6,
                      }}
                    />
                  ))}
                  <XAxis
                    dataKey="t"
                    type="number"
                    domain={[spanStart, spanEnd]}
                    tickFormatter={(v) => fmtTime(v)}
                    tick={{ fill: "#b9ad95", fontSize: 10 }}
                    tickLine={false}
                    tickMargin={8}
                    axisLine={{ stroke: "rgba(243,234,216,.16)" }}
                    minTickGap={52}
                  />
                  <YAxis
                    yAxisId="t"
                    domain={hasEnvData ? ["dataMin - 1", "dataMax + 1"] : [20, 26]}
                    tickFormatter={(v) => `${v}°`}
                    tick={{ fill: "#b9ad95", fontSize: 10 }}
                    tickLine={false}
                    axisLine={false}
                    width={44}
                  />
                  <YAxis yAxisId="h" orientation="right" domain={[0, 100]} hide />
                  <Tooltip
                    contentStyle={{ background: "rgba(16,16,40,.92)", border: "1px solid rgba(243,234,216,.16)", borderRadius: 12, fontSize: 12, color: "#f3ead8" }}
                    labelFormatter={(label) => {
                      const stage = stageAt(Number(label));
                      return `${fmtTime(Number(label))}${stage ? ` · ${stage}` : ""}`;
                    }}
                    formatter={(value, name) => [
                      name === "tempC" ? `${Number(value).toFixed(1)}℃` : `${Math.round(Number(value))}%`,
                      name === "tempC" ? "温度" : "湿度",
                    ]}
                  />
                  <Area yAxisId="h" type="monotone" dataKey="humidityPct" stroke="#7da2e8" strokeWidth={1.4} fill="url(#rh)" isAnimationActive={false} dot={false} />
                  <Area yAxisId="t" type="monotone" dataKey="tempC" stroke="#f5dfae" strokeWidth={2} fill="url(#rt)" isAnimationActive={false} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
        </>

        {/* 语音指令记录 */}
        <p className="mb-3 mt-10 text-[11px] tracking-[0.28em] text-cream-dim">语音指令记录</p>
        {voices.length === 0 ? (
          <p className="text-[13px] text-cream-dim">这一夜没有语音指令,一切都由系统安静完成。</p>
        ) : (
          <div>
            {voices.map((v, i) => (
              <div key={i} className="border-b border-dashed border-hair py-3">
                <div className="flex items-baseline justify-between">
                  <span className="text-[13.5px]">「{v.rawText}」</span>
                  <span className="text-[11px] text-cream-dim">
                    {fmtTime(v.at)} · {v.mode === "hardcoded" ? "快捷指令" : "AI 理解"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 操作 */}
        <div className="mt-12 flex flex-col gap-3 sm:flex-row">
          <button
            onClick={saveAsPref}
            disabled={saving}
            className="btn-moon flex-1 rounded-2xl py-4 text-[13.5px] font-semibold tracking-[0.24em] disabled:opacity-70"
          >
            {saving ? "正在保存" : "把本次环境存为睡眠方案"}
          </button>
          <a
            href="/dashboard"
            className="flex-1 rounded-2xl border border-hair py-4 text-center text-[13.5px] tracking-[0.24em] text-cream-dim transition-colors hover:border-moon/40 hover:text-cream"
          >
            回到仪表盘
          </a>
        </div>
      </div>

      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: -14 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="glass fixed left-1/2 top-24 z-50 -translate-x-1/2 rounded-full px-6 py-3 text-[13px] text-cream"
          >
            {toast}
          </motion.div>
        )}
      </AnimatePresence>
    </main>
  );
}
