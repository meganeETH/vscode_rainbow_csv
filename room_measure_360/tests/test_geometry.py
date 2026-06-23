"""
geometry モジュールの検証テスト。

既知の部屋の3D座標 → パノラマ上のピクセルへ投影 → そのピクセルから
寸法を逆算し、元の寸法が復元できることを確認する（往復テスト）。
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from room_measure import geometry as g


WIDTH, HEIGHT = 4096, 2048


def project_floor_corner(X, Y, camera_height):
    """床上の点(X, Y) を、カメラ(原点, 高さh)から見たパノラマ画素へ投影する。"""
    Z = -camera_height  # 床は z = -h
    theta = math.atan2(Y, X)
    r = math.hypot(X, Y)
    phi = math.atan2(Z, r)  # 下向きなので負
    return g.angles_to_pixel(theta, phi, WIDTH, HEIGHT)


def project_ceiling_corner(X, Y, camera_height, ceiling_height):
    """天井の角（床の角の真上、高さ=天井高）をパノラマ画素へ投影する。"""
    Z = ceiling_height - camera_height  # 天井は z = (天井高 - h)、正
    theta = math.atan2(Y, X)
    r = math.hypot(X, Y)
    phi = math.atan2(Z, r)  # 上向きなので正
    return g.angles_to_pixel(theta, phi, WIDTH, HEIGHT)


def test_pixel_angle_roundtrip():
    """ピクセル→角→ピクセルが元に戻ることを確認。"""
    for x, y in [(0, 0), (1000, 500), (2048, 1024), (4095, 2047)]:
        theta, phi = g.pixel_to_angles(x, y, WIDTH, HEIGHT)
        x2, y2 = g.angles_to_pixel(theta, phi, WIDTH, HEIGHT)
        assert abs(x - x2) < 1e-6, (x, x2)
        assert abs(y - y2) < 1e-6, (y, y2)


def test_rectangular_room_roundtrip():
    """4m×3m×高さ2.5m、カメラ高さ1.5m の長方形の部屋を復元する。"""
    camera_height = 1.5
    ceiling_height = 2.5
    # 部屋の四隅（カメラを部屋の中央に置く）。幅4m(X方向)×奥行き3m(Y方向)。
    true_corners = [
        (2.0, 1.5),
        (-2.0, 1.5),
        (-2.0, -1.5),
        (2.0, -1.5),
    ]

    floor_px = [project_floor_corner(X, Y, camera_height) for (X, Y) in true_corners]
    ceil_px = [
        project_ceiling_corner(X, Y, camera_height, ceiling_height)
        for (X, Y) in true_corners
    ]

    dims = g.compute_room_dimensions(
        floor_px, WIDTH, HEIGHT, camera_height, ceiling_corner_pixels=ceil_px
    )

    # 復元した角座標が元の座標と一致するか
    for (rx, ry), (tx, ty) in zip(dims.corners_xy, true_corners):
        assert abs(rx - tx) < 0.02, (rx, tx)
        assert abs(ry - ty) < 0.02, (ry, ty)

    # 壁の長さ: 4, 3, 4, 3
    expected_walls = [4.0, 3.0, 4.0, 3.0]
    for got, exp in zip(dims.wall_lengths, expected_walls):
        assert abs(got - exp) < 0.05, (got, exp)

    # 床面積 12 m^2, 周長 14 m
    assert abs(dims.floor_area - 12.0) < 0.1, dims.floor_area
    assert abs(dims.perimeter - 14.0) < 0.1, dims.perimeter

    # 天井高 2.5 m
    assert dims.ceiling_height is not None
    assert abs(dims.ceiling_height - 2.5) < 0.05, dims.ceiling_height

    # 囲み長方形サイズ 4 x 3
    bw, bd = dims.bounding_size
    assert abs(bw - 4.0) < 0.05 and abs(bd - 3.0) < 0.05, (bw, bd)


def test_scale_proportional_to_camera_height():
    """カメラ高さを2倍にすると、推定寸法も2倍になる（スケールは高さに比例）。"""
    camera_height = 1.5
    true_corners = [(2.0, 1.5), (-2.0, 1.5), (-2.0, -1.5), (2.0, -1.5)]
    floor_px = [project_floor_corner(X, Y, camera_height) for (X, Y) in true_corners]

    d1 = g.compute_room_dimensions(floor_px, WIDTH, HEIGHT, camera_height)
    d2 = g.compute_room_dimensions(floor_px, WIDTH, HEIGHT, camera_height * 2)

    assert abs(d2.floor_area / d1.floor_area - 4.0) < 0.01  # 面積は2^2=4倍


if __name__ == "__main__":
    test_pixel_angle_roundtrip()
    test_rectangular_room_roundtrip()
    test_scale_proportional_to_camera_height()
    print("✅ すべてのテストに合格しました")
