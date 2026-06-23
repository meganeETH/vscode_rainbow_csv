#!/usr/bin/env python3
"""
360度パノラマから部屋の寸法を計測するデスクトップアプリ（PySide6）。

操作の流れ:
  1. 「動画を開く」または「画像を開く」でパノラマを読み込む
     （動画の場合は自動で最も鮮明なフレームを選ぶ）
  2. カメラの高さ[m]を入力（撮影時の三脚などの床からの高さ）
  3. 「床の角」モードで、床と壁が接する角を部屋を一周する順にクリック
  4. （任意）「天井の角」モードで、天井と壁が接する角を同じ順にクリック
  5. 「計算する」を押すと、寸法と間取り図が表示される
  6. 「間取り図を保存」「結果をCSV保存」で書き出し

このファイル単体で起動できる: python3 app.py
"""

from __future__ import annotations

import csv
import sys

import cv2
import numpy as np

from PySide6 import QtCore, QtGui, QtWidgets

from room_measure import geometry as g
from room_measure import video as v
from room_measure import render


def cv_to_qpixmap(img_bgr: np.ndarray) -> QtGui.QPixmap:
    """OpenCVのBGR画像をQPixmapに変換する。"""
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    qimg = QtGui.QImage(rgb.data, w, h, 3 * w, QtGui.QImage.Format.Format_RGB888)
    return QtGui.QPixmap.fromImage(qimg.copy())


class PanoramaView(QtWidgets.QGraphicsView):
    """パノラマを表示し、クリックで角の点を追加できるビュー。"""

    pointClicked = QtCore.Signal(float, float)  # 画像座標(x, y)

    def __init__(self):
        super().__init__()
        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item: QtWidgets.QGraphicsPixmapItem | None = None
        self._marker_items: list[QtWidgets.QGraphicsItem] = []
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

    def set_image(self, img_bgr: np.ndarray) -> None:
        self._scene.clear()
        self._marker_items.clear()
        pm = cv_to_qpixmap(img_bgr)
        self._pixmap_item = self._scene.addPixmap(pm)
        self._scene.setSceneRect(QtCore.QRectF(pm.rect()))
        self.fitInView(self._pixmap_item, QtCore.Qt.AspectRatioMode.KeepAspectRatio)

    def has_image(self) -> bool:
        return self._pixmap_item is not None

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if (event.button() == QtCore.Qt.MouseButton.LeftButton
                and event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier
                and self._pixmap_item is not None):
            # Shift+クリックで点を追加（通常クリックはパン操作に使う）
            sp = self.mapToScene(event.position().toPoint())
            self.pointClicked.emit(sp.x(), sp.y())
            return
        super().mousePressEvent(event)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        # ホイールで拡大縮小
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        self.scale(factor, factor)

    def redraw_markers(self, floor_pts, ceiling_pts) -> None:
        for it in self._marker_items:
            self._scene.removeItem(it)
        self._marker_items.clear()
        if self._pixmap_item is None:
            return
        r = max(4.0, self._scene.width() / 300)
        for i, (x, y) in enumerate(floor_pts):
            self._add_marker(x, y, r, QtGui.QColor(220, 30, 30), f"F{i + 1}")
        for i, (x, y) in enumerate(ceiling_pts):
            self._add_marker(x, y, r, QtGui.QColor(30, 80, 230), f"C{i + 1}")

    def _add_marker(self, x, y, r, color, label) -> None:
        pen = QtGui.QPen(color)
        pen.setWidthF(r / 3)
        ell = self._scene.addEllipse(x - r, y - r, 2 * r, 2 * r, pen,
                                     QtGui.QBrush(color))
        txt = self._scene.addText(label)
        txt.setDefaultTextColor(color)
        txt.setPos(x + r, y - 2 * r)
        self._marker_items.extend([ell, txt])


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("360度カメラ 部屋寸法計測ツール")
        self.resize(1280, 760)

        self.image_bgr: np.ndarray | None = None
        self.floor_pts: list[tuple[float, float]] = []
        self.ceiling_pts: list[tuple[float, float]] = []
        self.add_mode = "floor"  # "floor" or "ceiling"
        self.last_dims: g.RoomDimensions | None = None
        self.last_plan: np.ndarray | None = None

        self.view = PanoramaView()
        self.view.pointClicked.connect(self.on_point_clicked)

        self._build_ui()
        self._update_status()

    # ---------------- UI 構築 ----------------
    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)

        # 左: パノラマ表示
        layout.addWidget(self.view, stretch=3)

        # 右: 操作パネル
        panel = QtWidgets.QVBoxLayout()
        layout.addLayout(panel, stretch=2)

        # 読み込み
        btn_video = QtWidgets.QPushButton("① 360度動画を開く")
        btn_video.clicked.connect(self.open_video)
        btn_image = QtWidgets.QPushButton("① パノラマ画像を開く")
        btn_image.clicked.connect(self.open_image)
        panel.addWidget(btn_video)
        panel.addWidget(btn_image)

        # カメラ高さ
        hl = QtWidgets.QHBoxLayout()
        hl.addWidget(QtWidgets.QLabel("② カメラの高さ[m]:"))
        self.spin_height = QtWidgets.QDoubleSpinBox()
        self.spin_height.setRange(0.1, 5.0)
        self.spin_height.setSingleStep(0.05)
        self.spin_height.setValue(1.50)
        self.spin_height.valueChanged.connect(self.recompute_if_ready)
        hl.addWidget(self.spin_height)
        panel.addLayout(hl)

        # 角の追加モード
        panel.addWidget(QtWidgets.QLabel("③ Shift+クリックで角を追加:"))
        self.radio_floor = QtWidgets.QRadioButton("床の角（赤）")
        self.radio_ceiling = QtWidgets.QRadioButton("天井の角（青）")
        self.radio_floor.setChecked(True)
        self.radio_floor.toggled.connect(self._on_mode_changed)
        panel.addWidget(self.radio_floor)
        panel.addWidget(self.radio_ceiling)

        # 点の操作
        bl = QtWidgets.QHBoxLayout()
        btn_undo = QtWidgets.QPushButton("最後の点を取消")
        btn_undo.clicked.connect(self.undo_point)
        btn_clear = QtWidgets.QPushButton("全点クリア")
        btn_clear.clicked.connect(self.clear_points)
        bl.addWidget(btn_undo)
        bl.addWidget(btn_clear)
        panel.addLayout(bl)

        # 計算
        btn_calc = QtWidgets.QPushButton("④ 計算する")
        btn_calc.setStyleSheet("font-weight:bold; padding:8px;")
        btn_calc.clicked.connect(self.compute)
        panel.addWidget(btn_calc)

        # 結果表示
        self.result_text = QtWidgets.QPlainTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(220)
        panel.addWidget(self.result_text)

        # 間取り図プレビュー
        self.plan_label = QtWidgets.QLabel("ここに間取り図が表示されます")
        self.plan_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.plan_label.setMinimumHeight(240)
        self.plan_label.setStyleSheet("border:1px solid #aaa;")
        panel.addWidget(self.plan_label)

        # 保存
        sl = QtWidgets.QHBoxLayout()
        btn_save_plan = QtWidgets.QPushButton("間取り図を保存")
        btn_save_plan.clicked.connect(self.save_plan)
        btn_save_csv = QtWidgets.QPushButton("結果をCSV保存")
        btn_save_csv.clicked.connect(self.save_csv)
        sl.addWidget(btn_save_plan)
        sl.addWidget(btn_save_csv)
        panel.addLayout(sl)

        self.status = self.statusBar()

    # ---------------- 読み込み ----------------
    def open_video(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "360度動画を選択", "", "動画 (*.mp4 *.mov *.avi *.mkv);;すべて (*)"
        )
        if not path:
            return
        try:
            info = v.probe_video(path)
            frames = v.select_sharpest_frames(path, n_return=1)
        except Exception as e:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "エラー", f"動画の読み込みに失敗しました:\n{e}")
            return
        if not info["is_equirectangular"]:
            QtWidgets.QMessageBox.warning(
                self, "確認",
                "この動画は横:縦が2:1ではありません。\n"
                "360度パノラマ形式(equirectangular)で書き出した動画を使ってください。",
            )
        if not frames:
            QtWidgets.QMessageBox.critical(self, "エラー", "フレームを取得できませんでした。")
            return
        self._set_image(frames[0].image)
        self.status.showMessage(
            f"動画を読み込みました（最も鮮明なフレーム: 時刻 {frames[0].time_sec:.2f}秒）"
        )

    def open_image(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "パノラマ画像を選択", "", "画像 (*.png *.jpg *.jpeg *.bmp);;すべて (*)"
        )
        if not path:
            return
        img = cv2.imread(path)
        if img is None:
            QtWidgets.QMessageBox.critical(self, "エラー", "画像を読み込めませんでした。")
            return
        self._set_image(img)
        self.status.showMessage("画像を読み込みました")

    def _set_image(self, img_bgr: np.ndarray) -> None:
        self.image_bgr = img_bgr
        self.clear_points()
        self.view.set_image(img_bgr)
        h, w = img_bgr.shape[:2]
        if abs(w / h - 2.0) > 0.15:
            self.status.showMessage("⚠️ 画像が2:1ではありません。計測精度が落ちる可能性があります。")

    # ---------------- 点の操作 ----------------
    def _on_mode_changed(self) -> None:
        self.add_mode = "floor" if self.radio_floor.isChecked() else "ceiling"

    def on_point_clicked(self, x: float, y: float) -> None:
        if self.image_bgr is None:
            return
        if self.add_mode == "floor":
            self.floor_pts.append((x, y))
        else:
            self.ceiling_pts.append((x, y))
        self.view.redraw_markers(self.floor_pts, self.ceiling_pts)
        self._update_status()

    def undo_point(self) -> None:
        target = self.floor_pts if self.add_mode == "floor" else self.ceiling_pts
        if target:
            target.pop()
        self.view.redraw_markers(self.floor_pts, self.ceiling_pts)
        self._update_status()

    def clear_points(self) -> None:
        self.floor_pts = []
        self.ceiling_pts = []
        if self.view.has_image():
            self.view.redraw_markers(self.floor_pts, self.ceiling_pts)
        self._update_status()

    def _update_status(self) -> None:
        self.setWindowTitle(
            f"360度カメラ 部屋寸法計測ツール  —  床の角:{len(self.floor_pts)}個 / "
            f"天井の角:{len(self.ceiling_pts)}個"
        )

    # ---------------- 計算 ----------------
    def compute(self) -> None:
        if self.image_bgr is None:
            QtWidgets.QMessageBox.information(self, "確認", "先に動画または画像を読み込んでください。")
            return
        if len(self.floor_pts) < 3:
            QtWidgets.QMessageBox.information(
                self, "確認", "床の角を3つ以上（できれば部屋の全ての角を）指定してください。"
            )
            return
        h, w = self.image_bgr.shape[:2]
        ceiling = self.ceiling_pts if self.ceiling_pts else None
        try:
            dims = g.compute_room_dimensions(
                self.floor_pts, w, h, self.spin_height.value(),
                ceiling_corner_pixels=ceiling,
            )
        except ValueError as e:
            QtWidgets.QMessageBox.warning(self, "計算できません", str(e))
            return
        self.last_dims = dims
        self.result_text.setPlainText(render.summary_text(dims))
        plan = render.render_floor_plan(dims)
        self.last_plan = plan
        pm = cv_to_qpixmap(plan).scaled(
            self.plan_label.width(), self.plan_label.height(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        self.plan_label.setPixmap(pm)

    def recompute_if_ready(self) -> None:
        if self.last_dims is not None and len(self.floor_pts) >= 3:
            self.compute()

    # ---------------- 保存 ----------------
    def save_plan(self) -> None:
        if self.last_plan is None:
            QtWidgets.QMessageBox.information(self, "確認", "先に「計算する」を押してください。")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "間取り図を保存", "floor_plan.png", "画像 (*.png *.jpg)"
        )
        if path:
            cv2.imwrite(path, self.last_plan)
            self.status.showMessage(f"間取り図を保存しました: {path}")

    def save_csv(self) -> None:
        if self.last_dims is None:
            QtWidgets.QMessageBox.information(self, "確認", "先に「計算する」を押してください。")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "結果をCSV保存", "room_dimensions.csv", "CSV (*.csv)"
        )
        if not path:
            return
        d = self.last_dims
        bw, bd = d.bounding_size
        with open(path, "w", newline="", encoding="utf-8-sig") as fp:
            w = csv.writer(fp)
            w.writerow(["項目", "値", "単位"])
            w.writerow(["カメラ高さ", f"{d.camera_height:.3f}", "m"])
            w.writerow(["床面積", f"{d.floor_area:.3f}", "m^2"])
            w.writerow(["幅", f"{bw:.3f}", "m"])
            w.writerow(["奥行き", f"{bd:.3f}", "m"])
            w.writerow(["周長", f"{d.perimeter:.3f}", "m"])
            if d.ceiling_height is not None:
                w.writerow(["天井高", f"{d.ceiling_height:.3f}", "m"])
            for i, wl in enumerate(d.wall_lengths):
                w.writerow([f"壁{i + 1}の長さ", f"{wl:.3f}", "m"])
            w.writerow([])
            w.writerow(["角番号", "X[m]", "Y[m]"])
            for i, (x, y) in enumerate(d.corners_xy):
                w.writerow([i + 1, f"{x:.3f}", f"{y:.3f}"])
        self.status.showMessage(f"CSVを保存しました: {path}")


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
