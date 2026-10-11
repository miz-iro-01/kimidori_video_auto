// ==========================================
// 1. プラン別型定義
// ==========================================

export type PlanTier = 'light' | 'standard' | 'pro';

export type TTSEngineType = 'edge-tts' | 'elevenlabs' | 'openai-tts';

export interface PlanConfig {
  tier: PlanTier;
  name: string;
  priceJPY: number;
  monthlyPoints: number;
  allowCustomBGM: boolean;
  allowedTTSEngines: TTSEngineType[];
  maxVideoDurationSeconds: number;
  maxHighlightCutsPerVideo: number;
}

// ==========================================
// 2. カット種別型定義
// ==========================================

export type CutType = 'highlight' | 'midroll' | 'stock';

export type HighlightVideoModel = 'minimax' | 'ltx-video';

export type ImageGenerationModel = 'krea' | 'flux-dev' | 'flux-schnell';

export type FfmpegEffectType = 'zoom_in' | 'zoom_out' | 'pan_left' | 'pan_right' | 'subtle_bounce';

// 見せ場カット（高品質AI動画: fal.ai MiniMax / LTX-Video I2V）
export interface HighlightCutConfig {
  type: 'highlight';
  model: HighlightVideoModel;
  prompt: string;
  sourceImageUrl?: string;
  durationSeconds: number; // 2〜3秒（最大49フレーム）
  maxFrames: number; // 49フレーム以内
}

// 中盤・解説カット（静止画 + ffmpegズーム・パン演出）
export interface MidrollCutConfig {
  type: 'midroll';
  model: ImageGenerationModel;
  prompt: string;
  effect: FfmpegEffectType;
  durationSeconds: number;
}

// インサートカット（Pexels API無料ストック動画・画像）
export interface StockCutConfig {
  type: 'stock';
  mediaType: 'video' | 'image';
  query: string;
  sourceUrl: string;
  durationSeconds: number;
}

export type CutConfig = HighlightCutConfig | MidrollCutConfig | StockCutConfig;

// ==========================================
// 3. アクション種別・リクエスト型定義
// ==========================================

export type ActionType =
  | 'generate_short_video'
  | 'generate_long_video'
  | 'generate_highlight_cut'
  | 'generate_midroll_cut'
  | 'fetch_stock_cut'
  | 'generate_tts_audio'
  | 'upload_custom_bgm';

export interface ActionCost {
  actionType: ActionType;
  basePoints: number;
  description: string;
}

export interface GenerateShortVideoRequest {
  title: string;
  script: string;
  bgmId?: string;
  ttsEngine: TTSEngineType;
  highlightCutsCount: number;
  midrollCutsCount: number;
  stockCutsCount: number;
}

export interface GenerateLongVideoRequest {
  title: string;
  script: string;
  bgmId?: string;
  ttsEngine: TTSEngineType;
  highlightCutsCount: number;
  midrollCutsCount: number;
  stockCutsCount: number;
  estimatedDurationMinutes: number;
}

// ==========================================
// 4. クレジット・ポイント型定義
// ==========================================

export type TransactionType = 'monthly_grant' | 'topup_purchase' | 'usage_deduction' | 'refund';

export interface CreditTransaction {
  id: string;
  userId: string;
  type: TransactionType;
  amount: number; // 付与・購入は正、消費は負
  actionType?: ActionType;
  description: string;
  createdAt: Date;
}

export interface UserCreditProfile {
  userId: string;
  planTier: PlanTier;
  currentPoints: number;
  monthlyResetDate: Date;
  updatedAt: Date;
}

export interface PointPurchaseOption {
  points: number;
  priceJPY: number;
}

// ==========================================
// 5. ComfyUI / LTX-Video 動画生成型定義
// ==========================================

export interface LTXVideoOptions {
  width?: number;          // デフォルト: 768
  height?: number;         // デフォルト: 512
  frameRate?: number;      // デフォルト: 25
  numFrames?: number;      // デフォルト: 97 (約3.8秒)
  seed?: number;
  steps?: number;          // デフォルト: 20
  cfg?: number;            // デフォルト: 3.0
  negativePrompt?: string;
  imageFilename?: string;  // Image-to-Video用
}

export interface ComfyUIOutputFileInfo {
  filename: string;
  subfolder: string;
  type: string;
}

export interface GenerateVideoResult {
  promptId: string;
  videoUrl: string;
  fileInfo: ComfyUIOutputFileInfo;
  status: 'completed' | 'failed';
  isFallback?: boolean;
  warning?: string;
}

export interface HealthCheckResult {
  status: 'ok' | 'error';
  message: string;
  comfyuiUrl?: string;
  statusCode?: number;
  details?: string;
  isFallback?: boolean;
  troubleshooting?: string[];
}

