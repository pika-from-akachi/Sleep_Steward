export type HeroCopyState = "care" | "companion" | "rest";

export interface HeroFrame {
  roomScale: number;
  roomOpacity: number;
  skyScale: number;
  copyOpacity: number;
  copyState: HeroCopyState;
}

const clamp = (value: number) => Math.min(1, Math.max(0, value));
const range = (value: number, start: number, end: number) =>
  clamp((value - start) / (end - start));
const mix = (from: number, to: number, progress: number) =>
  from + (to - from) * progress;

export function getHeroFrame(progress: number, reducedMotion = false): HeroFrame {
  const normalized = clamp(progress);
  const copyState: HeroCopyState =
    normalized < 0.32 ? "care" : normalized < 0.72 ? "companion" : "rest";
  const copyOpacity = range(normalized, 0, 0.08);

  if (reducedMotion) {
    return {
      roomScale: 1,
      roomOpacity: 1 - normalized,
      skyScale: 1,
      copyOpacity,
      copyState,
    };
  }

  return {
    roomScale: mix(1, 3.6, range(normalized, 0.1, 0.75)),
    roomOpacity: 1 - range(normalized, 0.75, 0.88),
    skyScale: mix(1.06, 1, normalized),
    copyOpacity,
    copyState,
  };
}
