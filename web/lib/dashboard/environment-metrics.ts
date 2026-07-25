export interface GaugeEnvironment {
  tempC: number;
  humidityPct: number;
  lightLux: number;
}

export type MetricKey = "temp" | "humidity" | "light";

export interface EnvironmentMetric {
  key: MetricKey;
  label: string;
  unit: string;
  min: number;
  max: number;
  accent: string;
  glow: string;
  shadow: string;
  read: (env: GaugeEnvironment) => number;
  format: (value: number) => string;
}

export const METRIC_ORDER: readonly MetricKey[] = ["temp", "humidity", "light"];

export const ENVIRONMENT_METRICS: readonly EnvironmentMetric[] = [
  {
    key: "temp",
    label: "温度",
    unit: "℃",
    min: 12,
    max: 34,
    accent: "#f0c184",
    glow: "rgba(230, 143, 76, 0.72)",
    shadow: "rgba(119, 54, 26, 0.5)",
    read: (env) => env.tempC,
    format: (value) => value.toFixed(1),
  },
  {
    key: "humidity",
    label: "湿度",
    unit: "%",
    min: 20,
    max: 90,
    accent: "#8ed9c9",
    glow: "rgba(72, 188, 174, 0.68)",
    shadow: "rgba(18, 87, 91, 0.52)",
    read: (env) => env.humidityPct,
    format: (value) => String(Math.round(value)),
  },
  {
    key: "light",
    label: "光照",
    unit: "lux",
    min: 0,
    max: 600,
    accent: "#f1dfb2",
    glow: "rgba(238, 214, 158, 0.62)",
    shadow: "rgba(93, 75, 39, 0.48)",
    read: (env) => env.lightLux,
    format: (value) => String(Math.round(value)),
  },
] as const;

export function metricDefinition(key: MetricKey): EnvironmentMetric {
  return ENVIRONMENT_METRICS.find((metric) => metric.key === key)!;
}

export function getMetricSlots(active: MetricKey): {
  left: MetricKey;
  center: MetricKey;
  right: MetricKey;
} {
  const remaining = METRIC_ORDER.filter((key) => key !== active);
  return { left: remaining[0], center: active, right: remaining[1] };
}

export function readMetric(key: MetricKey, env: GaugeEnvironment | null): string {
  if (!env) return "--";
  const metric = metricDefinition(key);
  return metric.format(metric.read(env));
}

export function metricProgress(key: MetricKey, value: number | null): number {
  if (value === null) return 0;
  const metric = metricDefinition(key);
  return Math.min(1, Math.max(0, (value - metric.min) / (metric.max - metric.min)));
}
