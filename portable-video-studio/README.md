# Video Studio Hub (Portable Edition)

台本執筆・絵コンテ展開・リアルタイムサムネイル生成ギャラリーを備えた、完全自己完結型（ポータブル）の動画制作スタジオパッケージです。

重いブラウザ自動化（PlaywrightやGoogle Flow操作）を完全に排除し、**「台本入力と自動解析」「カット別タイムライン」「生成中の素材が次々とサムネイル表示されるリアルタイムUI」**というコアUXを1つのフォルダに抽出しています。

---

## 1. フォルダ構成（このフォルダ1つで丸ごとコピー可能）

```
portable-video-studio/
├── app.py                  # 軽量FastAPIサーバー（REST API & 静的配信）
├── script_generator.py      # Gemini APIによる高速5章台本生成（タイムスタンプ保証）
├── storyboard_generator.py  # 台本→絵コンテ解析エンジン（カット・演出・秒数抽出）
├── generator_hook.py       # プラグ可能素材生成フック（任意の画像生成AIに差し替え可能）
├── templates/
│   └── index.html          # 洗練された左右分割スタジオUI（iframe埋め込み対応）
├── static/
│   ├── app.js              # スタジオ操作・リアルタイムサムネイル反映・postMessage連携
│   └── style.css           # ダークテーマ・グラスモーフィズムデザイン
├── input_scripts/          # 台本テキスト・絵コンテJSONの自動保存先
├── output/                 # 生成アセット（画像・動画）保存先
├── requirements.txt        # 最小限の依存関係（fastapi, uvicorn, aiohttp, pillow）
└── README.md               # 本ドキュメント
```

---

## 2. 起動方法（クイックスタート）

### ステップ1: 依存ライブラリのインストール
```bash
cd portable-video-studio
pip install -r requirements.txt
```

### ステップ2: サーバー起動
```bash
python app.py
```
ブラウザで `http://127.0.0.1:8080` を開くとスタジオ画面が表示されます。

---

## 3. コア機能とUX

### ① 左右分割ワークスペース
- **左画面（台本エリア）**:
  - **Gemini API台本生成**: テーマを入力するだけで、全5章・タイムスタンプ付きの台本を並列高速生成。
  - **直接入力 & 自動解析**: 台本を貼り付けると500msのデバウンスで自動的に絵コンテを解析。
- **上部プログレスバー**:
  - 現在の進捗率（%）と処理状況（カット番号・ステップ）をリアルタイム表示。
- **右画面（ビジュアルエリア）**:
  - **タブ1: 絵コンテリスト**: カットID、タイム、話者、セリフ、シーン描写、演出指示を一覧表で確認。
  - **タブ2: 生成アセット一覧**: 生成された画像や動画が、リアルタイムに次々とサムネイルカードとして追加・表示されるダイナミックギャラリー。
  - **タブ3: タイムライン調整**: 各カットの表示秒数をスライダー/数値で微調整。

### ② リアルタイムサムネイル描画の仕組み
1. 「素材生成開始」を押すと、画面が自動的に「生成アセット一覧」タブへ切り替わります。
2. バックグラウンドで素材が1カット完成するごとに `output/<project_name>/` にファイルが保存されます。
3. フロントエンドが約1.5秒間隔でポーリングし、新しいカットが追加されると即座にアニメーション付きでサムネイルカード（または動画プレーヤー）を描画します。
4. 途中停止しても、既存の生成済み素材を保持したまま「続きから生成を再開 (Cut_XXX〜)」ボタンで安全に再開できます。

---

## 4. 他プロジェクトへの3つの組み込み方法

### 方法A: フォルダごと別プロジェクトにコピーして単独起動
本フォルダ `portable-video-studio` をそのまま移動し、`python app.py` でポート（環境変数 `PORT`）を指定して起動します。

### 方法B: 既存のWebツール（きみいろサロン /tools 等）に iframe 埋め込み
本スタジオは iframe 埋め込みを前提としたヘッダー（`Content-Security-Policy: frame-ancestors *`）を設定済みです。

#### 埋め込みHTML例:
```html
<iframe 
  src="http://127.0.0.1:8080" 
  style="width: 100%; height: 850px; border: none; border-radius: 12px;"
  sandbox="allow-scripts allow-same-origin allow-forms allow-popups">
</iframe>
```

#### 双方向通信（postMessage）:
- **親からスタジオへ台本を渡す**:
  ```javascript
  iframeEl.contentWindow.postMessage({
      type: 'LOAD_SCRIPT',
      script: '【タイトル】：... [00:00] Cut_001 ...'
  }, '*');
  ```
- **スタジオから親へ下書きを保存する**:
  スタジオヘッダーの「下書き連携」ボタンを押すと、親ウィンドウに以下のイベントが送信されます：
  ```javascript
  window.addEventListener('message', (event) => {
      if (event.data?.type === 'SAVE_DRAFT') {
          console.log('受信した台本:', event.data.content);
          console.log('受信した絵コンテ:', event.data.storyboard);
          // 親側のFirestoreやデータベースに保存
      }
  });
  ```

### 方法C: 自前の画像生成AI（DALL-E, ComfyUI, Midjourney等）へ差し替え
`generator_hook.py` 内の `generate_asset` メソッドを好みのAPI呼び出しに書き換えるだけで、お好みの生成AIエンジンと完全に連携できます。

```python
# generator_hook.py の書き換え例 (OpenAI DALL-E 3連携)
async def generate_asset(self, cut: dict, output_path: str, format_ratio: str = "16:9"):
    prompt = cut.get("visual_prompt", "")
    # OpenAI API呼び出し
    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1792x1024",
        response_format="b64_json"
    )
    # output_path に画像バイナリを保存
    ...
```

また、外部スクリプトから完成画像を投入したい場合は、以下のAPIを叩くだけでリアルタイム反映されます：
```bash
curl -X POST http://127.0.0.1:8080/api/upload-asset \
  -F "cut_number=1" \
  -F "file=@/path/to/my_image.png"
```

---

## 5. 主なREST API一覧

| メソッド | パス | 説明 |
| :--- | :--- | :--- |
| `GET` | `/` | スタジオUI画面を返却 |
| `GET` | `/health` | ヘルスチェック (200 OK) |
| `POST` | `/api/generate-ai-script` | Gemini APIによる台本自動生成 |
| `POST` | `/api/parse-storyboard` | 台本テキストの絵コンテ解析・タイムスタンプ付与 |
| `GET` | `/api/current-storyboard` | 現在の台本および絵コンテJSONの取得 |
| `GET` | `/api/status` | 現在の生成進捗・稼働ステータス取得 |
| `GET` | `/api/assets` | 生成済み画像・動画の一覧取得 |
| `POST` | `/api/start-production` | 素材生成タスクの開始 |
| `POST` | `/api/upload-asset` | 外部からのアセット画像・動画直接アップロード |
| `POST` | `/api/regenerate-cut` | 単一カットの再生成 |
