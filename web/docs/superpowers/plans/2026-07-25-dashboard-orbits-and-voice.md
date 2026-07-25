# Dashboard Orbits and Voice Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把仪表盘单圆环境仪表升级为可点击换位的三圆 3D 轨道，并明确语音按钮操作方式及指令解析来源。

**Architecture:** 把指标排序、格式化和语音来源标签提取为纯函数并用 Vitest 锁定，再由 React 组件负责 Framer Motion 换位与 CSS 3D 视差。硬件 API 与 StepFun 服务端保持不变。

**Tech Stack:** Next.js 16、React 19、TypeScript、Framer Motion、Tailwind CSS v4、Vitest。

## Global Constraints

- 中央主圆、左右副圆始终同时展示温度、湿度、光照。
- CSS 3D + Framer Motion，不新增 Three.js 场景。
- 默认温度居中；点击副圆或分段按钮触发相同换位。
- 桌面与 390px 移动端不得重叠文字或溢出。
- 语音为单击开始、再次单击停止，不使用长按。
- 快捷指令显示“本地指令”，自然语言成功显示“StepFun 智能理解”，fallback 显示“模型未配置或暂不可用”。
- 不修改硬件服务、LED Pin、DHT11 或 StepFun 服务端协议。

---

### Task 1: Environment Metric Model

**Files:**
- Create: `lib/dashboard/environment-metrics.ts`
- Test: `lib/dashboard/environment-metrics.test.ts`

**Interfaces:**
- Produces: `MetricKey = "temp" | "humidity" | "light"`
- Produces: `ENVIRONMENT_METRICS`
- Produces: `getMetricSlots(active: MetricKey)`
- Produces: `readMetric(metric, env)` and `metricProgress(metric, value)`

- [ ] **Step 1: Write failing tests**

```ts
it("keeps all three metrics visible with the active metric centered", () => {
  expect(getMetricSlots("humidity")).toEqual({
    left: "temp", center: "humidity", right: "light",
  });
});

it("formats live readings independently", () => {
  expect(readMetric("temp", { tempC: 26.9, humidityPct: 65.2, lightLux: 2 })).toBe("26.9");
  expect(readMetric("humidity", { tempC: 26.9, humidityPct: 65.2, lightLux: 2 })).toBe("65");
});
```

- [ ] **Step 2: Verify RED**

Run: `npx vitest run lib/dashboard/environment-metrics.test.ts`
Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement the metric model**

```ts
export const METRIC_ORDER = ["temp", "humidity", "light"] as const;

export function getMetricSlots(active: MetricKey) {
  const remaining = METRIC_ORDER.filter((key) => key !== active);
  return { left: remaining[0], center: active, right: remaining[1] };
}
```

Each metric definition includes label, unit, min, max, formatter, reader, accent, glow, and progress color. Null environments return `--`.

- [ ] **Step 4: Verify GREEN**

Run: `npx vitest run lib/dashboard/environment-metrics.test.ts`
Expected: all metric tests PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/dashboard/environment-metrics.ts lib/dashboard/environment-metrics.test.ts
git commit -m "feat: add dashboard environment metric model"
```

### Task 2: Three-Orb Environment Gauge

**Files:**
- Modify: `components/EnvGauge.tsx`
- Modify: `app/globals.css`

**Interfaces:**
- Consumes: metric model from Task 1.
- Preserves: `EnvGauge({ env }: { env: GaugeEnv | null })`.

- [ ] **Step 1: Replace the single gauge with three stable slots**

Render all metrics as `motion.button` elements. For each metric, derive `left | center | right` from `getMetricSlots(active)` and animate to fixed slot variants:

```ts
const SLOT_MOTION = {
  left: { x: "-78%", y: 24, scale: 0.52, opacity: 0.82, zIndex: 1 },
  center: { x: "0%", y: 0, scale: 1, opacity: 1, zIndex: 3 },
  right: { x: "78%", y: 24, scale: 0.52, opacity: 0.82, zIndex: 1 },
};
```

The button uses `aria-pressed`, visible value/unit/label, and an SVG progress ring. Clicking sets the metric active.

- [ ] **Step 2: Add shared pointer perspective**

The stage writes `--orbit-tilt-x` and `--orbit-tilt-y` from pointer position, clamped to 7 degrees. Inner orb surfaces apply:

```css
transform: perspective(800px)
  rotateX(calc(var(--orbit-tilt-x) * 1deg))
  rotateY(calc(var(--orbit-tilt-y) * 1deg));
```

Pointer leave resets both variables to zero. `prefers-reduced-motion` disables tilt and continuous glow rotation.

- [ ] **Step 3: Add responsive fixed dimensions**

Desktop stage uses `min-height: 340px`, main orb `300px`, side scale `0.52`. At `max-width: 520px`, main orb becomes `236px`, side scale `0.39`, and horizontal offset becomes `72%` so the side values remain legible.

- [ ] **Step 4: Verify component integration**

Run: `npm test && npx tsc --noEmit`
Expected: all tests and typecheck PASS.

- [ ] **Step 5: Commit**

```bash
git add components/EnvGauge.tsx app/globals.css
git commit -m "feat: add interactive three-orb environment gauge"
```

### Task 3: Voice Interaction Source Feedback

**Files:**
- Create: `lib/voice/presentation.ts`
- Test: `lib/voice/presentation.test.ts`
- Modify: `components/VoiceInput.tsx`

**Interfaces:**
- Produces: `voiceSourceLabel(result: { mode?: unknown; fallback?: unknown }): string | null`
- Consumes existing `/api/voice/parse` response fields `mode` and `fallback`.

- [ ] **Step 1: Write failing source-label tests**

```ts
expect(voiceSourceLabel({ mode: "hardcoded" })).toBe("本地指令");
expect(voiceSourceLabel({ mode: "natural" })).toBe("StepFun 智能理解");
expect(voiceSourceLabel({ mode: "natural", fallback: true })).toBe("模型未配置或暂不可用");
```

- [ ] **Step 2: Verify RED**

Run: `npx vitest run lib/voice/presentation.test.ts`
Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement source labeling**

```ts
export function voiceSourceLabel(result: VoiceResult): string | null {
  if (result.fallback === true) return "模型未配置或暂不可用";
  if (result.mode === "hardcoded") return "本地指令";
  if (result.mode === "natural") return "StepFun 智能理解";
  return null;
}
```

- [ ] **Step 4: Update VoiceInput feedback**

Store `sourceLabel` after each response. Listening text becomes “正在聆听，再次点击可停止”; successful result displays a compact source label above the result message. Starting a new request clears the old source label.

- [ ] **Step 5: Verify GREEN**

Run: `npx vitest run lib/voice/presentation.test.ts && npm test && npx tsc --noEmit`
Expected: all tests and typecheck PASS.

- [ ] **Step 6: Commit**

```bash
git add lib/voice/presentation.ts lib/voice/presentation.test.ts components/VoiceInput.tsx
git commit -m "feat: clarify voice interaction and model source"
```

### Task 4: Browser and Hardware Acceptance

**Files:**
- No source change unless a failing test or screenshot demonstrates a defect.

- [ ] **Step 1: Run complete verification**

Run: `python3 -m unittest hardware/rdk-x5/test_hardware_agent.py -v`
Run: `npm test`
Run: `npx tsc --noEmit`
Run: `npm run build`

- [ ] **Step 2: Verify desktop layout**

At `1115x837`, confirm all three values are visible, side orbs do not cover the greeting or sleep profile, and clicking each side orb moves it to center without layout shift.

- [ ] **Step 3: Verify mobile layout**

At `390x844`, confirm side circles stay inside the viewport, labels do not clip, the segmented control remains usable, and the voice button remains below the sleep profile.

- [ ] **Step 4: Verify voice and hardware**

Click the microphone once to start and again to stop. Execute quick command “关灯”; confirm the UI shows “本地指令” and RDK X5 reports all light channels at 0. Natural language may show StepFun only after a real Key is configured.
