"""
計測結果を可視化するモジュール。

- 部屋を真上から見た「間取り図」を画像として描く。
- 各壁の長さ・床面積・天井高を図中に書き込む。
"""

from __future__ import annotations

import cv2
import numpy as np

from .geometry import RoomDimensions


def render_floor_plan(
    dims: RoomDimensions,
    size: int = 800,
    margin: int = 80,
) -> np.ndarray:
    """部屋の間取り図（上から見た図）をBGR画像として返す。"""
    img = np.full((size, size, 3), 255, dtype=np.uint8)

    pts = dims.corners_xy
    if len(pts) < 2:
        cv2.putText(
            img, "no corners", (margin, size // 2),
            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2,
        )
        return img

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1e-6)
    span_y = max(max_y - min_y, 1e-6)
    span = max(span_x, span_y)
    scale = (size - 2 * margin) / span

    def to_px(p: tuple[float, float]) -> tuple[int, int]:
        # 中央寄せ。yは画像座標で下向きなので反転。
        cx = (p[0] - (min_x + max_x) / 2) * scale + size / 2
        cy = -(p[1] - (min_y + max_y) / 2) * scale + size / 2
        return int(round(cx)), int(round(cy))

    poly = np.array([to_px(p) for p in pts], dtype=np.int32)

    # 床（薄い水色）と壁（濃い線）
    cv2.fillPoly(img, [poly], (250, 230, 210))
    cv2.polylines(img, [poly], isClosed=True, color=(120, 60, 0), thickness=3)

    # カメラ位置（原点）に印
    ox, oy = to_px((0.0, 0.0))
    cv2.drawMarker(img, (ox, oy), (0, 0, 200), cv2.MARKER_TRIANGLE_UP, 18, 2)
    cv2.putText(img, "camera", (ox + 10, oy + 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 200), 1)

    # 各壁の長さを中点に書き込む
    n = len(pts)
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        mx, my = to_px(mid)
        cv2.putText(
            img, f"{dims.wall_lengths[i]:.2f} m", (mx - 30, my),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA,
        )

    # 角の番号
    for i, p in enumerate(pts):
        px, py = to_px(p)
        cv2.circle(img, (px, py), 4, (0, 0, 200), -1)
        cv2.putText(img, str(i + 1), (px + 6, py - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 200), 1)

    # 概要テキスト（左上）
    bw, bd = dims.bounding_size
    lines = [
        f"Area: {dims.floor_area:.2f} m2",
        f"Size (WxD): {bw:.2f} x {bd:.2f} m",
        f"Perimeter: {dims.perimeter:.2f} m",
        f"Camera height: {dims.camera_height:.2f} m",
    ]
    if dims.ceiling_height is not None:
        lines.append(f"Ceiling: {dims.ceiling_height:.2f} m")
    for i, line in enumerate(lines):
        cv2.putText(img, line, (10, 24 + i * 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (40, 40, 40), 1, cv2.LINE_AA)

    return img


def summary_text(dims: RoomDimensions) -> str:
    """計測結果を日本語のテキストにまとめる。"""
    bw, bd = dims.bounding_size
    lines = [
        "===== 部屋の寸法（計測結果） =====",
        f"カメラ高さ（基準）: {dims.camera_height:.2f} m",
        f"床面積           : {dims.floor_area:.2f} m^2",
        f"おおよそのサイズ : 幅 {bw:.2f} m × 奥行き {bd:.2f} m",
        f"周長             : {dims.perimeter:.2f} m",
    ]
    if dims.ceiling_height is not None:
        lines.append(f"天井高           : {dims.ceiling_height:.2f} m")
    lines.append("--- 各壁の長さ ---")
    for i, w in enumerate(dims.wall_lengths):
        lines.append(f"  壁{i + 1}: {w:.2f} m")
    return "\n".join(lines)
