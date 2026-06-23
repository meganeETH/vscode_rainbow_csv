"""
360度動画からパノラマ静止画（フレーム）を取り出すモジュール。

多くの360度カメラ（Ricoh Theta, Insta360 等）は、最終的に
正距円筒図法（equirectangular, 横:縦 = 2:1）のmp4として書き出します。
このモジュールはその動画から、計測に使いやすい鮮明なフレームを選びます。
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class FrameInfo:
    """取り出した1フレームの情報。"""

    index: int          # 動画中のフレーム番号
    time_sec: float     # 動画中の時刻[秒]
    sharpness: float    # 鮮明さの指標（大きいほどくっきり＝ブレが少ない）
    image: np.ndarray   # BGR画像（OpenCV形式）


def _sharpness(gray: np.ndarray) -> float:
    """ラプラシアンの分散で鮮明さ（ブレの少なさ）を測る。"""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def probe_video(path: str) -> dict:
    """動画の基本情報（解像度・フレーム数・長さ・equirectangularか）を返す。"""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise FileNotFoundError(f"動画を開けませんでした: {path}")
    try:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = n_frames / fps if fps > 0 else 0.0
        # 正距円筒図法は横:縦がほぼ2:1
        is_equirect = height > 0 and abs(width / height - 2.0) < 0.15
        return {
            "width": width,
            "height": height,
            "fps": fps,
            "n_frames": n_frames,
            "duration_sec": duration,
            "is_equirectangular": is_equirect,
        }
    finally:
        cap.release()


def extract_frame_at(path: str, time_sec: float) -> FrameInfo:
    """指定した時刻のフレームを1枚取り出す。"""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise FileNotFoundError(f"動画を開けませんでした: {path}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        index = int(round(time_sec * fps))
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = cap.read()
        if not ok:
            raise ValueError(f"フレームを取得できませんでした（時刻 {time_sec}秒）")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return FrameInfo(index=index, time_sec=time_sec, sharpness=_sharpness(gray), image=frame)
    finally:
        cap.release()


def select_sharpest_frames(
    path: str, n_candidates: int = 20, n_return: int = 3
) -> list[FrameInfo]:
    """
    動画を等間隔にサンプリングし、最も鮮明（ブレが少ない）なフレームを返す。

    計測ではブレの少ない鮮明なフレームを使うほど精度が上がるため、
    候補を複数取り出してシャープネス上位を返す。
    """
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise FileNotFoundError(f"動画を開けませんでした: {path}")
    try:
        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if n_frames <= 0:
            raise ValueError("フレーム数を取得できませんでした。")

        n_candidates = max(1, min(n_candidates, n_frames))
        sample_indices = np.linspace(0, n_frames - 1, n_candidates).astype(int)

        candidates: list[FrameInfo] = []
        for idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ok, frame = cap.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            candidates.append(
                FrameInfo(
                    index=int(idx),
                    time_sec=idx / fps,
                    sharpness=_sharpness(gray),
                    image=frame,
                )
            )

        candidates.sort(key=lambda f: f.sharpness, reverse=True)
        return candidates[:n_return]
    finally:
        cap.release()


def save_frame(frame: FrameInfo, out_path: str) -> None:
    """フレーム画像をファイルに保存する。"""
    cv2.imwrite(out_path, frame.image)
