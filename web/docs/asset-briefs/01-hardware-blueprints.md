# 素材 01 · 硬件蓝图线稿 ×5(最高优先级)

## 用途
品牌展示页「硬件生态」一屏(对标 jeskojets 的 Fleet 蓝图页)。五件硬件以工程蓝图线稿风格陈列在夜空底色上,是展示页最出彩的一格。

## 统一规格
- **尺寸**:1600 × 1200(4:3)
- **格式**:PNG,**透明背景**(必须,要叠在深夜色渐变上)
- **线条颜色**:暖象牙白 `#F3EAD8`(整站的月下暖白),细线,线宽统一
- **风格**:工程蓝图 / 产品示意线稿,正面或 3/4 视角,可带少量尺寸标注线,克制优雅
- **禁止**:文字、色块填充、阴影、写实照片质感、蓝色网格底(底必须透明)

## 通用负面提示词(每张都加)
```
text, letters, watermark, solid background, blueprint grid paper, color fill, photorealistic, shadow, blurry
```

## 逐张提示词

### 1. RDK X5 开发板 → 交付名 `rdk-x5.png`
```
Technical blueprint line drawing of a single-board computer development board (like Raspberry Pi form factor) with 40-pin GPIO header, heatsink, USB and Ethernet ports, thin warm ivory lines (#F3EAD8) on transparent background, engineering schematic style, top view with subtle dimension marks, minimal, elegant
```

### 2. 温湿度传感器 → 交付名 `sensor-temp-humidity.png`
```
Technical blueprint line drawing of a small temperature and humidity sensor module (SHT3x style breakout board with 4 pins), thin warm ivory lines (#F3EAD8) on transparent background, engineering schematic style, front view with subtle dimension marks, minimal, elegant
```

### 3. LED 灯带 → 交付名 `led-strip.png`
```
Technical blueprint line drawing of a flexible LED light strip gently curved in an S shape, individual LED chips visible, thin warm ivory lines (#F3EAD8) on transparent background, engineering schematic style, subtle dimension marks, minimal, elegant
```

### 4. 小扬声器 → 交付名 `speaker.png`
```
Technical blueprint line drawing of a small round bedside speaker with fabric mesh texture indicated by fine lines, thin warm ivory lines (#F3EAD8) on transparent background, engineering schematic style, 3/4 view with subtle dimension marks, minimal, elegant
```

### 5. 智能睡眠戒指 → 交付名 `sleep-ring.png`
```
Technical blueprint line drawing of a smart ring (sleep tracker) with inner sensor bumps, shown at an angle with a cross-section detail, thin warm ivory lines (#F3EAD8) on transparent background, engineering schematic style, subtle dimension marks, minimal, elegant
```

## 交付
放入 `public/assets/blueprints/`,文件名如上。五张线宽和风格要一致(建议同一会话/同一参数连续生成)。

## 验收标准
- 底透明,叠在深靛夜色(`#131539`)上线条清晰可读
- 五张并排看风格统一,像同一位工程师画的
- 无任何文字和 logo
