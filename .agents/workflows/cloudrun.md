---
description: Google Cloud Run効率化ツールの開発・デプロイ・サロンプラットフォーム連携および他プロジェクト共有
---

# Google Cloud Run ツール開発・デプロイ・連携ワークフロー

Google Cloud Run を使用してサロンプラットフォーム配下の効率化ツールを開発・デプロイし、他プロジェクト間でも共有・再利用するための標準ワークフローです。

## 実行手順

1. **スキル仕様の確認**:
   `salon-cloudrun-tools` スキルの `SKILL.md` を読み込み、コンテナ構成と連携手順を確認する。

2. **ツール実装とコンテナ化**:
   - Python (FastAPI) または Node.js (Express) の標準テンプレートを使用。
   - `PORT=8080` バインドおよび `GET /health` エンドポイントを実装。
   - サロン埋め込み用 CSP ヘッダー (`frame-ancestors 'self' https://kimiiro-salon.web.app http://localhost:3000`) を設定。
   - 生成データをサロンの下書き（コラム/コンテンツ）へ直接送信する `postMessage` (`SAVE_DRAFT`) を実装。

3. **Google Cloud Run へのデプロイ**:
   - リージョン: `asia-northeast1` (東京)
   - 認証: `--allow-unauthenticated`
   - メモリ: 512Mi〜1Gi, 最小インスタンス: 0, 最大インスタンス: 5
   - 自動デプロイスクリプト (`deploy-cloudrun.ps1` または `deploy-cloudrun.sh`) を実行。

4. **サロンプラットフォームへの登録**:
   - `node scripts/register-tool.mjs --name "<ツール名>" --url "<Cloud Run URL>" --category "<カテゴリ>" --role "user"` を実行。
   - サロンの `/tools` 画面に即時反映。

5. **他プロジェクトでの再利用**:
   - iframeウィジェット埋め込み (`<iframe src="...">`)
   - REST API 呼び出し (`POST /api/generate`)

$ARGUMENTS
