"""
デスクトップアプリ(app.py)の起動・計算スモークテスト（ヘッドレス）。

実ディスプレイが無くても QT_QPA_PLATFORM=offscreen で実行できる。
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_app_loads_and_computes():
    from PySide6 import QtWidgets

    from room_measure.synthetic import SyntheticRoom, render_panorama, true_corner_pixels
    import app as A

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    win = A.MainWindow()
    room = SyntheticRoom(4, 3, 2.5, 1.5)
    pano = render_panorama(room, 1024, 512)
    win._set_image(pano)

    floor, ceil = true_corner_pixels(room, 1024, 512)
    win.floor_pts = [tuple(p) for p in floor]
    win.ceiling_pts = [tuple(p) for p in ceil]
    win.spin_height.setValue(1.5)
    win.compute()

    d = win.last_dims
    assert d is not None
    assert abs(d.floor_area - 12.0) < 0.2
    assert d.ceiling_height is not None
    assert abs(d.ceiling_height - 2.5) < 0.1
    bw, bd = d.bounding_size
    assert abs(bw - 4.0) < 0.1 and abs(bd - 3.0) < 0.1
    _ = qapp  # 参照を保持


if __name__ == "__main__":
    test_app_loads_and_computes()
    print("✅ アプリのスモークテストに合格しました")
