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


## Phase 1: Cyber UI / Own-script / Studio Handoff
- Cyber theme (#0B0F19 base, emerald/cyan accents) appended to frontend/css/style.css; status shown as AI Core: Online/Standby dot indicator.
- Internal terms sanitized in UI text, api-client errors and showToast (_sanitizeUserMessage in app.js).
- Simple Short own-script input (direct / file / Drive) rewrites via getScriptPreview (btnNormalizeSimpleScript).
- Pro Short and Long: 'Open in editing studio' button (btnStudioHandoffPro/Long) saves kimidori_editor_handoff (video_url, audio_tracks, telops) to localStorage and opens view-edit with handoff panel and timeline.
- Simple Short: MP4 save only; studio button locked (btnStudioLockedSimple).
- Standalone editor drag-and-drop (uploadZoneB) retained.


## Phase 2: Studio Pro (jet-cut / wipe / B-roll / telop clips / BGM track)
- New files: frontend/js/studio-pro.js (editor extension, state in editorState.studio), backend/studio_pro.py (router + FFmpeg postprocess).
- Editor tabs 5 (jet-cut, Pexels B-roll, bottom-right wipe) and 6 (telop clips, BGM track); extra timeline lanes B-ROLL / TELOP CLIP / WIPE / BGM (studioExtraTracks).
- Jet-cut: Web Audio RMS analysis (threshold dB, min silence 0.3s), scene.jet_keep ranges + duration shortened; backend rebuilds narration audio via ffmpeg atrim/concat (build_jetcut_audio).
- Wipe: face camera video or talking character (loudness-driven jaw/mouth/bob animation), circle or rounded, size/position sliders and drag; live preview in stage; rendered by apply_studio_postprocess.
- B-roll: keyword extraction (Intl.Segmenter) + POST /api/studio/pexels-search (Gemini keyword translation optional), 3-5s overlays that return to main video.
- Telop clips: auto placement from script, inline timeline editing, size/colour/timing; telops_override disables per-cut telops at render.
- BGM track: default builtin:upbeat_business at 15% for new projects, volume slider, mute (bgm_muted), custom upload (/api/studio/{job}/upload-asset kind=bgm into data/bgm).
- Phase 1 theme and kimidori_editor_handoff are unchanged.

## Phase 3: Pro Shorts Comic Manga Style & Long Video Business Manga (Character Consistency / Western Book Adaptation / Hybrid Generation)
- **Pro版ショート「漫画風（コミック）」スタイル (`comic_manga` / `comic_manga_mono`)**:
  - スタイル選択肢に「漫画風」を追加（`#inputProShortsVisualStyle`, `#inputLongVideoVisualStyle`）。
  - 漫画演出オプションUI（`#proShortsComicOptionsBox`, `#longVideoComicOptionsBox`）:
    1. カラー / 白黒（モノクロ・スクリーントーン調）切り替えトグル（`#proShortsComicColorMode`, `#longVideoComicColorMode`）。
    2. セリフ後出し演出（`#proShortsComicBubbleDelay`, `#longVideoComicBubbleDelay`、デフォルト `+0.40s`）: 映像/コマ静止画の表示から少し遅れて話者バッジ付きフキダシ（`_create_comic_speech_bubble_card`）がポップに浮き出るアニメーション合成。
  - 下部通常字幕テロップの自動非表示（`bottom_telop_suppressed = True`）: 「漫画風」選択時は画面内フキダシ演出と被らないよう下部の通常テロップ（TELOP）を自動的にオフ化。
- **Pro版長尺動画（15〜20分）キャラクター一貫性（キャラ固定・2系統UI）**:
  - `POST /api/studio/generate-character-ref` (`backend/studio_pro.py`) による「1. AIでキャラクター生成」（`#btnGenerateAiCharLong`）と「2. 手持ちのキャラクター画像をアップロード」（`#fileRefImagesLongVideo`）の2系統UIを実装。
  - 指定されたキャラクターの特徴（名前・役割・服装 `clothing`・髪型 `hairstyle`・容姿 `appearance`）およびリファレンス画像を `character_traits` / `custom_reference_images` として全シーンの生成パイプラインへ一貫注入。
- **Pro版長尺動画：洋書翻案ビジネス漫画台本 ＆ 自前台本連携**:
  - 台本生成モード選択（`#longVideoScriptModeSelect`: `western_book_adaptation` / `custom_script_rewrite` / `standard`）。
  - 「洋書翻案モード」: 海外のベストセラービジネス洋書の概念・ノウハウを取り入れ、日本のビジネスパーソン向けの共感ストーリー・会話劇へ自動翻案（`backend/processors/long_video_engine.py`）。
  - 「自前台本持ち込み」: テキスト直貼り・ファイル選択（`.txt/.md/.json`）・Google Drive連携で投入された自作台本を長尺用の全5章・複数シーンカット割りJSONへ正確にリライト分解。
- **長尺ハイブリッド動画生成 ＆ スタジオ引き渡し**:
  - ハイブリッド生成ロジック（`backend/models/timeline.py` `optimize_video_ratio`, `backend/processors/batch_asset_generator.py`, `backend/processors/manga_video_composer.py`）:
    - 導入（冒頭カット）・各章の幕開け（`_cut1`）・クライマックスの重要カット（`scene.type == "video"`）: Stage 2 AIアニメーション動画（I2V）を生成。
    - 通常の会話・解説カット（`scene.type == "image"`）: キャラ固定静止画 ＋ カメラワーク（`zoom_in` / `pan_right` / `pan_left` / `zoom_out` Ken Burns演出） ＋ セリフ後出しフキダシ浮き出し演出で高速・高品質に合成。
  - 編集スタジオ連携: 長尺プレビュー画面の「動画編集スタジオで開く」（`#btnStudioHandoffLong`）押下時、生成された全カット・音声・セリフ/テロップ・BGMをエディタ側のタイムラインへ展開した状態でシームレスに遷移。

## Phase 4: High-Quality OSS TTS Adapter (ElevenLabs Compatible) & YouTube Direct OAuth 2.0 Upload / Scheduled Publishing
- **高品質OSS TTS（ElevenLabs互換）アダプタ層 (`backend/tts_engine.py`, `backend/processors/tts_manager.py`, `backend/main.py`)**:
  - `HighQualityOSSTTSAdapter` (`oss_elevenlabs` / `voxcpm`) を実装し、以下のエンドポイント形式に単一アダプタで対応:
    1. **OpenBMB VoxCPM** (`https://github.com/OpenBMB/VoxCPM.git`): Tokenizer-free 2Bアーキテクチャ、48kHzスタジオ音質、vLLM-Omni (`POST /v1/audio/speech`)、FastAPI (`POST /v1/tts`)、およびElevenLabs互換API対応。Voice Designプロンプト（`voxcpm_prompt`）による自然言語トーン制御と接続不能時のEdge-TTS自動フォールバックを完備。
    2. ElevenLabs互換 `POST /v1/text-to-speech/{voice_id}` および `POST /v1/text-to-speech`
    3. OpenAI Audio Speech互換 `POST /v1/audio/speech` (Kokoro-FastAPI, OpenedAI-Speech等)
    4. F5-TTS / Fish Speech / GPT-SoVITS 汎用 `POST /v1/tts`・`POST /tts`
  - 設定画面（`#groupOssElevenlabs`）および `.env` (`VOXCPM_ENDPOINT_URL`, `VOXCPM_API_KEY`, `VOXCPM_VOICE_ID`, `VOXCPM_PROTOCOL`, `VOXCPM_SAMPLE_RATE`, `OSS_TTS_ENDPOINT_URL`, `OSS_TTS_API_KEY`, `OSS_TTS_VOICE_ID`, `OSS_TTS_PROTOCOL`) で外部TTSエンドポイントURL、APIキー、ボイスID、通信プロトコル、Voice Designプロンプトを指定可能。
  - 音声選択UI（`#proShortsTtsEngine`, `#longVideoTtsEngine`, `#setTtsEngine`, `#editorCutTtsEngine`）において、「無料TTS（VOICEVOX / Edge-TTS）」と「OpenBMB VoxCPM (48kHzスタジオ音質・ElevenLabs互換OSS)」を明快にグループ分けして切り替え可能。
- **YouTube Data API (OAuth 2.0) 直接アップロード ＆ 予約投稿機能 (`backend/services/youtube_service.py`, `backend/main.py`, `#youtubeDirectUploadModal`)**:
  - GoogleアカウントOAuth 2.0連携フロー（`youtube.upload` スコープ対応）とローカルJSON永続化フォールバック（`backend/data/youtube_oauth.json`）を実装。
  - Pro版ショート・Pro版長尺・自動編集画面・動画編集スタジオ書き出し画面に「YouTubeに直接投稿（OAuth・予約投稿）」ボタンおよび専用設定モーダル（`#youtubeDirectUploadModal`）を設置。
  - 投稿設定UI: 動画タイトル、概要欄（説明文）、タグ/ハッシュタグ、公開設定（「公開 `public`」「非公開 `private`」「限定公開 `unlisted`」「予約投稿 `scheduled` + ISO 8601 `publish_at` 日時指定」）、サムネイル画像設定（動画内カット選択またはカスタム画像アップロード）。
  - バックエンドの `POST /api/youtube/direct-upload` にて、`google-api-python-client` の `MediaFileUpload(..., chunksize=10*1024*1024, resumable=True)` を用いたチャンク分割アップロード（Resumable Upload）および `youtube.thumbnails().set` によるカスタムサムネイル自動反映を実装。
- **権限制御・利用可否の基盤連動 (`can_use_premium_tts`, `can_direct_upload_youtube`)**:
  - `backend/services/user_permission_manager.py` および `frontend/js/settings-manager.js` に `can_use_premium_tts`・`can_direct_upload_youtube` フラグを導入:
    - **簡易ショート / ライトプラン相当 (`simple_shorts`)**: 無料TTSのみ、YouTube直接投稿はロックバッジ付きで無効化し、MP4ダウンロードのみに制限。
    - **Pro版 / プロプラン以上（またはBYOGモード）**: 高品質OSS TTSの選択・合成、およびYouTube直接投稿・予約投稿機能を解放。

## Phase 5: Colab Dual-Engine Workflow, BYOG Mode, Stripe Billing & Cloud Run Security Guard
- **ComfyUI 二刀流エンジン切り替えロジック (`backend/processors/colab_gpu_client.py`, `backend/processors/batch_asset_generator.py`)**:
  - 単一のComfyUIエンドポイントに対し、動画リクエスト種別に応じて適切なワークフローJSONを自動ロード・送信:
    1. ショート動画リクエスト（9:16縦型）: **LTX-Video ワークフロー**（T2V / I2V）で高速モーションアニメーション化。
    2. 長尺動画重要カット（16:9横型、scene.type == 'video'）: **MiniMax H3 ワークフロー**で超高精細映画級アニメーション動画を生成。
  - ComfyUIの `/queue` 監視および `/history/{prompt_id}` のタイムアウト付き非同期ポーリングにより、複数リクエスト到達時でも順番待ち処理を担保。
- **BYOG（ユーザー環境持ち込み）設定UI ＆ ルーティング (`#cardByogSettings`, `frontend/js/settings-manager.js`, `frontend/js/app.js`, `frontend/js/api-client.js`)**:
  - 設定画面（`#view-settings`）に「BYOG（自前環境接続）モード」設定パネルを設置:
    1. 自前 ComfyUI URL（trycloudflare / ngrok / ローカル）および自前 Gemini API キーの入力欄。
    2. 「接続テスト」ボタンによる ComfyUI 疎通確認（`/system_stats` / `/queue`）。
    3. BYOG有効時（`byogEnabled: true` または自前URL/キー設定時）、動画生成リクエストは運営側APIではなくユーザー独自のComfyUIエンドポイントへルーティングされ、クレジット消費0で実行可能。
- **Stripe サブスクリプション ＆ クレジット管理システム (`backend/services/billing_manager.py`, `backend/config.py`, `backend/main.py`)**:
  - 料金プラン体系:
    - **ライト**（月額 1,980円）: 300クレジット/月、無料TTSのみ、BGM固定、YouTube直接投稿不可、MP4ダウンロードのみ、スタジオ利用不可。
    - **プロ**（月額 3,980円）: 1,000クレジット/月、高品質VoxCPM TTS開放、BGM差し替え開放、YouTube直接投稿開放、スタジオ利用可能。
    - **プレミアム**（月額 7,980円）: 3,000クレジット/月、全機能フル開放、生成優先キュー。
    - **追加クレジットチャージ（買い切り）**: 200pt (980円) / 600pt (2,480円) / 1,500pt (4,980円)。
  - Stripe Webhook処理 (`POST /api/stripe/webhook`): `checkout.session.completed`, `customer.subscription.created/updated/deleted` を受信し、Firestoreへサブスクリプション有効期限・クレジット残高を自動同期。
  - クレジット減算処理: ショート動画（1カット5pt）および長尺動画（1シーン12pt）の生成前に残高を検証し、不足時はHTTP 402エラーを返却。BYOGモード時は0消費で実行。
- **Cloud Run 本番セキュリティ保護 ＆ アクセス制御 (`backend/main.py`, `frontend/js/auth.js`)**:
  - サロンiframe連携判定: URLパラメータ（`auth_token`, `salon_plan`）および `window.postMessage` (`SALON_AUTH_SYNC`) からトークンを抽出し保持。
  - バックエンドAPI保護ミドルウェア (`security_and_auth_middleware`): 主要生成・投稿エンドポイントへのアクセスに対し、サロントークン（`X-Salon-Token`）またはBearer認証を検証。
  - 単体URL直接アクセスガード: 未認証かつBYOG未設定の場合は画面上部にサロン連携案内バナーを表示。

## Phase 6: マーケティング自動化基盤（外部Webhook/シナリオ連動API）＆ 最終デプロイ準備
- **マーケティング自動化・外部トリガーAPI (`backend/main.py`)**:
  - `POST /api/marketing/trigger-video-job`: 外部シナリオツール（LINE配信, X自動化, ブログ連携等）から完全自動で動画生成ジョブをキックできる汎用エンドポイント。
    - リクエストパラメータ: `marketing_source` (line/x_auto/blog/affiliate等), `topic`/`script` (どちらか必須), `mode` (pro_shorts or long_manga), `style`, `tts_engine`, `webhook_callback_url`, `user_id`
    - 認証: `X-Marketing-Token` ヘッダー（Firestoreに保存された `marketing_api_token` フィールドと照合）
    - バックグラウンドで動画生成パイプラインを実行し、完了時に `webhook_callback_url` へ動画URL・タイトル・概要・テロップ含むJSONをPOST通知
    - レスポンス: `job_id`, `status: "accepted"`, `accepted_at`
  - `POST /api/marketing/generate-token`: Marketing API Tokenの新規発行・再生成（Firestoreの `users/{user_id}.marketing_api_token` に保存）
  - `GET /api/marketing/token/{user_id}`: 現在のトークンのマスク表示取得
  - `POST /api/marketing/test-webhook`: 指定URLへのテスト送信（テストペイロードを使用して疎通確認）
  - Webhook完了通知ライブラリ: `httpx.AsyncClient` による非同期POST（タイムアウト15秒、失敗時は警告ログのみ）
- **外部連携ステータス ＆ Webhook設定UI (`#cardMarketingWebhook`, `frontend/index.html`, `frontend/js/app.js`, `frontend/js/settings-manager.js`)**:
  - 設定画面（`#view-settings`）に「マーケティング連携・Webhook設定」パネルを設置:
    1. Marketing API Token 発行・再生成UI（`#btnGenerateMarketingToken`, `#marketingApiTokenDisplay`）
    2. 外部トリガーAPIエンドポイント情報表示（エンドポイント, 必須ヘッダー, パラメータ一覧）
    3. 完了通知Webhook URLの設定（`#setMarketingWebhookUrl`）とテスト送信ボタン（`#btnTestMarketingWebhook`）
    4. Webhook URL保存ボタン（`#btnSaveMarketingWebhook`、`settingsManager` の `marketingWebhookUrl` キーに永続化）
- **本番デプロイ（Cloud Run）向け環境変数テンプレート (`.env.example`)**:
  - 全環境変数を網羅: Gemini API, Firebase/Firestore, YouTube OAuth 2.0, Stripe (Secret/Publishable/Webhook), VoxCPM/OSS TTS, Cloudflare Tunnel/ComfyUI, セキュリティ (SALON_SHARED_SECRET, REQUIRE_AUTH_API), Marketing API, Cloud Run デプロイ設定, GCS バケット
  - 各変数にコメントでデプロイ手順・注意事項を記載済み
  - 本番環境では `REQUIRE_AUTH_API=true` を推奨

## Phase 7: salon-cloudrun-tools 仕様準拠（サロンプラットフォーム統合・SSOハンドシェイク・セキュリティヘッダー）
- **Iframe 埋め込み ＆ セキュリティヘッダー設定 (`backend/main.py`)**:
  - `X-Frame-Options: DENY` を完全排除。
  - `Content-Security-Policy: frame-ancestors 'self' https://kimiiro-salon.web.app https://*.web.app http://localhost:3000;` を全レスポンスに付与し、サロンプラットフォームからの埋め込みを安全に許可。
- **Salon SSO ハンドシェイクの完全適合 (`backend/main.py`, `frontend/js/auth.js`)**:
  - 親ウィンドウからの `postMessage`（`SALON_AUTH_SYNC`, `INIT_CONTEXT`）およびURLパラメータ（`user_email`, `user_id`, `role`, `is_admin`, `from_salon=true`）を受け取るSSO認証フロー。
  - `POST /api/auth/sso`: サロンセッション（email, id, role, plan）を検証・Firestore同期し、即座にツールを開放。
  - スタンドアロン直接アクセス時: 既存のログイン画面（`#loginPage`）を表示し、不正アクセスを防止。
  - PostMessageブリッジ: `window.sendDraftToSalon(title, content, targetCollection)` により、サロンの `columns` または `contents` 下書きコレクションへ直接下書き保存可能。
- **管理者ユーザー管理パネルの表示制御 (`frontend/index.html`, `frontend/js/app.js`)**:
  - ログイン中ユーザーが master administrator（`oumaumauma32@gmail.com` または `role: 'admin'`）の場合のみ、ヘッダー右上に「管理者設定 (ユーザー管理)」ボタン（`#btnHeaderAdminSettings`）を表示。
  - サイドバーの「管理者ダッシュボード」ナビ項目と完全連動。
- **Cloud Run 本番デプロイ ＆ サロンプラットフォーム登録情報**:
  - **本番サービスURL**: `https://kimidori-youtube-auto-xfl36wickq-an.a.run.app`
  - **Cloud Run サービス名**: `kimidori-youtube-auto` (Region: `asia-northeast1`, Project: `kimiiro-salon`)
  - **Firestore 登録先**: `custom_tools/cr_1791814765113` および `portal_data/custom_tools`
  - **サロンプラットフォーム表示**: `https://kimiiro-salon.web.app/tools` 配下の「コンテンツ制作」カテゴリにて公開中

## Phase 8: プラン体系統一（free_trial対応）＆ 管理者ホワイトリスト厳格化 ＆ 買い切り79,800円反映
- **管理者判定の厳格化（サロンAdminフラグ昇格の完全廃止） (`backend/main.py`, `backend/services/user_permission_manager.py`, `frontend/js/auth.js`, `frontend/js/app.js`)**:
  - サロンSSO連携時、サロン側の `role: 'admin'` や `is_admin: true` を理由にマスター管理者（ユーザー管理やColab無制限）へ昇格させる処理を【完全に廃止】。
  - マスター管理者は `oumaumauma32@gmail.com` のみに厳格限定。
  - 「家族・共有Colab利用メンバー」は、ツール側の事前登録リスト（Firestoreの `allowed_colab_users` コレクション、ドキュメント、または `users` テーブルの `can_use_shared_colab` / `allowed_colab` 属性）に登録されたメールアドレスと一致する場合のみ、BYOG/Colab無制限モードを適用。
- **プラン名称・識別子の完全統一 ＆ 買い切り79,800円反映 (`backend/config.py`, `backend/services/billing_manager.py`, `frontend/js/settings-manager.js`, `frontend/index.html`, `frontend/js/app.js`)**:
  - 統一プラン体系:
    1. `free_trial`（無料体験枠）: 簡易ショートのみ、動画編集スタジオ利用不可、BGM固定、YouTube直接投稿不可（0円 / 30 pt）
    2. `standard`（旧lite / スタンダード）: 300 pt、動画編集スタジオ利用不可、MP4保存のみ、無料TTS（月額 1,980円）
    3. `premium`（旧pro / プレミアム）: 1,000 pt、動画編集スタジオ利用可能、高品質VoxCPM TTS開放、YouTube直接投稿開放（月額 3,980円）
    4. `master`（旧premium / マスター）: 3,000 pt、全機能フル開放、優先キュー処理（月額 7,980円）
    5. `byog_purchased`（買い切り 79,800円）: 無制限（0 pt消費）、自前環境セットアップガイド表示、スタジオ＆全機能フル開放（一括 79,800円）
  - サロンSSO（`POST /api/auth/sso`）受信時、`salon_plan` が `free_trial` / `standard` / `premium` / `master` のいずれかであれば、ツールの該当プランへ自動同期。
  - 後方互換性エイリアス（`lite` -> `standard`, `pro` -> `premium`, `free` -> `free_trial`）を完備。
  - Stripe Checkout Session 発行および Webhook 処理にて `byog_purchased`（`mode: "payment"`, unit_amount: 79800）の決済・権限付与を完全サポート。





