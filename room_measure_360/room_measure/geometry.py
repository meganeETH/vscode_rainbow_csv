"""
360度パノラマ画像の幾何計算モジュール。

正距円筒図法（equirectangular）のパノラマ画像上のピクセル座標と、
カメラを原点とした3D方向ベクトル（視線）を相互に変換します。
さらに「カメラの高さ」を1つの基準として使い、床・天井・壁の
実寸（メートル）を計算します。

座標系:
  - カメラを原点(0,0,0)に置く。
  - z 軸を上向き（天井方向が +z、床方向が -z）とする。
  - 床は平面 z = -h （h = カメラの床からの高さ[m]）。

正距円筒図法のピクセル(x, y) と 球面角(θ, φ) の対応:
  画像サイズ W x H に対して、
    経度(yaw)   θ = (x / W) * 2π - π        範囲 [-π, +π]
    緯度(pitch) φ = π/2 - (y / H) * π        範囲 [+π/2, -π/2]
  すなわち
    y = 0    → φ = +π/2 （真上・天頂）
    y = H/2  → φ = 0    （水平線）
    y = H    → φ = -π/2 （真下・天底）
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# --------------------------------------------------------------------------
# ピクセル ⇔ 球面角 ⇔ 3D方向ベクトル の変換
# --------------------------------------------------------------------------
def pixel_to_angles(x: float, y: float, width: int, height: int) -> tuple[float, float]:
    """正距円筒パノラマのピクセル(x, y)を球面角(θ経度, φ緯度)[ラジアン]に変換する。"""
    theta = (x / width) * 2.0 * math.pi - math.pi
    phi = math.pi / 2.0 - (y / height) * math.pi
    return theta, phi


def angles_to_pixel(theta: float, phi: float, width: int, height: int) -> tuple[float, float]:
    """球面角(θ, φ)[ラジアン]を正距円筒パノラマのピクセル(x, y)に変換する。"""
    x = (theta + math.pi) / (2.0 * math.pi) * width
    y = (math.pi / 2.0 - phi) / math.pi * height
    return x, y


def angles_to_direction(theta: float, phi: float) -> tuple[float, float, float]:
    """球面角(θ, φ)から単位方向ベクトル(dx, dy, dz)を返す（z上向き）。"""
    dx = math.cos(phi) * math.cos(theta)
    dy = math.cos(phi) * math.sin(theta)
    dz = math.sin(phi)
    return dx, dy, dz


# --------------------------------------------------------------------------
# 実寸の計算（カメラ高さ h を基準に使う）
# --------------------------------------------------------------------------
def floor_point_to_xy(
    x: float, y: float, width: int, height: int, camera_height: float
) -> tuple[float, float]:
    """
    床と壁の境界（床の角）のピクセルから、その点の床平面上の実座標(X, Y)[m]を求める。

    視線 φ<0（水平線より下）を床平面 z=-h と交差させる。
      水平距離 r = h / |tan(φ)|
      X = r·cos(θ),  Y = r·sin(θ)
    """
    theta, phi = pixel_to_angles(x, y, width, height)
    if phi >= 0:
        raise ValueError(
            "床の点は水平線より下（画像の下半分）にある必要があります。"
            f"（緯度 φ={math.degrees(phi):.1f}°）"
        )
    r = camera_height / abs(math.tan(phi))
    return r * math.cos(theta), r * math.sin(theta)


def horizontal_distance(x: float, y: float, width: int, height: int, camera_height: float) -> float:
    """床の角ピクセルから、カメラ直下までの水平距離[m]を返す。"""
    fx, fy = floor_point_to_xy(x, y, width, height, camera_height)
    return math.hypot(fx, fy)


def ceiling_height_from_point(
    x: float,
    y: float,
    width: int,
    height: int,
    camera_height: float,
    horizontal_dist: float,
) -> float:
    """
    天井と壁の境界（天井の角）のピクセルと、その壁までの水平距離から、
    部屋全体の天井高（床から天井まで）[m]を求める。

      カメラから天井の角までの高さ = r · tan(φ)   （φ>0）
      天井高 = カメラ高さ h + r · tan(φ)
    """
    _theta, phi = pixel_to_angles(x, y, width, height)
    if phi <= 0:
        raise ValueError(
            "天井の点は水平線より上（画像の上半分）にある必要があります。"
            f"（緯度 φ={math.degrees(phi):.1f}°）"
        )
    return camera_height + horizontal_dist * math.tan(phi)


# --------------------------------------------------------------------------
# 多角形（部屋の床の輪郭）に関する計算
# --------------------------------------------------------------------------
@dataclass
class RoomDimensions:
    """計算された部屋の寸法一式。"""

    corners_xy: list[tuple[float, float]]  # 床の各角の実座標[m]
    wall_lengths: list[float]              # 各壁の長さ[m]（隣り合う角の距離）
    floor_area: float                      # 床面積[m^2]
    perimeter: float                       # 周長[m]
    ceiling_height: float | None           # 天井高[m]（不明ならNone）
    camera_height: float                   # 計算に使ったカメラ高さ[m]

    @property
    def bounding_size(self) -> tuple[float, float]:
        """床の輪郭を囲む長方形の幅・奥行き[m]（おおまかな部屋サイズの目安）。"""
        xs = [p[0] for p in self.corners_xy]
        ys = [p[1] for p in self.corners_xy]
        return (max(xs) - min(xs), max(ys) - min(ys))


def polygon_area(points: list[tuple[float, float]]) -> float:
    """多角形の面積[m^2]をシューレース公式で求める。"""
    n = len(points)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def polygon_perimeter(points: list[tuple[float, float]]) -> float:
    """多角形の周長[m]を求める。"""
    n = len(points)
    if n < 2:
        return 0.0
    total = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        total += math.hypot(x2 - x1, y2 - y1)
    return total


def wall_lengths(points: list[tuple[float, float]]) -> list[float]:
    """隣り合う角どうしの距離（各壁の長さ）[m]のリストを返す。"""
    n = len(points)
    lengths = []
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        lengths.append(math.hypot(x2 - x1, y2 - y1))
    return lengths


def compute_room_dimensions(
    floor_corner_pixels: list[tuple[float, float]],
    width: int,
    height: int,
    camera_height: float,
    ceiling_corner_pixels: list[tuple[float, float]] | None = None,
) -> RoomDimensions:
    """
    床の角ピクセル群（必要なら天井の角ピクセル群も）から部屋の寸法一式を計算する。

    Args:
        floor_corner_pixels: 床と壁の境界の角ピクセル[(x, y), ...]（部屋を一周する順）。
        width, height: パノラマ画像のサイズ。
        camera_height: カメラの床からの高さ[m]（唯一の実寸基準）。
        ceiling_corner_pixels: 天井と壁の境界の角ピクセル。床の角と同じ順・同数なら
            各壁の天井高を推定し平均する。Noneなら天井高はNone。
    """
    corners_xy = [
        floor_point_to_xy(x, y, width, height, camera_height)
        for (x, y) in floor_corner_pixels
    ]

    ceiling = None
    if ceiling_corner_pixels:
        heights = []
        for i, (cx, cy) in enumerate(ceiling_corner_pixels):
            if i < len(corners_xy):
                r = math.hypot(*corners_xy[i])
                heights.append(
                    ceiling_height_from_point(cx, cy, width, height, camera_height, r)
                )
        if heights:
            ceiling = sum(heights) / len(heights)

    return RoomDimensions(
        corners_xy=corners_xy,
        wall_lengths=wall_lengths(corners_xy),
        floor_area=polygon_area(corners_xy),
        perimeter=polygon_perimeter(corners_xy),
        ceiling_height=ceiling,
        camera_height=camera_height,
    )
