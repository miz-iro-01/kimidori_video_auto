const express = require('express');
const cors = require('cors');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 8080;
const GEMINI_API_KEY = process.env.GEMINI_API_KEY || '';

// Enable CORS
app.use(cors());
app.use(express.json());

// Iframe Security Headers Middleware
app.use((req, res, next) => {
  // Remove restrictive frame headers
  res.removeHeader('X-Frame-Options');
  // Allow embedding from Salon and localhost
  res.setHeader(
    'Content-Security-Policy',
    "frame-ancestors 'self' https://kimiiro-salon.web.app https://*.web.app http://localhost:3000;"
  );
  next();
});

// Health check endpoint for Cloud Run
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'salon-express-tool', timestamp: new Date().toISOString() });
});

// AI Generation API Endpoint
app.post('/api/generate', async (req, res) => {
  const { theme, category = 'catchphrase', systemPrompt = '' } = req.body;

  if (!theme || !theme.trim()) {
    return res.status(400).json({ error: 'Theme is required' });
  }

  // Construct prompt
  let instruction = systemPrompt;
  if (!instruction) {
    if (category === 'catchphrase') {
      instruction = 'あなたは一流のマーケターです。ターゲットの目を奪う魅力的なキャッチコピーを5つ作成してください。';
    } else if (category === 'summary') {
      instruction = 'あなたは優秀なエディターです。内容を3つの要点にまとめ、具体的なネクストアクションを提示してください。';
    } else {
      instruction = 'あなたは新規事業企画のプロです。このテーマから発展させられる画期的なアイデアを3つ提示してください。';
    }
  }

  // Generate output (if API key available or fallback sample)
  if (GEMINI_API_KEY) {
    try {
      const { GoogleGenAI } = require('@google/genai');
      const ai = new GoogleGenAI({ apiKey: GEMINI_API_KEY });
      const response = await ai.models.generateContent({
        model: 'gemini-1.5-flash',
        contents: `${instruction}\n\nテーマ: ${theme}`
      });
      return res.json({ status: 'success', output: response.text });
    } catch (err) {
      return res.json({
        status: 'error',
        message: err.message,
        output: `[生成エラー] ${err.message}`
      });
    }
  } else {
    // Demonstration mock response
    const mockOutput = `[デモ出力 - APIキー未設定]\n` +
      `テーマ「${theme}」に関する提案:\n\n` +
      `1. 【成果直結】今日からできる！${theme}実践の3ステップ\n` +
      `2. なぜ9割の人が${theme}でつまずくのか？解決策を公開\n` +
      `3. ゼロから最短で成果を出す！${theme}徹底マスター講座\n\n` +
      `※ 本番環境では環境変数 GEMINI_API_KEY を設定してください。`;
    return res.json({ status: 'success', output: mockOutput });
  }
});

// Serve static frontend
app.use(express.static(path.join(__dirname, 'public')));

app.listen(PORT, '0.0.0.0', () => {
  console.log(`[OK] Salon Express Tool listening on port ${PORT}`);
});
