---
description: Google Cloud Run効率化ツールの開発・デプロイ・サロンプラットフォーム連携および他プロジェクトでの共有
---

# Salon Cloud Run Tools ワークフロー

Google Cloud Run を使用してサロンプラットフォーム配下の効率化ツールを開発・デプロイし、他プロジェクト間でも共有・再利用するためのワークフローです。

## 実行手順

1. **スキル指示書の読み込み**:
   `salon-cloudrun-tools` スキルの指示に従って進めます。

2. **ツール開発とコンテナ化**:
   - Python (FastAPI) または Node.js (Express) の標準テンプレートを使用。
   - `PORT=8080` バインドおよび `GET /health` エンドポイントを実装。
   - サロン埋め込み用 CSP ヘッダー (`frame-ancestors 'self' https://kimiiro-salon.web.app http://localhost:3000`) を設定。
   - 生成データをサロンの下書き（コラム/コンテンツ）へ直接送信する `postMessage` (`SAVE_DRAFT`) を実装。

3. **Google Cloud Run へのデプロイ**:
   - リージョン: `asia-northeast1` (東京)
   - 認証: `--allow-unauthenticated`
   - 自動デプロイスクリプト (`deploy-cloudrun.ps1` または `deploy-cloudrun.sh`) を実行。

4. **サロンプラットフォームへの登録**:
   - `register-tool.mjs` を実行してサロンの `/tools` 画面に即時反映。

5. **他プロジェクトでの再利用**:
   - iframeウィジェット埋め込み、または REST API 連携。

$ARGUMENTS
