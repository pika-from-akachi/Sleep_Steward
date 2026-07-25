"""
云端 VLM 物体检测器
使用 StepFun step-3.7-flash 多模态模型从图像中定位目标物体

用法:
    from detector import CloudDetector
    det = CloudDetector(api_key="...")
    bbox_norm, center_uv, label = det.detect(rgb_image, "饮料瓶")
    # bbox_norm: [x1, y1, x2, y2] 归一化到 0~1
    # center_uv: (cx, cy) 像素坐标
"""

import base64
import json
import time
import re
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Tuple

import requests


class CloudDetector:
    """基于 StepFun 云端多模态模型的物体检测器"""

    API_URL = "https://api.stepfun.com/v1/chat/completions"
    MODEL = "step-3.7-flash"

    SYSTEM_PROMPT = (
        "你是机器人抓取系统。在图像中找目标物体，输出**紧贴物体**的边界框。\n"
        "规则:\n"
        "- 严禁框机械臂自身的部件(夹爪/机械手/手指/臂杆/线缆等)! 这些不是目标, 只框独立的物体\n"
        "- 只框实体小物体(盒子/瓶/罐/水果等), 严禁框大面积的地面/桌面/墙面/阴影等背景区域\n"
        "- 边界框必须紧贴物体边缘, 不包含多余背景\n"
        "- 若目标颜色和大面积背景相近(如黑物体+黑地面), 只框那个**独立的实体小物体**, 不要框背景\n"
        "- 画面里可能有多个黑色物体, 选符合描述的那个独立物体(非机械臂部件)\n\n"
        "输出格式(只此一行):\n"
        "FOUND|x1|y1|x2|y2|物体名\n"
        "例如: FOUND|670|0|940|80|黄色罐子\n"
        "找不到: NOTFOUND\n"
        "坐标归一化到0-1000。只输出这一行, 不要其他文字。"
    )

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    def detect(
        self, image: np.ndarray, target: str, retry: int = 2
    ) -> Tuple[Optional[list], Optional[Tuple[int, int]], Optional[str]]:
        """
        在图像中检测目标物体

        Args:
            image: BGR numpy 数组 (H, W, 3)
            target: 目标物体中文描述，如 "红色的饮料瓶"、"苹果"
            retry: 重试次数

        Returns:
            (bbox_norm, center_uv, label)
            bbox_norm: [x1,y1,x2,y2] 归一化到 0~1，None 表示未检测到
            center_uv: (cx, cy) 像素坐标
            label: 物体标签
        """
        h, w = image.shape[:2]

        # 编码为 JPEG base64，灰度图先增强对比度
        if len(image.shape) == 2:
            image = cv2.equalizeHist(image.astype(np.uint8))
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        _, jpg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
        image_b64 = base64.b64encode(jpg.tobytes()).decode("utf-8")

        user_text = f"请在图像中找到: {target}"

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
                                "url": f"data:image/jpeg;base64,{image_b64}",
                                "detail": "low",
                            },
                        },
                        {"type": "text", "text": user_text},
                    ],
                },
            ],
            "temperature": 0.1,
            "max_tokens": 200,
        }

        for attempt in range(retry + 1):
            try:
                resp = self.session.post(self.API_URL, json=payload, timeout=20)
                if resp.status_code == 200:
                    msg = resp.json()["choices"][0]["message"]
                    raw = msg.get("content", "") or msg.get("reasoning", "")
                    result = self._parse(raw, w, h)
                    if result:
                        bbox, center_uv, label = result
                        area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
                        if area > 0.20:
                            print(f"[Detector] ⚠️ bbox 面积 {area:.2f} 过大 (疑似背景: 地面/桌面/墙面), 丢弃并重试")
                            continue   # 重试, 让 VLM 重新找小物体
                        print(f"[Detector] 找到 '{label}' bbox={[round(v,3) for v in bbox]}, center={center_uv}")
                        return bbox, center_uv, label
                else:
                    print(f"[Detector] API 错误 {resp.status_code}: {resp.text[:200]}")
            except Exception as e:
                print(f"[Detector] 请求异常: {e}")

            if attempt < retry:
                time.sleep(2 ** attempt)

        print("[Detector] 所有重试失败")
        return None, None, None

    def _parse(self, text: str, img_w: int, img_h: int):
        """解析 VLM 返回，支持多种格式"""
        text = text.strip()
        # 清理 markdown
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:]) if len(lines) > 1 else text
            if text.endswith("```"):
                text = text[:-3]
        text = text.strip()

        # 格式1: FOUND|x1|y1|x2|y2|label
        pipe = re.match(r'FOUND\s*[|/]\s*(\d+)\s*[|/]\s*(\d+)\s*[|/]\s*(\d+)\s*[|/]\s*(\d+)\s*[|/]?\s*(.*)', text, re.IGNORECASE)
        if pipe:
            x1, y1, x2, y2 = int(pipe[1]), int(pipe[2]), int(pipe[3]), int(pipe[4])
            label = pipe[5].strip() or "object"
            bbox = [x1/1000.0, y1/1000.0, x2/1000.0, y2/1000.0]
            center_uv = (int((bbox[0]+bbox[2])/2*img_w), int((bbox[1]+bbox[3])/2*img_h))
            print(f"[Detector] pipe格式: {[round(v,3) for v in bbox]} {label}")
            return bbox, center_uv, label

        if re.search(r'NOTFOUND|not.found', text, re.IGNORECASE):
            print("[Detector] 模型报告未找到")
            return None

        # 格式2: JSON
        json_match = re.search(r"\{[^}]+\}", text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                if data.get("found") is False:
                    return None
                for fmt in [["x1","y1","x2","y2"], ["bbox_norm_1000"]]:
                    try:
                        if fmt[0] == "bbox_norm_1000" and fmt[0] in data:
                            vals = data["bbox_norm_1000"]
                            bbox = [v/1000.0 for v in vals]
                        elif all(k in data for k in fmt):
                            bbox = [data[k]/1000.0 for k in fmt]
                        else:
                            continue
                        center_uv = (int((bbox[0]+bbox[2])/2*img_w), int((bbox[1]+bbox[3])/2*img_h))
                        return bbox, center_uv, data.get("label", "object")
                    except: pass
            except json.JSONDecodeError: pass

        # 格式3: 自然语言 "x1: 约 670" → 去掉中文再匹配 (带分隔符)
        clean = re.sub(r'[约左右大约大概在]', ' ', text)
        coords = re.findall(r'(?:x1|x2|y1|y2)\s*[=:：\s]*\s*(\d+)', clean)
        if len(coords) >= 4:
            x1, y1, x2, y2 = int(coords[0]), int(coords[1]), int(coords[2]), int(coords[3])
            bbox = [x1/1000.0, y1/1000.0, x2/1000.0, y2/1000.0]
            center_uv = (int((bbox[0]+bbox[2])/2*img_w), int((bbox[1]+bbox[3])/2*img_h))
            print(f"[Detector] 从NL提取: bbox={[round(v,3) for v in bbox]}")
            return bbox, center_uv, "object"

        # 格式3b: 模型输出中文自然语言但坐标分散在不同句子中
        # 如 "x1在670左右，y1在380左右，x2在840左右，y2在560左右"
        # 先清理所有中文修饰词，再找 x1/x2/y1/y2 标签后的首个数字
        clean2 = re.sub(r'[约左右大约大概在是，,。.\s]+', ' ', text)
        coords2 = re.findall(r'[xy](\d)\s*[^\d]*?(\d{2,4})', clean2)
        if len(coords2) >= 4:
            nums = {}
            for suffix, val in coords2:
                key = f"{'x' if suffix in '12' else 'y'}{suffix}"
                if key not in nums:
                    nums[key] = int(val)
            if all(k in nums for k in ['x1','y1','x2','y2']):
                bbox = [nums['x1']/1000.0, nums['y1']/1000.0,
                        nums['x2']/1000.0, nums['y2']/1000.0]
                center_uv = (int((bbox[0]+bbox[2])/2*img_w), int((bbox[1]+bbox[3])/2*img_h))
                print(f"[Detector] NL格式3b: bbox={[round(v,3) for v in bbox]}")
                return bbox, center_uv, "object"

        # 格式4: 小数坐标 "x=0.67 到 x=0.94"
        x_nums = re.findall(r'x\s*[=:：\s]*(\d*\.?\d+)', text)
        y_nums = re.findall(r'y\s*[=:：]\s*(\d*\.?\d+)', text)
        if len(x_nums) >= 2 and len(y_nums) >= 2:
            bbox = [float(x_nums[0]), float(y_nums[0]), float(x_nums[1]), float(y_nums[1])]
            # 如果值小于1，当做0-1归一化
            if max(bbox) <= 1.0:
                pass  # 已经是0-1
            else:
                bbox = [v/1000.0 for v in bbox]
            center_uv = (int((bbox[0]+bbox[2])/2*img_w), int((bbox[1]+bbox[3])/2*img_h))
            print(f"[Detector] 小数坐标: {[round(v,3) for v in bbox]}")
            return bbox, center_uv, "object"

        # 格式6: 兜底 — 在文本中找 4 个连续的在合法像素范围的数字
        all_nums = re.findall(r'\b(\d{2,4})\b', text)
        valid = [int(n) for n in all_nums if 200 <= int(n) <= 950]
        if len(valid) >= 4:
            # 找最接近的顺序组合
            for i in range(len(valid) - 3):
                x1, y1, x2, y2 = valid[i], valid[i+1], valid[i+2], valid[i+3]
                if x1 < x2 and y1 < y2:  # 合理的 bbox
                    bbox = [x1/1000.0, y1/1000.0, x2/1000.0, y2/1000.0]
                    center_uv = (int((bbox[0]+bbox[2])/2*img_w), int((bbox[1]+bbox[3])/2*img_h))
                    print(f"[Detector] 兜底提取: bbox={[round(v,3) for v in bbox]}")
                    return bbox, center_uv, "object"

        print(f"[Detector] 解析失败: {text[:200]}")
        return None


if __name__ == "__main__":
    import sys
    api_key = sys.argv[1] if len(sys.argv) > 1 else "your-api-key"
    img_path = sys.argv[2] if len(sys.argv) > 2 else "/tmp/test_rgb.jpg"

    det = CloudDetector(api_key)
    img = cv2.imread(img_path)
    if img is None:
        print(f"无法读取图片: {img_path}")
        sys.exit(1)

    bbox, center, label = det.detect(img, "饮料瓶")
    if bbox:
        print(f"检测成功: {label}, bbox={bbox}, center_px={center}")
        # 画框验证
        h, w = img.shape[:2]
        x1, y1 = int(bbox[0] * w), int(bbox[1] * h)
        x2, y2 = int(bbox[2] * w), int(bbox[3] * h)
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.circle(img, center, 5, (0, 0, 255), -1)
        cv2.putText(img, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imwrite("/tmp/detection_result.jpg", img)
        print("结果保存到 /tmp/detection_result.jpg")
