"""
盖被子机器人 - VLM 视觉检测模块
使用 StepFun step-3.7-flash 多模态模型分析摄像头画面
判断小朋友是否踢掉了被子
"""
import base64
import time
import requests
from pathlib import Path
from typing import Optional


class BlanketDetector:
    """检测小朋友是否盖着被子"""

    # StepFun API 配置 (OpenAI 兼容接口)
    API_URL = "https://api.stepfun.com/v1/chat/completions"
    MODEL = "step-3.7-flash"

    SYSTEM_PROMPT = """你是一个婴儿监护机器人视觉系统。请仔细观察图像，回答以下问题：

1. 图像中是否有一个正在睡觉的人/小朋友？(有/没有)
2. 小朋友/人的身体是否被毯子/被子盖着？(盖着/没盖着)
3. 毯子盖到了什么位置？(胸口以上/胸口以下/完全没盖/不确定)

请用 JSON 格式回答：
{"person_detected": true/false, "covered": true/false, "cover_level": "chest_above"|"chest_below"|"not_covered"|"unknown", "description": "简短描述"}

只输出 JSON，不要有其他内容。"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    def _encode_image(self, image_path: str) -> str:
        """将图片编码为 base64"""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def analyze(self, image_path: str, retry: int = 2) -> Optional[dict]:
        """
        分析一张图片，返回检测结果

        Returns:
            dict: {"person_detected": bool, "covered": bool, "cover_level": str, "description": str}
            或 None (调用失败时)
        """
        if not Path(image_path).exists():
            print(f"[VLM] 图片不存在: {image_path}")
            return None

        image_b64 = self._encode_image(image_path)
        ext = Path(image_path).suffix.lower().replace(".", "")
        mime = f"image/{ext}" if ext in ("jpg", "jpeg", "png", "webp") else "image/jpeg"

        payload = {
            "model": self.MODEL,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{image_b64}",
                                "detail": "low",
                            },
                        },
                        {"type": "text", "text": "请分析这张监护画面。"},
                    ],
                },
            ],
            "temperature": 0.1,
            "max_tokens": 200,
        }

        for attempt in range(retry + 1):
            try:
                resp = self.session.post(
                    self.API_URL,
                    json=payload,
                    timeout=15,
                )
                if resp.status_code == 200:
                    raw = resp.json()["choices"][0]["message"]["content"]
                    return self._parse_response(raw)
                else:
                    print(f"[VLM] API 错误 {resp.status_code}: {resp.text[:200]}")
                    if attempt < retry:
                        time.sleep(2 ** attempt)
            except Exception as e:
                print(f"[VLM] 请求异常: {e}")
                if attempt < retry:
                    time.sleep(2 ** attempt)

        return None

    def _parse_response(self, text: str) -> dict:
        """解析 VLM 返回的 JSON"""
        import json
        text = text.strip()
        # 清理可能的 markdown 包裹
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 简单关键词回退
            covered = "盖着" in text and "没盖着" not in text
            person = "有" in text and "没有" not in text
            return {
                "person_detected": person,
                "covered": covered,
                "cover_level": "unknown",
                "description": text[:100],
            }

    def is_uncovered(self, image_path: str) -> tuple[bool, str]:
        """
        检查是否踢被子了

        Returns:
            (is_uncovered, description)
            is_uncovered=True 表示需要盖被子
        """
        result = self.analyze(image_path)
        if result is None:
            return False, "检测失败"

        person = result.get("person_detected", True)
        covered = result.get("covered", True)
        level = result.get("cover_level", "unknown")
        desc = result.get("description", "")

        # 判断逻辑
        is_uncovered = person and (not covered or level in ("not_covered", "chest_below"))

        status = "❌ 踢被子了!" if is_uncovered else "✅ 被子盖好了"
        print(f"[VLM] {status} | 有人:{person} 盖着:{covered} 位置:{level} | {desc}")

        return is_uncovered, desc


if __name__ == "__main__":
    import sys
    api_key = sys.argv[1] if len(sys.argv) > 1 else "your-api-key"
    img = sys.argv[2] if len(sys.argv) > 2 else "test.jpg"

    detector = BlanketDetector(api_key)
    uncovered, desc = detector.is_uncovered(img)
    print(f"\n结果: {'需要盖被子!' if uncovered else '无需操作'}")
    print(f"描述: {desc}")
