"""生成 ArUco 标记图像 — 用于手眼标定。

生成 DICT_5X5_50 ID=0 标记, 保存为 PNG。
打印后裁剪为边长 0.10m (标记黑方块的实际物理尺寸)。

用法:
    python3 generate_marker.py                 # 默认: 500px, 0.10m, ID=0
    python3 generate_marker.py --id 5 --size 0.05  # 自定义
"""
import argparse
import os
import cv2
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(SCRIPT_DIR, "calibration")
os.makedirs(OUT_DIR, exist_ok=True)


def generate(marker_id=0, marker_size_m=0.10, pixel_size=500, dict_id=cv2.aruco.DICT_5X5_50):
    """生成 ArUco 标记

    Args:
        marker_id: 标记 ID
        marker_size_m: 实际物理边长 (米) — 用于 reference
        pixel_size: 图像像素尺寸
        dict_id: ArUco 字典
    """
    dic = cv2.aruco.getPredefinedDictionary(dict_id)
    img = cv2.aruco.generateImageMarker(dic, marker_id, pixel_size, borderBits=2)

    # 原始标记
    out_raw = os.path.join(OUT_DIR, f"aruco_id{marker_id}.png")
    cv2.imwrite(out_raw, img)

    # 带白色边框版本 (方便打印和裁剪)
    border = 100
    h, w = img.shape
    padded = np.ones((h + 2 * border, w + 2 * border), dtype=np.uint8) * 255
    padded[border:border + h, border:border + w] = img
    out_print = os.path.join(OUT_DIR, f"aruco_id{marker_id}_print.png")
    cv2.imwrite(out_print, padded)

    # 在打印版上添加文字说明
    text_img = cv2.cvtColor(padded, cv2.COLOR_GRAY2BGR)
    info_lines = [
        f"ArUco 5x5_50 ID={marker_id}",
        f"Black square: {marker_size_m*100:.0f}mm x {marker_size_m*100:.0f}mm",
        f"Print & cut to {marker_size_m*100:.0f}mm square",
    ]
    for i, line in enumerate(info_lines):
        cv2.putText(text_img, line, (15, 30 + i * 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    out_annotated = os.path.join(OUT_DIR, f"aruco_id{marker_id}_annotated.png")
    cv2.imwrite(out_annotated, text_img)

    print(f"✅ 标记已生成:")
    print(f"   原始:     {out_raw}")
    print(f"   打印版:   {out_print}")
    print(f"   注释版:   {out_annotated}")
    print(f"")
    print(f"   📐 标记实际边长 (黑方块): {marker_size_m:.2f} m = {marker_size_m*1000:.0f} mm")
    print(f"   打印后请裁剪为 {marker_size_m*1000:.0f}mm × {marker_size_m*1000:.0f}mm")
    print(f"   确保 aruco_detect.py 中的 MARKER_SIZE = {marker_size_m}")

    return out_print


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ArUco 标记生成器")
    parser.add_argument("--id", type=int, default=0, help="标记 ID")
    parser.add_argument("--size", type=float, default=0.10, help="标记实际边长 (米)")
    parser.add_argument("--pixels", type=int, default=500, help="图像像素尺寸")
    args = parser.parse_args()

    generate(args.id, args.size, args.pixels)
