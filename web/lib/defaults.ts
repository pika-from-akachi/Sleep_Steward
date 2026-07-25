export type UserType = "adult" | "child";

export interface PrefSeed {
  name: string;
  tempMin: number;
  tempMax: number;
  humidityMin: number;
  humidityMax: number;
  lightBrightness: number;
  lightColorTemp: "warm" | "cool";
  isDefault: boolean;
}

/** 一键进入时预填的默认偏好(成人/儿童各一套)。 */
export function defaultPrefFor(userType: UserType): PrefSeed {
  return userType === "child"
    ? {
        name: "宝宝舒睡",
        tempMin: 24,
        tempMax: 26,
        humidityMin: 45,
        humidityMax: 60,
        lightBrightness: 15,
        lightColorTemp: "warm",
        isDefault: true,
      }
    : {
        name: "标准助眠",
        tempMin: 22,
        tempMax: 25,
        humidityMin: 40,
        humidityMax: 60,
        lightBrightness: 20,
        lightColorTemp: "warm",
        isDefault: true,
      };
}

/** 内置的可点选睡眠方案预设(仪表盘方案卡 + 种子数据用)。 */
export function presetPlansFor(userType: UserType): PrefSeed[] {
  if (userType === "child") {
    return [
      {
        name: "宝宝午睡",
        tempMin: 25,
        tempMax: 27,
        humidityMin: 45,
        humidityMax: 60,
        lightBrightness: 25,
        lightColorTemp: "warm",
        isDefault: false,
      },
      {
        name: "夜间安睡",
        tempMin: 23,
        tempMax: 25,
        humidityMin: 45,
        humidityMax: 60,
        lightBrightness: 8,
        lightColorTemp: "warm",
        isDefault: false,
      },
    ];
  }
  return [
    {
      name: "夏季低温模式",
      tempMin: 20,
      tempMax: 23,
      humidityMin: 40,
      humidityMax: 55,
      lightBrightness: 15,
      lightColorTemp: "cool",
      isDefault: false,
    },
    {
      name: "宿舍静音灯光模式",
      tempMin: 22,
      tempMax: 25,
      humidityMin: 40,
      humidityMax: 60,
      lightBrightness: 5,
      lightColorTemp: "warm",
      isDefault: false,
    },
    {
      name: "冬夜暖睡",
      tempMin: 24,
      tempMax: 26,
      humidityMin: 45,
      humidityMax: 60,
      lightBrightness: 12,
      lightColorTemp: "warm",
      isDefault: false,
    },
  ];
}
