# 素材 05 · 助眠音频 2~3 段(可选,有则加分)

## 用途
功能区「助眠资源」真实可播放的音频。没有也不阻塞开发(会先放静音占位),demo 现场有真声音体验完整度高很多。

## 统一规格
- **格式**:MP3(128kbps 以上)或 AAC
- **时长**:每段 3~5 分钟,**首尾无缝循环**(结尾淡出到与开头相同的底噪/和声)
- **响度**:整体偏低响度(-20 LUFS 左右的感觉),不能有突然的响音
- **禁止**:人声(歌词)、鼓点、突强突弱

## 逐段提示词(Suno / Udio 等)

### 1. 轻音乐(成人+儿童通用)→ 交付名 `soft-music.mp3`
```
gentle sleep ambient, warm felt piano and soft pad, 60 bpm, very sparse, seamless loop, no vocals, no drums, lullaby mood, warm and tender
```

### 2. 白噪/自然底噪 → 交付名 `white-noise.mp3`
```
soft rain on window with distant low wind, steady gentle white noise texture, no melody, no vocals, seamless loop, calm night ambience
```

### 3. 冥想引导底乐(仅成人,可选)→ 交付名 `meditation.mp3`
```
deep meditation drone, slow breathing pace ambient pad, subtle warm harmonics, 50 bpm feel, no vocals, no percussion, seamless loop, floating and serene
```

## 交付
放入 `public/assets/audio/`,文件名如上。

## 验收标准
- 循环点听不出接缝
- 音量平稳,深夜戴耳机听不刺耳
- 儿童模式只会用到 1 和 2(冥想不给儿童),所以 1、2 优先
