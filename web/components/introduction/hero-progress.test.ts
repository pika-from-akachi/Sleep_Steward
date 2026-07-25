import { describe, expect, it } from "vitest";
import { getHeroFrame } from "./hero-progress";

describe("Introduction hero progress", () => {
  it("从卧室进入完整夜景，并在结束时展示品牌文案", () => {
    expect(getHeroFrame(0)).toMatchObject({
      roomScale: 1,
      roomOpacity: 1,
      skyScale: 1.06,
      copyState: "care",
    });
    expect(getHeroFrame(1)).toMatchObject({
      roomScale: 3.6,
      roomOpacity: 0,
      skyScale: 1,
      copyOpacity: 1,
      copyState: "rest",
    });
  });

  it("限制越界滚动进度并按设计切换三段文案", () => {
    expect(getHeroFrame(-1)).toEqual(getHeroFrame(0));
    expect(getHeroFrame(2)).toEqual(getHeroFrame(1));
    expect(getHeroFrame(0.31).copyState).toBe("care");
    expect(getHeroFrame(0.32).copyState).toBe("companion");
    expect(getHeroFrame(0.72).copyState).toBe("rest");
  });

  it("减少动态效果时只保留安静的淡出过渡", () => {
    const frame = getHeroFrame(0.8, true);
    expect(frame.roomScale).toBe(1);
    expect(frame.skyScale).toBe(1);
    expect(frame.roomOpacity).toBeCloseTo(0.2, 5);
  });
});
