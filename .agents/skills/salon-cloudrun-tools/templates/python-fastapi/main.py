import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai

app = FastAPI(title="Salon Efficiency Tool API", version="1.0.0")

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom Middleware for Iframe Security Headers
@app.middleware("http")
async def add_iframe_security_headers(request: Request, call_next):
    response = await call_next(request)
    # Remove restrictive headers if present
    response.headers.pop("x-frame-options", None)
    # Permit embedding by the Salon platform and localhost
    response.headers["Content-Security-Policy"] = (
        "frame-ancestors 'self' https://kimiiro-salon.web.app https://*.web.app http://localhost:3000;"
    )
    return response

# Request Body Schema
class GenerateRequest(BaseModel):
    theme: str
    category: str = "catchphrase"
    system_prompt: str = ""

# AI Generation Engine
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

@app.get("/health")
def health():
    return {"status": "ok", "service": "salon-efficiency-tool", "version": "1.0.0"}

@app.post("/api/generate")
async def generate_content(req: GenerateRequest):
    if not req.theme.strip():
        return JSONResponse(status_code=400, content={"error": "Theme is required"})

    prompt = f"テーマ: {req.theme}\n分類: {req.category}\n"
    if req.category == "catchphrase":
        system_instruction = req.system_prompt or (
            "あなたはプロのコピーライターです。読者の注意を惹き、クリック率と成約率を最大化する"
            "キャッチコピーを5パターン作成してください。各コピーには簡単な訴求ポイントの解説を添えてください。"
        )
    elif req.category == "summary":
        system_instruction = req.system_prompt or (
            "あなたは編集ディレクターです。提供されたテーマまたは文章を簡潔に要約し、"
            "3つの重要ポイントと実践アクションに整理してください。"
        )
    else:
        system_instruction = req.system_prompt or (
            "あなたはコンテンツプランナーです。このテーマから展開できる独自の企画アイデアを"
            "3つ提案してください。各企画のターゲット層と期待できる成果を含めてください。"
        )

    full_prompt = f"{system_instruction}\n\n{prompt}"

    if GEMINI_KEY:
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(full_prompt)
            output_text = response.text
        except Exception as e:
            output_text = f"[AI生成エラー] {str(e)}\n\n入力テーマ: {req.theme}"
    else:
        output_text = (
            f"[デモ出力 - APIキー未設定]\n"
            f"テーマ「{req.theme}」に基づく自動生成サンプル:\n\n"
            f"1. 【注目度No.1】たった5分で劇的改善！{req.theme}の超実践メソッド\n"
            f"2. プロが明かす！なぜ今{req.theme}が必要なのか？徹底解説\n"
            f"3. 初心者から上級者まで！成果を最大化する{req.theme}完全攻略ガイド\n\n"
            f"※ 本番環境では環境変数 GEMINI_API_KEY を設定してください。"
        )

    return {"status": "success", "theme": req.theme, "output": output_text}

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    html_content = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>サロン効率化ツール - AIコンテンツ生成</title>
  <style>
    :root {
      --primary: #84cc16;
      --primary-dark: #65a30d;
      --primary-deep: #166534;
      --bg: #f8fafc;
      --surface: #ffffff;
      --text: #0f172a;
      --text-muted: #64748b;
      --border: #e2e8f0;
      --radius: 12px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background: var(--bg); color: var(--text); padding: 1.5rem; }
    .container { max-width: 900px; margin: 0 auto; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 2rem; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }
    .header { display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border); padding-bottom: 1rem; margin-bottom: 1.5rem; }
    .title { font-size: 1.25rem; font-weight: 800; color: var(--primary-deep); }
    .badge { font-size: 0.75rem; font-weight: 700; background: #ecfccb; color: var(--primary-deep); padding: 0.25rem 0.6rem; border-radius: 9999px; }
    .tabs { display: flex; gap: 0.5rem; margin-bottom: 1.25rem; }
    .tab-btn { padding: 0.5rem 1rem; border-radius: 8px; border: 1px solid var(--border); background: var(--surface); color: var(--text-muted); font-size: 0.875rem; font-weight: 700; cursor: pointer; transition: all 0.2s; }
    .tab-btn.active { background: #f7fee7; border-color: var(--primary); color: var(--primary-deep); }
    .form-group { margin-bottom: 1.25rem; }
    label { display: block; font-size: 0.875rem; font-weight: 700; margin-bottom: 0.5rem; color: var(--text); }
    textarea, input { width: 100%; padding: 0.75rem 1rem; border: 1px solid var(--border); border-radius: 8px; font-size: 0.95rem; line-height: 1.5; outline: none; transition: border-color 0.2s; }
    textarea:focus, input:focus { border-color: var(--primary); }
    .actions { display: flex; justify-content: flex-end; gap: 0.75rem; margin-bottom: 1.5rem; }
    .btn { display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.75rem 1.5rem; border-radius: 8px; font-size: 0.95rem; font-weight: 700; cursor: pointer; border: none; transition: background 0.2s; }
    .btn-primary { background: var(--primary); color: white; }
    .btn-primary:hover { background: var(--primary-dark); }
    .btn-secondary { background: #f1f5f9; color: var(--text); }
    .btn-secondary:hover { background: #e2e8f0; }
    .btn-success { background: #059669; color: white; }
    .btn-success:hover { background: #047857; }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .output-card { background: #f8fafc; border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; margin-top: 1.5rem; }
    .output-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; font-size: 0.875rem; font-weight: 700; color: var(--primary-deep); }
    .output-body { white-space: pre-wrap; font-size: 0.95rem; line-height: 1.7; color: var(--text); }
    .toast { position: fixed; bottom: 1.5rem; right: 1.5rem; background: #0f172a; color: white; padding: 0.75rem 1.25rem; border-radius: 8px; font-size: 0.875rem; display: none; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="title">Cloud Run 効率化ツール: AIライティングスタジオ</div>
      <div class="badge">サロン統合モード</div>
    </div>

    <div class="tabs">
      <button class="tab-btn active" onclick="setCategory('catchphrase', this)">キャッチコピー</button>
      <button class="tab-btn" onclick="setCategory('summary', this)">文章要約・整理</button>
      <button class="tab-btn" onclick="setCategory('idea', this)">企画発想</button>
    </div>

    <div class="form-group">
      <label for="themeInput">テーマ / キーワード / 素材文</label>
      <textarea id="themeInput" rows="4" placeholder="例: 個人開発者のためのSNS集客戦略、副業マーケティングの始め方"></textarea>
    </div>

    <div class="actions">
      <button id="genBtn" class="btn btn-primary" onclick="generate()">AIで一括生成する</button>
    </div>

    <div id="outputArea" style="display: none;">
      <div class="output-card">
        <div class="output-header">
          <span>AI生成結果プレビュー</span>
          <div style="display: flex; gap: 0.5rem;">
            <button class="btn btn-secondary" style="padding: 0.4rem 0.8rem; font-size: 0.8rem;" onclick="copyOutput()">コピー</button>
            <button class="btn btn-success" style="padding: 0.4rem 0.8rem; font-size: 0.8rem;" onclick="sendDraft('columns')">コラム下書きに送信</button>
            <button class="btn btn-success" style="padding: 0.4rem 0.8rem; font-size: 0.8rem;" onclick="sendDraft('contents')">コンテンツ下書きに送信</button>
          </div>
        </div>
        <div id="outputContent" class="output-body"></div>
      </div>
    </div>
  </div>

  <div id="toast" class="toast"></div>

  <script>
    let currentCategory = 'catchphrase';

    function setCategory(cat, el) {
      currentCategory = cat;
      document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
      el.classList.add('active');
    }

    async function generate() {
      const theme = document.getElementById('themeInput').value.trim();
      if (!theme) {
        showToast('テーマを入力してください');
        return;
      }
      const btn = document.getElementById('genBtn');
      btn.disabled = true;
      btn.innerText = 'AI生成中...';

      try {
        const res = await fetch('/api/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ theme: theme, category: currentCategory })
        });
        const data = await res.json();
        document.getElementById('outputContent').innerText = data.output;
        document.getElementById('outputArea').style.display = 'block';
        showToast('生成が完了しました');
      } catch (err) {
        showToast('エラーが発生しました: ' + err.message);
      } finally {
        btn.disabled = false;
        btn.innerText = 'AIで一括生成する';
      }
    }

    function copyOutput() {
      const text = document.getElementById('outputContent').innerText;
      navigator.clipboard.writeText(text);
      showToast('クリップボードにコピーしました');
    }

    function sendDraft(target) {
      const text = document.getElementById('outputContent').innerText;
      const theme = document.getElementById('themeInput').value.trim();
      const title = theme ? `${theme} (AI生成)` : '外部ツール作成下書き';

      if (window.parent && window.parent !== window) {
        window.parent.postMessage({
          type: 'SAVE_DRAFT',
          title: title,
          content: text,
          targetCollection: target
        }, '*');
        showToast(`サロンの${target === 'columns' ? 'コラム' : 'コンテンツ'}下書きへ送信しました`);
      } else {
        showToast('スタンドアロンモードのため、下書きファイルをローカルダウンロードします');
        const blob = new Blob([`# ${title}\n\n${text}`], { type: 'text/markdown' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `${title}.md`;
        a.click();
      }
    }

    function showToast(msg) {
      const t = document.getElementById('toast');
      t.innerText = msg;
      t.style.display = 'block';
      setTimeout(() => { t.style.display = 'none'; }, 3000);
    }
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
