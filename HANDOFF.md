# Swipe Shooter Puzzle — 引き継ぎメモ

> このプロジェクトを **PC で / 共同で**続けるための引き継ぎ資料です。
> 作成日: 2026-06-20

---

## 0. これは何のプロジェクトか

- スワイプで狙って連射し、数字付きブロックを壊す **Ballz / Bricks n Balls 風**のモバイル向けパズルシューター（Godot 4.3）。
- 外部アセット無し・GDScript のみ・縦持ち（720×1280, タッチ, gl_compatibility）。
- 元リポジトリは **Rainbow CSV の VS Code 拡張**で、本ゲームはこのブランチで**新規追加**したもの。
- ⚠️ **ゲーム仕様は未合意**。現在の設計はフォルダ名 `swipe-shooter-puzzle` からの**推測で決め打ち**したたたき台。「土台にするか作り直すか」は未決定。

---

## 1. まず取得するもの

| 項目 | 値 |
| --- | --- |
| リポジトリ | `meganeETH/vscode_rainbow_csv` |
| ブランチ | `claude/godot-android-build-config-571w61` ← **master ではない** |
| 最新コミット | `53104ce`（時点） |
| PR | #1（draft） |

```bash
git fetch origin claude/godot-android-build-config-571w61
git checkout claude/godot-android-build-config-571w61
git pull origin claude/godot-android-build-config-571w61
```

> リモート実行コンテナは使い捨て。**必要なものは全て push 済み**で、ローカルに残した作業はありません。

---

## 2. 動かし方

### エディタで遊ぶ（署名不要）
1. **Godot 4.3 stable** で `swipe-shooter-puzzle/project.godot` を開く（別バージョン非推奨）。
2. F5 で実行。デスクトップではマウスがタッチとして扱われる（`emulate_touch_from_mouse`）。
3. 初回起動で `.godot/`（gitignore 済み）が自動生成 ＝ 正常。

### Android デバッグ APK（CI）
- `claude/**` への push / PR / 手動実行（workflow_dispatch）で、`swipe-shooter-puzzle/**` 変更時に `.github/workflows/android.yml` が走る。
- 取得: **Actions → 対象 run → artifact `swipe-shooter-puzzle-debug-apk`**（arm64・未署名）。

---

## 3. ⚠️ 実機インストール時の重要な注意

**今の APK は未署名なので、実機にそのままインストールできない可能性が高い**
（Android は未署名 APK を拒否：`INSTALL_PARSE_FAILED_NO_CERTIFICATES` 等）。

- 元タスクの指示どおり `export_presets.cfg` は `package/signed=false`。
- **実機で試すなら `export_presets.cfg` の `package/signed=true` に変更**するだけでOK。
  CI 側はデバッグキーストア生成＋`GODOT_ANDROID_KEYSTORE_DEBUG_*` を既に渡しているので、
  それだけで**署名済み・インストール可能なデバッグ APK**になる。
- エディタ（F5）で遊ぶだけなら署名は不要。

---

## 4. プロジェクト構成

| パス | 役割 |
| --- | --- |
| `swipe-shooter-puzzle/project.godot` | プロジェクト設定（縦720×1280・タッチ・gl_compatibility・ETC2/ASTC有効） |
| `swipe-shooter-puzzle/main.tscn` | メインシーン（`Game` ノード + `scripts/game.gd`） |
| `swipe-shooter-puzzle/scripts/game.gd` | ゲーム全ロジック（入力・物理・描画・盤面・状態管理） |
| `swipe-shooter-puzzle/export_presets.cfg` | Android 書き出し（未署名・gradleビルド無効・arm64・APK形式） |
| `swipe-shooter-puzzle/icon.svg` / `icon.svg.import` | アイコンとインポート設定 |
| `swipe-shooter-puzzle/README.md` | リポジトリ内の状況ドキュメント |
| `.github/workflows/android.yml` | CI（Godot とテンプレ取得 → debug APK 書き出し） |

> 今後アセットを追加したら、生成される **`*.import` も一緒にコミット**すること（`icon.svg.import` と同様）。

---

## 5. 実装メモ（コードを触る前に）

- 手動サブステップの **円 vs AABB 衝突**。速度一定化＋「ほぼ水平な弾」の補正で、
  弾が左右の壁で無限往復してターンが終わらない状態を防止している。
- 描画はすべて `_draw()` 内の `draw_*`（ブロック/数字/弾/HUD/ゲームオーバー）。
- 状態機械: `AIM`（照準）→ `SHOOT`（発射・解決）→ `AIM` / `OVER`。
- 主要パラメータは `game.gd` 冒頭の定数（`COLS`, `MAX_ROWS`, `BALL_SPEED`, `BALL_RADIUS`,
  `SHOOT_INTERVAL` など）。難易度調整はここが起点。

---

## 6. ビルドを緑にするまでに潰した問題（再発時の参考）

1. **そもそも Godot プロジェクトが無い** → エクスポート可能な最小プロジェクトを作成。
2. **Android デバッグキーストア未設定** → CI でキーストア生成し `GODOT_ANDROID_KEYSTORE_DEBUG_*` で注入。
3. **空の `configuration errors`（真因）** → Godot の `should_import_etc2_astc()` が false だと
   **メッセージ無しで**検証失敗する。`rendering/textures/vram_compression/import_etc2_astc=true` で解決。

---

## 7. 検証済み / 未検証

- ✅ Godot 4.3 でインポート成功（構文・シーン参照エラー無し）。
- ✅ ヘッドレスでコアループ実走（衝突・オーブ取得・ボール増加・ターン解決・ゲームオーバー・無限ループ防止を確認）。
- ✅ CI で debug APK ビルド成功（artifact 24MB / arm64・未署名）。
- ⚠️ `_draw` の**見た目**と**実機タッチ**は未検証（CI/ヘッドレスに画面が無いため）。

---

## 8. 次の論点 / TODO（要相談）

- [ ] **ゲーム仕様の合意**（ジャンル・操作・勝敗条件・テーマ）。現状は推測ベース。
- [ ] 現設計（Ballz 系）を**土台にするか作り直すか**の決定。
- [ ] 実機/エディタでの見た目・操作感の確認。
- [ ] 演出（効果音・BGM・パーティクル）、ハイスコア保存、難易度カーブ調整、アイコン差し替え。
- [ ] リリース署名（現状はデバッグ・未署名のみ）。

---

## 9. 運用ルール（提案）

- 作業は GitHub 経由で共有。**README と PR #1 説明を最新に保つ**ことで、GitHub だけで現状を追える状態を維持する。
- PR #1 への CI 失敗監視は、リモートセッション側で当面継続中（不要になれば停止指示で止められる）。
