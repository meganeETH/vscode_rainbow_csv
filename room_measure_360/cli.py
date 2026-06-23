#!/usr/bin/env python3
"""
コマンドラインから使う計測ツール。

使い方の例:
  # 1) 動画から鮮明なフレームを抽出して保存
  python3 cli.py extract-frame --video room.mp4 --out frame.png

  # 2) パノラマ画像と角の座標(JSON)から寸法を計算
  python3 cli.py measure --image frame.png --points points.json \
      --camera-height 1.5 --out-plan plan.png

  # 3) デモ用の合成360度動画を生成（実機の動画が無いとき）
  python3 cli.py make-demo --out demo.mp4

points.json の形式:
  {
    "floor": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]],   # 床と壁の角（部屋を一周する順）
    "ceiling": [[x1,y1],...]                        # 任意: 天井と壁の角（床と同じ順）
  }
"""

from __future__ import annotations

import argparse
import json
import sys

import cv2

from room_measure import geometry as g
from room_measure import video as v
from room_measure import render
from room_measure.synthetic import SyntheticRoom, write_demo_video


def cmd_extract_frame(args) -> int:
    info = v.probe_video(args.video)
    print(f"動画情報: {info['width']}x{info['height']} / "
          f"{info['duration_sec']:.1f}秒 / equirectangular={info['is_equirectangular']}")
    if not info["is_equirectangular"]:
        print("⚠️ 横:縦が2:1ではありません。360度パノラマ形式(equirectangular)で書き出した動画を使ってください。")
    frames = v.select_sharpest_frames(args.video, n_return=1)
    if not frames:
        print("フレームを抽出できませんでした。", file=sys.stderr)
        return 1
    f = frames[0]
    v.save_frame(f, args.out)
    print(f"✅ 最も鮮明なフレーム(時刻 {f.time_sec:.2f}秒, 鮮明度 {f.sharpness:.0f}) を {args.out} に保存しました。")
    return 0


def cmd_measure(args) -> int:
    img = cv2.imread(args.image)
    if img is None:
        print(f"画像を読み込めません: {args.image}", file=sys.stderr)
        return 1
    height, width = img.shape[:2]

    with open(args.points, encoding="utf-8") as fp:
        pts = json.load(fp)
    floor = [tuple(p) for p in pts["floor"]]
    ceiling = [tuple(p) for p in pts.get("ceiling", [])] or None

    dims = g.compute_room_dimensions(
        floor, width, height, args.camera_height, ceiling_corner_pixels=ceiling
    )
    print(render.summary_text(dims))

    if args.out_plan:
        plan = render.render_floor_plan(dims)
        cv2.imwrite(args.out_plan, plan)
        print(f"\n🗺  間取り図を {args.out_plan} に保存しました。")
    return 0


def cmd_make_demo(args) -> int:
    room = SyntheticRoom(
        width_m=args.width, depth_m=args.depth,
        height_m=args.ceiling, camera_height_m=args.camera_height,
    )
    write_demo_video(args.out, room)
    print(f"✅ デモ用360度動画を {args.out} に書き出しました "
          f"（部屋 {args.width}x{args.depth}x{args.ceiling}m, カメラ高さ {args.camera_height}m）。")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="360度パノラマから部屋の寸法を計測するツール")
    sub = p.add_subparsers(dest="command", required=True)

    pe = sub.add_parser("extract-frame", help="動画から鮮明なフレームを抽出")
    pe.add_argument("--video", required=True)
    pe.add_argument("--out", required=True)
    pe.set_defaults(func=cmd_extract_frame)

    pm = sub.add_parser("measure", help="角の座標から寸法を計算")
    pm.add_argument("--image", required=True)
    pm.add_argument("--points", required=True)
    pm.add_argument("--camera-height", type=float, default=1.5)
    pm.add_argument("--out-plan", default=None)
    pm.set_defaults(func=cmd_measure)

    pd = sub.add_parser("make-demo", help="デモ用の合成360度動画を生成")
    pd.add_argument("--out", required=True)
    pd.add_argument("--width", type=float, default=4.0)
    pd.add_argument("--depth", type=float, default=3.0)
    pd.add_argument("--ceiling", type=float, default=2.5)
    pd.add_argument("--camera-height", type=float, default=1.5)
    pd.set_defaults(func=cmd_make_demo)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
