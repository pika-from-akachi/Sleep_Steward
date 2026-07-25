"use client";

import { CSSProperties, PointerEvent, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  ENVIRONMENT_METRICS,
  GaugeEnvironment,
  getMetricSlots,
  metricProgress,
  MetricKey,
  readMetric,
} from "@/lib/dashboard/environment-metrics";

export type GaugeEnv = GaugeEnvironment;

type MetricSlot = "left" | "center" | "right";

const RADIUS = 45;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function slotForMetric(active: MetricKey, key: MetricKey): MetricSlot {
  const slots = getMetricSlots(active);
  if (slots.center === key) return "center";
  return slots.left === key ? "left" : "right";
}

function positionForSlot(slot: MetricSlot) {
  if (slot === "left") return { left: "14%", top: "var(--orbit-side-drop)", opacity: 0.82, zIndex: 1 };
  if (slot === "right") return { left: "86%", top: "var(--orbit-side-drop)", opacity: 0.82, zIndex: 1 };
  return { left: "50%", top: "0px", opacity: 1, zIndex: 3 };
}

export default function EnvGauge({ env }: { env: GaugeEnv | null }) {
  const [active, setActive] = useState<MetricKey>("temp");
  const stageRef = useRef<HTMLDivElement>(null);
  const reduceMotion = useReducedMotion();

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    if (reduceMotion || !stageRef.current) return;
    const bounds = stageRef.current.getBoundingClientRect();
    const x = Math.max(-1, Math.min(1, ((event.clientX - bounds.left) / bounds.width - 0.5) * 2));
    const y = Math.max(-1, Math.min(1, ((event.clientY - bounds.top) / bounds.height - 0.5) * 2));
    stageRef.current.style.setProperty("--orbit-main-tilt-x", `${(-y * 7).toFixed(2)}deg`);
    stageRef.current.style.setProperty("--orbit-main-tilt-y", `${(x * 7).toFixed(2)}deg`);
    stageRef.current.style.setProperty("--orbit-side-tilt-x", `${(-y * 4).toFixed(2)}deg`);
    stageRef.current.style.setProperty("--orbit-side-tilt-y", `${(x * 4).toFixed(2)}deg`);
  }

  function resetPointerTilt() {
    if (!stageRef.current) return;
    stageRef.current.style.setProperty("--orbit-main-tilt-x", "0deg");
    stageRef.current.style.setProperty("--orbit-main-tilt-y", "0deg");
    stageRef.current.style.setProperty("--orbit-side-tilt-x", "0deg");
    stageRef.current.style.setProperty("--orbit-side-tilt-y", "0deg");
  }

  return (
    <div className="env-orbit-wrap">
      <div
        ref={stageRef}
        className="env-orbit-stage"
        onPointerMove={handlePointerMove}
        onPointerLeave={resetPointerTilt}
      >
        {ENVIRONMENT_METRICS.map((metric) => {
          const slot = slotForMetric(active, metric.key);
          const rawValue = env ? metric.read(env) : null;
          const progress = metricProgress(metric.key, rawValue);
          const customProperties = {
            "--orbit-accent": metric.accent,
            "--orbit-glow": metric.glow,
            "--orbit-shadow": metric.shadow,
          } as CSSProperties;

          return (
            <motion.div
              key={metric.key}
              className={`env-orbit-position is-${slot}`}
              animate={positionForSlot(slot)}
              transition={reduceMotion ? { duration: 0 } : { duration: 0.72, ease: [0.22, 1, 0.36, 1] }}
            >
              <button
                type="button"
                aria-label={`查看${metric.label}，当前${readMetric(metric.key, env)}${metric.unit}`}
                aria-pressed={slot === "center"}
                className={`env-orbit-button ${slot === "center" ? "is-center" : "is-side"}`}
                style={customProperties}
                onClick={() => setActive(metric.key)}
              >
                <span className="env-orbit-glow" aria-hidden />
                <span className="env-orbit-surface">
                  <svg className="env-orbit-ring" viewBox="0 0 100 100" aria-hidden>
                    <circle cx="50" cy="50" r={RADIUS} fill="none" stroke="rgba(243,234,216,0.11)" strokeWidth="1.8" />
                    <circle
                      cx="50"
                      cy="50"
                      r={RADIUS}
                      fill="none"
                      stroke="var(--orbit-accent)"
                      strokeWidth="2.5"
                      strokeLinecap="round"
                      strokeDasharray={`${progress * CIRCUMFERENCE} ${CIRCUMFERENCE}`}
                    />
                  </svg>
                  <span className="env-orbit-content">
                    <span className="env-orbit-number serif">
                      {readMetric(metric.key, env)}
                      <span className="env-orbit-unit">{metric.unit}</span>
                    </span>
                    <span className="env-orbit-label">{metric.label}</span>
                  </span>
                </span>
              </button>
            </motion.div>
          );
        })}
      </div>

      <div className="glass env-orbit-tabs" aria-label="环境指标切换">
        {ENVIRONMENT_METRICS.map((metric) => (
          <button
            key={metric.key}
            type="button"
            onClick={() => setActive(metric.key)}
            aria-pressed={metric.key === active}
            className={metric.key === active ? "is-active" : ""}
          >
            {metric.label}
          </button>
        ))}
      </div>
    </div>
  );
}
