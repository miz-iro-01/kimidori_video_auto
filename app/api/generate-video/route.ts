import { generateVideoWithLTX, checkComfyUIHealth, ComfyUIError } from '../../../lib/comfyui-client';
import { LTXVideoOptions } from '../../../types/video';

// JSONレスポンス生成ヘルパー（Next.js App Router準拠）
function jsonResponse(data: any, init?: { status?: number; headers?: Record<string, string> }): Response {
  return new Response(JSON.stringify(data), {
    status: init?.status ?? 200,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });
}

/**
 * POST /api/generate-video
 * ComfyUI (LTX-Video) への動画生成リクエスト
 */
export async function POST(req: Request): Promise<Response> {
  try {
    let body: any;
    try {
      body = await req.json();
    } catch {
      return jsonResponse(
        { error: '無効なJSONリクエストです。' },
        { status: 400 }
      );
    }

    const { prompt, options } = body as { prompt?: string; options?: LTXVideoOptions };

    if (!prompt || typeof prompt !== 'string' || prompt.trim() === '') {
      return jsonResponse(
        { error: 'プロンプト (prompt) は必須項目です。' },
        { status: 400 }
      );
    }

    // LTX-Video生成・ポーリング処理を実行
    const result = await generateVideoWithLTX(prompt.trim(), options);

    return jsonResponse(result, { status: 200 });
  } catch (error: any) {
    if (error instanceof ComfyUIError) {
      return jsonResponse(
        {
          error: error.message,
          code: error.code,
        },
        { status: error.statusCode }
      );
    }

    return jsonResponse(
      {
        error: '動画生成中に予期せぬエラーが発生しました。',
        details: error?.message || String(error),
      },
      { status: 500 }
    );
  }
}

/**
 * GET /api/generate-video
 * ComfyUI (Google Colab) 疎通ヘルスチェック
 */
export async function GET(): Promise<Response> {
  const health = await checkComfyUIHealth();
  // UI側でトラブルシューティング情報を表示できるように200で詳細オブジェクトを返却
  return jsonResponse(health, { status: 200 });
}
