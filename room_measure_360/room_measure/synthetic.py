"""
検証・デモ用の合成データ生成モジュール。

既知サイズの直方体の部屋を、正距円筒図法のパノラマ画像として
レイキャストで描画する。実機の360度動画が無くても、パイプライン
全体（フレーム抽出→計測→間取り図）を検証できる。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from . import geometry as g


@dataclass
class SyntheticRoom:
    width_m: float = 4.0     # X方向の幅[m]
    depth_m: float = 3.0     # Y方向の奥行き[m]
    height_m: float = 2.5    # 天井高[m]
    camera_height_m: float = 1.5  # 床からのカメラ高さ[m]
    # カメラは床面では部屋の中央に置く。

    def floor_corners_world(self) -> list[tuple[float, float]]:
        """床の四隅の実座標(X, Y)[m]（カメラを中央とする）。"""
        hw, hd = self.width_m / 2, self.depth_m / 2
        return [(hw, hd), (-hw, hd), (-hw, -hd), (hw, -hd)]


def render_panorama(room: SyntheticRoom, width: int = 2048, height: int = 1024) -> np.ndarray:
    """直方体の部屋をレイキャストして正距円筒パノラマ(BGR)を描く。"""
    h = room.camera_height_m
    hw, hd = room.width_m / 2, room.depth_m / 2
    z_floor = -h
    z_ceil = room.height_m - h

    # 各ピクセルの角度→方向ベクトル
    ys, xs = np.mgrid[0:height, 0:width]
    theta = (xs / width) * 2.0 * math.pi - math.pi
    phi = math.pi / 2.0 - (ys / height) * math.pi
    dx = np.cos(phi) * np.cos(theta)
    dy = np.cos(phi) * np.sin(theta)
    dz = np.sin(phi)

    best_t = np.full((height, width), np.inf)
    surface = np.zeros((height, width), dtype=np.int32)  # 1床2天井3-6壁
    u = np.zeros((height, width))  # テクスチャ座標
    v = np.zeros((height, width))

    eps = 1e-9
    # レイが面と平行のとき 0除算で inf/nan が出るが、結果は hit_mask で除外するため無視する
    np.seterr(divide="ignore", invalid="ignore")

    def consider(t, hit_mask, sid, uu, vv):
        nonlocal best_t, surface, u, v
        m = hit_mask & (t > eps) & (t < best_t)
        best_t = np.where(m, t, best_t)
        surface = np.where(m, sid, surface)
        u = np.where(m, uu, u)
        v = np.where(m, vv, v)

    # 床 z=z_floor
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (z_floor) / dz
    px, py = t * dx, t * dy
    consider(t, (dz < -eps) & (np.abs(px) <= hw) & (np.abs(py) <= hd), 1, px, py)

    # 天井 z=z_ceil
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (z_ceil) / dz
    px, py = t * dx, t * dy
    consider(t, (dz > eps) & (np.abs(px) <= hw) & (np.abs(py) <= hd), 2, px, py)

    # 壁 X=+hw, X=-hw, Y=+hd, Y=-hd
    for sid, (axis, val) in enumerate(
        [("x", hw), ("x", -hw), ("y", hd), ("y", -hd)], start=3
    ):
        if axis == "x":
            with np.errstate(divide="ignore", invalid="ignore"):
                t = val / dx
            py, pz = t * dy, t * dz
            hit = (np.sign(dx) == np.sign(val)) & (np.abs(py) <= hd) & (pz >= z_floor) & (pz <= z_ceil)
            consider(t, hit, sid, py, pz)
        else:
            with np.errstate(divide="ignore", invalid="ignore"):
                t = val / dy
            px, pz = t * dx, t * dz
            hit = (np.sign(dy) == np.sign(val)) & (np.abs(px) <= hw) & (pz >= z_floor) & (pz <= z_ceil)
            consider(t, hit, sid, px, pz)

    # 色付け（市松模様で奥行き感を出す）
    base_colors = {
        1: (170, 190, 200),  # 床（薄茶）
        2: (240, 235, 230),  # 天井（白っぽい）
        3: (200, 170, 150),  # 壁
        4: (190, 160, 150),
        5: (180, 170, 160),
        6: (170, 160, 170),
    }
    img = np.zeros((height, width, 3), dtype=np.uint8)
    checker = (((np.floor(u * 2) + np.floor(v * 2)).astype(int)) % 2)
    for sid, col in base_colors.items():
        mask = surface == sid
        c = np.array(col, dtype=np.int16)
        shade = np.where(checker == 0, 0, -25)
        for ch in range(3):
            img[..., ch] = np.where(mask, np.clip(c[ch] + shade, 0, 255), img[..., ch])

    return img


def true_corner_pixels(
    room: SyntheticRoom, width: int, height: int
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """部屋の床の角・天井の角の正解ピクセル位置を返す（検証用）。"""
    floor_px, ceil_px = [], []
    for (X, Y) in room.floor_corners_world():
        theta = math.atan2(Y, X)
        r = math.hypot(X, Y)
        phi_f = math.atan2(-room.camera_height_m, r)
        phi_c = math.atan2(room.height_m - room.camera_height_m, r)
        floor_px.append(g.angles_to_pixel(theta, phi_f, width, height))
        ceil_px.append(g.angles_to_pixel(theta, phi_c, width, height))
    return floor_px, ceil_px


def write_demo_video(
    path: str, room: SyntheticRoom, width: int = 2048, height: int = 1024,
    seconds: float = 2.0, fps: int = 10,
) -> None:
    """合成パノラマを少し揺らしながら繰り返し、デモ用の360度動画(mp4)を書き出す。"""
    pano = render_panorama(room, width, height)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (width, height))
    n = int(seconds * fps)
    rng = np.random.default_rng(0)
    for i in range(n):
        frame = pano.copy()
        # 数フレームだけ意図的にブレさせ、シャープ選別が効くか確認できるようにする
        if i % 5 == 1:
            k = 9
            frame = cv2.GaussianBlur(frame, (k, k), 0)
        else:
            noise = rng.integers(-3, 4, frame.shape, dtype=np.int16)
            frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        writer.write(frame)
    writer.release()
