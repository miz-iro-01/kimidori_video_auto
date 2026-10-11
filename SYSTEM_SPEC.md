# KIMIDORI YouTube Auto - システム仕様書 (SYSTEM_SPEC.md)

## 1. システム概要
- **システム名**: KIMIDORI YouTube Auto (KIMIDORI Movie Auto)
- **目的**: YouTube ショート動画（簡易版・Pro版60秒アニメーション）および長尺漫画・解説動画（15〜20分・全5章構成）、実写動画の自動編集（ジェットカット＋高精度テロップ付与）、トレンド・Outlier（外れ値）リサーチ、YouTube 自動投稿までを一貫して行う統合AI動画生成プラットフォーム。
- **アーキテクチャ構成**:
  - **フロントエンド層**: Next.js 14 (TypeScript / App Router, Port 3001) + Vanilla JS SPA (`frontend/index.html`, `frontend/js/app.js`, `frontend/js/api-client.js`)
  - **バックエンド層**: Python FastAPI (`backend/main.py`, Port 8080) + FFmpeg マルチレイヤー動画合成エンジン
  - **AI・メディア生成基盤**:
    - テキスト・台本・Outlier分析: Google Gemini API (`gemini-2.5-flash`, `gemini-2.5-pro`)
    - 一貫性キャラクター＆シーン画像生成 (Stage 1): 有料 Gemini API Nano Banana (`gemini-3.1-flash-image`, `gemini-nano-banana-2.1`, `gemini-3-pro-image`) / FLUX.1 / Google Colab GPU / Pexels
    - リファレンス Image-to-Video アニメーション動画生成 (Stage 2): Google Colab ComfyUI (`LTX-Video I2V`) / 有料 Gemini API Veo 3.1 (`veo-3.1-fast-generate-preview`, `veo-3.1-generate-preview`)
    - 音声合成 (TTS): Edge TTS, VOICEVOX, Google Cloud TTS, ElevenLabs, OpenAI TTS, Azure Speech, Amazon Polly, SHAREVOX, COEIROINK, AivisSpeech, 音読さん, CoeFont
  - **データ・ストレージ基盤**: Firebase Firestore / Local JSON Fallback (`backend/services/firestore_service.py`), Google Cloud Storage, YouTube Data API v3 (OAuth2)

---

## 2. 主要機能一覧
1. **簡易ショート動画自動生成 (Mode A)**:
   - テーマ入力・トレンドリサーチから台本生成、TTS音声合成、画像生成、テロップ合成、BGMミキシング、YouTube投稿までを自動実行。
2. **Pro版ショート動画生成 (60秒・2段階I2Vアニメーション＆5層プロ仕様テロップ)**:
   - **統一ワークフロー**: `テーマ記入` ➔ `Outlier（外れ値）リサーチ` ➔ `ジャンル選定 ＆ スタイル（絵柄）独立選定` ➔ `自前の台本入力欄` ➔ `1. 台本作成ボタン` ➔ `AI動画生成ワーカー（TTSその場試聴・テロップ即時プレビュー・BGM選曲変更＆試聴）` ➔ `2. ショート動画作成ボタン`。
   - **ジャンルとスタイル（絵柄）の分離登録**: 構成ジャンル（`story`, `business`, `edoculture`, `trivia`）とビジュアルスタイル（`ukiyoe` 本格浮世絵・江戸木版画、`anime_modern`、`manga_dramatic`、`watercolor_ink`、`flat_2d_motion`、`photoreal_cinematic`）を独立指定可能。`ukiyoe` 選択時はアニメ調キーワードを完全排除し、北斎・広重・国芳・写楽風の伝統木版画（錦絵・和紙繊維質感・墨骨線・岩絵具）として一貫生成。
   - **Stage 0**: 登場人物の単一バストアップ基準マスター画像を Nano Banana で `visual_style` に準拠して確定生成。
   - **Stage 1**: マスター画像を `inlineData` リファレンス参照し、単一フルスクリーン9:16シーン静止画 (`bg_xxx.png`) を生成（分割パネル・外枠自動検出トリミング保護付き）。
   - **Stage 2**: 生成したシーン静止画 (`bg_xxx.png`) をリファレンス入力として、Colab ComfyUI (`LTX-Video I2V`) または Gemini `Veo 3.1 I2V` でアニメーション動画 (`clip_xxx.mp4`) に変換。
   - **Stage 3**: YouTube定番の極太日本語フォント8種から選択可能な5層マルチレイヤーテロップ（即時プレビューAPI `/api/telop/preview` 対応）および内蔵/カスタムBGM（`/api/bgm/builtin/{preset_id}`, `/api/bgm/file/{bgm_id}`）を合成。
3. **長尺動画自動生成 (15〜20分・全5章構成)**:
   - Pro版ショート動画と同一の統一ワークフロー（テーマ・Outlierリサーチ・ジャンル×スタイル分離・自前台本・AI動画生成ワーカー内TTS試聴・テロップ即時プレビュー・BGM選択＆試聴）を搭載。
   - 全5章・120〜180カットのタイムラインJSON設計図生成、マルチBGMクロスフェード合成、カット単位の単体再生成リカバリー機能 (`/api/timeline/scene/regenerate`)。
   - **チェックポイント再利用＆自動再開機構**: マスター画像 (`master_*.png`)・音声 (`speech_xxx.mp3`)・シーン静止画 (`bg_xxx.png`)・I2Vアニメーション動画 (`clip_xxx.mp4`) をカット単位でディスクチェックポイント化し、サーバー再起動や中断が発生しても `/api/jobs/{job_id}` ポーリング時に `job_params.json` から自動検知して未完了カットから即座に自動再開。
4. **実写動画の自動編集 (Mode B: ジェットカット＆高精度テロップ焼き付け)**:
   - 無音区間の自動検知・ジェットカット、Whisper 音声認識によるタイムスタンプ抽出、文脈スコアリング改行によるテロップ焼き付け、Bロール自動挿入。
5. **トレンド・Outlier（外れ値）リサーチ＆海外ビジネス洋書翻案**:
   - 登録者数比で高再生を記録しているOutlier動画の抽出・隠れ需要インサイト分析 (`/api/research/outliers`)。
   - 海外ビジネス書・行動経済学理論を日本の職場ストーリーへ翻案 (`/api/research/adapt-book`)。
6. **保存済み動画ストック（最大5本保持・リロード自動復元）＆ ユーザーリファレンス画像アップロード**:
   - **最大5本ストック自動保存・リロード保持**: Pro版ショート動画および長尺動画それぞれで完成した動画を最大5本まで自動保存・インデックス化（`GET /api/videos/saved`, `DELETE /api/videos/saved/{job_id}`）。画面リロード時も直近の完成動画および作成中台本JSONを自動復元し、ワンクリックで再生・MP4保存・タイムライン編集への引き渡しが可能。
   - **ユーザー側リファレンス画像アップロード**: ユーザーがキャラクター画像や画風基準画像を複数枚アップロード（キャラ名指定または全カット共通指定）でき、Stage 0/1（Gemini Nano Banana）および Stage 2（Colab LTX-Video / Gemini Veo I2V）の最優先リファレンスとして注入。
7. **Pro 動画タイムライン編集スタジオ（Remotion / Filmcraft アーキテクチャ準拠・`#proVideoEditorModal`）**:
   - Pro版ショート動画および長尺動画の完成後（または5本ストック一覧から）「編集する」ボタンでタイムライン編集スタジオへ引き渡し（`GET /api/manga/editor/{job_id}`, `POST /api/manga/editor/{job_id}/save`）。
   - **テロップの種類・位置・サイズ変更**: フォント8種・5層スタイル配色5種・縦位置Y座標（上部18% / 中央50% / 下部76% / 10〜90%スライダー / プレビュー画面上の直接上下ドラッグ移動）・文字サイズ倍率のカット別変更および全カット一括適用。
   - **ナレーション変更＆その場再合成**: セリフ書き換え・TTSエンジン/声色/話速変更・単一カット即時音声再合成（`POST /api/manga/editor/{job_id}/resynthesize-tts`、尺の自動更新付き）・カスタム音声ファイル差替。
   - **カット作業・素材差替**: カット有効/無効トグル、表示尺 `duration`・開始トリミング `trim_start` 調整、カット2分割、複製、順序入替、削除、背景画像・動画クリップの差し替えアップロード（`POST /api/manga/editor/{job_id}/upload-cut-media`）。
   - **効果音（SE）追加＆BGM変更**: 内蔵プロシージャル高音質SE 10種（ドン！、和太鼓ドドン！、拍子木カンカン！、キラーン！、ピコン！、シュッ！、ジャジャン！、ピンポーン！、ガーン…、ドラムロール＋ジャン！）＋カスタムSEアップロード（`/api/se/list`, `/api/se/file/{se_id}`, `/api/se/upload`）、発動タイミング `se_delay`・音量調整、および全体BGM変更・音量調整。
   - **高速再書き出し（`POST /api/manga/editor/{job_id}/render`）**: 既存の動画クリップ・画像・音声アセットを再利用してFFmpegで高速再合成し、`manga_video_final.mp4` と保存済みストックを即時更新。
8. **管理者機能・外部GPU/API統合設定**:
   - ユーザー権限・プラン管理 (`/api/admin/users`)。
   - Google Colab / ComfyUI 接続URLの動的設定・永続化 (`/api/colab/config`) およびヘルスチェック (`/api/colab/health`)。
   - BGMライブラリ管理・YouTube マルチチャンネル OAuth 連携。

---

## 3. 現在の実装済みファイル一覧

### ルート & ハーネス・設定ファイル
- `package.json`: Next.js アプリケーション依存関係および `harness:check` 定義
- `tsconfig.json`: TypeScript 型検査設定
- `next.config.mjs`: Next.js ビルド・ルーティング・APIプロキシ設定
- `scripts/harness.mjs`: 型チェック (`tsc --noEmit`) と本番ビルド (`npm run build`) の自律検証ハーネススクリプト
- `GEMINI.md` / `AGENTS.md`: 開発標準ルールおよび自律ハーネス検証ワークフロー規範
- `SYSTEM_SPEC.md`: 本システム仕様書

### フロントエンド (`app/`, `lib/`, `frontend/`)
- `app/layout.tsx`: Next.js ルートレイアウト
- `app/page.tsx`: 既存フロントエンド (`frontend/index.html`) を統合配信するメインエントリーページ
- `app/api/comfyui/route.ts`: ComfyUI (LTX-Video) 連携用 Next.js API Route
- `lib/comfyui-client.ts`: ComfyUI ワークフロークライアントライブラリ
- `frontend/index.html`: KIMIDORI YouTube Auto メインSPA画面（ダッシュボード、簡易ショート、Pro版ショート、長尺動画、実写自動編集、Pro動画タイムライン編集スタジオ `#proVideoEditorModal`、BGM管理、設定、管理者画面）
- `frontend/css/style.css`: グラスモーフィズム・レスポンシブUI・マルチトラックタイムライン編集スタジオスタイルシート
- `frontend/js/app.js`: UIコントローラー・5本保存ストック管理・リファレンス画像アップロード・Pro動画タイムライン編集スタジオ制御モジュール
- `frontend/js/api-client.js`: バックエンドAPI通信・動画ストック・SE・タイムライン編集スタジオAPIクライアント
- `frontend/js/settings.js`: APIキー・TTS・Colab URL設定管理モジュール
- `frontend/js/bgm-library.js`: BGM管理・試聴モジュール
- `frontend/js/youtube-accounts.js`: YouTube OAuth マルチアカウント管理モジュール
- `frontend/js/firebase-config.js`: Firebase 初期化・認証設定

### バックエンド (`backend/`)
- `backend/main.py`: FastAPI メインアプリケーション・全APIエンドポイント定義
- `backend/config.py`: 環境変数・ディレクトリ・デフォルトモデル設定
- `backend/models/timeline.py`: タイムライン・シーン・カメラワークPydanticデータモデル
- `backend/processors/batch_asset_generator.py`: 音声・ユーザーリファレンス画像最優先注入・Nano Banana単一フレーム画像・Stage 2 I2Vアニメーション動画・カスタムY座標＆倍率対応5層テロップ生成モジュール
- `backend/processors/long_manga_pipeline.py`: Pro版ショートおよび長尺動画の統合生成パイプライン・単体カット再生成・完成時5本ストック自動登録
- `backend/processors/manga_video_composer.py`: FFmpeg シーン動画合成（トリミング・強制尺・効果音SE `adelay`+`amix` 合成）・順次テロップオーバーレイ・マルチBGMクロスフェード合成エンジン
- `backend/processors/pro_shorts_engine.py`: Pro版ショート動画（60秒・全カット動画演出）台本生成エンジン
- `backend/processors/long_video_engine.py`: 長尺動画（全5章構成）台本生成エンジン
- `backend/processors/colab_gpu_client.py`: Google Colab ComfyUI (`LTXVImgToVideo` / T2V) およびカスタムGPUワーカー通信クライアント
- `backend/processors/flux_client.py`: FLUX.1 (fal.ai / Replicate) 画像生成クライアント
- `backend/processors/pexels_client.py`: Pexels ストック動画・画像検索ダウンロードクライアント
- `backend/processors/tts_manager.py`: 12種マルチTTSエンジン統合・音声合成マネージャー
- `backend/processors/outlier_research_engine.py`: Outlier動画検出・隠れ需要分析・洋書翻案エンジン
- `backend/processors/research_engine.py`: トレンドリサーチエンジン
- `backend/processors/script_normalizer.py`: 外部原稿のタイムラインJSON正規化エンジン
- `backend/processors/mode_a_generator.py`: 簡易ショート動画 (Mode A) プロセッサー
- `backend/processors/mode_b_editor.py`: 実写動画ジェットカット＆字幕焼き付け (Mode B) プロセッサー
- `backend/processors/broll_inserter.py`: 自動Bロール挿入プロセッサー
- `backend/services/video_stock_service.py`: 保存済み5本動画ストック永続化・10種プロシージャル効果音(SE)生成・ユーザーリファレンス画像保存・Proタイムライン編集スタジオ状態管理＆高速FFmpeg再レンダリングサービス
- `backend/services/firestore_service.py`: Firestore / ローカルJSONジョブ状態永続化サービス
- `backend/services/storage_service.py`: Cloud Storage アップロードサービス
- `backend/services/youtube_service.py`: YouTube Data API v3 アップロード＆OAuthサービス
- `backend/services/bgm_service.py`: BGM管理・AI自動選曲サービス
- `backend/services/permission_manager.py`: 会員プラン・ロール権限管理サービス
- `backend/utils/asset_cache_manager.py`: 音声・画像ハッシュキャッシュ管理ユーティリティ
- `backend/utils/ffmpeg_utils.py`: FFmpeg 音声長計測・BGMミックスユーティリティ
- `backend/utils/key_manager.py`: Gemini API キーローテーション・リトライ管理ユーティリティ
- `backend/assets/fonts/`: YouTube定番極太日本語フォント8種 (`DelaGothicOne-Regular.ttf`, `ReggaeOne-Regular.ttf`, `MochiyPopOne-Regular.ttf`, `ShipporiMinchoB1-ExtraBold.ttf`, `MPLUSRounded1c-Black.ttf`, `RocknRollOne-Regular.ttf`, `ZenMaruGothic-Black.ttf`, `RampartOne-Regular.ttf`)

