import os
import sys
import json
import shutil
import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, BackgroundTasks, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel

from storyboard_generator import parse_script_to_storyboard, normalize_script_with_timestamps
from script_generator import AIScriptGenerator
from generator_hook import AssetGeneratorHook

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

app = FastAPI(title="Video Studio Hub - Portable")

# Iframe埋め込み許可ミドルウェア (サロン/toolsや外部CMSから自由に埋め込み可能)
@app.middleware("http")
async def add_iframe_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "frame-ancestors *;"
    if "X-Frame-Options" in response.headers:
        del response.headers["X-Frame-Options"]
    return response

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
INPUT_DIR = BASE_DIR / "input_scripts"
OUTPUT_DIR = BASE_DIR / "output"

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/output_assets", StaticFiles(directory=str(OUTPUT_DIR)), name="output_assets")

# ==========================================
# Pydantic Request Models
# ==========================================
class ScriptRequest(BaseModel):
    script: str
    format: str = "16:9"
    video_type: str = "long"
    style: str = "manga_color"
    genre: str = "business"
    thumbnail_style: str = "split"

class AIScriptRequest(BaseModel):
    theme: str
    genre: str = "business"
    video_type: str = "long"
    length_minutes: int = 18
    api_key: str = ""

class RegenerateCutRequest(BaseModel):
    cut_number: int
    project_name: Optional[str] = None

# ==========================================
# Global Production State
# ==========================================
production_state = {
    "is_running": False,
    "is_completed": False,
    "progress": 0,
    "status_text": "待機中",
    "detail": "台本を入力・生成すると自動解析され、「素材生成開始」を押せます。",
    "current_project": "",
    "total_cuts": 0,
    "completed_cuts": 0
}

# ==========================================
# Routes & API Endpoints
# ==========================================
@app.get("/", response_class=HTMLResponse)
async def read_root():
    index_file = TEMPLATES_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>index.html not found</h1>", status_code=404)
    with open(index_file, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/health")
async def health_check():
    return {"status": "ok", "app": "video-studio-hub-portable"}

@app.post("/api/generate-ai-script")
async def generate_ai_script(req: AIScriptRequest):
    api_key = req.api_key or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return JSONResponse({"status": "error", "message": "Gemini APIキーを入力または設定してください。"}, status_code=400)

    try:
        generator = AIScriptGenerator(api_key=api_key)
        if req.video_type == "short":
            script = await generator.generate_short_script(theme=req.theme, genre=req.genre)
        else:
            script = await generator.generate_complete_long_script(theme=req.theme, genre=req.genre)

        cuts = parse_script_to_storyboard(script, genre=req.genre)
        normalized_script = normalize_script_with_timestamps(script, cuts)

        # 保存
        with open(INPUT_DIR / "studio_project.txt", "w", encoding="utf-8") as f:
            f.write(normalized_script)
        with open(INPUT_DIR / "studio_project_storyboard.json", "w", encoding="utf-8") as f:
            json.dump(cuts, f, ensure_ascii=False, indent=2)

        return {"status": "success", "script": normalized_script, "cuts": cuts}
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/api/parse-storyboard")
async def parse_storyboard(req: ScriptRequest):
    cuts = parse_script_to_storyboard(
        req.script, 
        style=req.style, 
        genre=req.genre, 
        thumbnail_style=req.thumbnail_style, 
        format=req.format
    )
    normalized_script = normalize_script_with_timestamps(req.script, cuts)

    raw_spks = list(set([cut.get("speaker", "ナレーション") for cut in cuts if cut.get("speaker")]))
    filtered_spks = [s for s in raw_spks if s and s not in ["【サムネイル画像】", "セリフ", "話者", "キャラクター", "ナレーション", "メイン解説者", "解説者", "語り手", "語り"]]
    speakers = ["ナレーション"] + sorted(filtered_spks)

    return {
        "status": "success",
        "storyboard": cuts,
        "normalized_script": normalized_script,
        "speakers": speakers,
        "total_cuts": len(cuts)
    }

@app.get("/api/current-storyboard")
async def get_current_storyboard():
    json_path = INPUT_DIR / "studio_project_storyboard.json"
    txt_path = INPUT_DIR / "studio_project.txt"
    script_text = ""
    cuts = []

    if txt_path.exists():
        with open(txt_path, "r", encoding="utf-8") as f:
            script_text = f.read()

    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            cuts = json.load(f)

    return {
        "status": "success",
        "script": script_text,
        "storyboard": cuts,
        "total_cuts": len(cuts)
    }

@app.get("/api/status")
async def get_status():
    global production_state
    proj = production_state.get("current_project")
    if not proj and OUTPUT_DIR.exists():
        subdirs = [d for d in os.listdir(OUTPUT_DIR) if (OUTPUT_DIR / d).is_dir()]
        if subdirs:
            proj = sorted(subdirs, key=lambda d: os.path.getmtime(OUTPUT_DIR / d))[-1]
            production_state["current_project"] = proj

    return production_state

@app.get("/api/assets")
async def get_assets(project: Optional[str] = None):
    target_proj = project or production_state.get("current_project")
    if not target_proj and OUTPUT_DIR.exists():
        subdirs = [d for d in os.listdir(OUTPUT_DIR) if (OUTPUT_DIR / d).is_dir()]
        if subdirs:
            target_proj = sorted(subdirs, key=lambda d: os.path.getmtime(OUTPUT_DIR / d))[-1]

    if not target_proj:
        target_proj = "studio_project"

    target_dir = OUTPUT_DIR / target_proj
    images = []

    if target_dir.exists():
        for root, dirs, files in os.walk(target_dir):
            for f in files:
                ext = f.lower()
                if ext.endswith(('.png', '.jpg', '.jpeg', '.webp', '.mp4')):
                    rel_path = os.path.relpath(os.path.join(root, f), OUTPUT_DIR).replace("\\", "/")
                    images.append({
                        "name": f,
                        "project": target_proj,
                        "url": f"/output_assets/{rel_path}",
                        "is_video": ext.endswith('.mp4')
                    })

    # カット番号順にソート (000, 001, 002...)
    def sort_key(img):
        m = re.match(r'^(\d+)', img["name"])
        return int(m.group(1)) if m else 9999

    images.sort(key=sort_key)
    return {"images": images, "project": target_proj}

# ==========================================
# 素材生成バックグラウンドタスク
# ==========================================
def generate_project_name(script_text: str) -> str:
    theme_match = re.search(r'【選定テーマ】[：:]\s*([^\n]+)', script_text)
    if theme_match:
        clean_theme = re.sub(r'[\\/*?:"<>|、。\s]+', '_', theme_match.group(1).strip())[:25].strip('_')
        date_str = datetime.now().strftime("%Y%m%d_%H%M")
        return f"{date_str}_{clean_theme}"
    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    return f"project_{date_str}"

async def run_production_task(cuts: list, project_name: str, format_ratio: str):
    global production_state
    production_state["is_running"] = True
    production_state["is_completed"] = False
    production_state["progress"] = 5
    production_state["status_text"] = "素材生成準備中..."
    production_state["detail"] = f"全 {len(cuts)} カットの生成を開始します..."

    project_dir = OUTPUT_DIR / project_name
    os.makedirs(project_dir, exist_ok=True)

    generator = AssetGeneratorHook()
    total_cuts = len(cuts)

    for idx, cut in enumerate(cuts):
        if not production_state["is_running"]:
            break

        cut_num = cut.get("cut_number", 0)
        is_video = cut.get("is_video", False)
        ext = ".mp4" if is_video else ".png"
        output_file = project_dir / f"{cut_num:03d}{ext}"

        production_state["status_text"] = f"素材生成中: {idx + 1}/{total_cuts} カット"
        production_state["detail"] = f"Cut_{cut_num:03d} を生成しています..."

        try:
            await generator.generate_asset(cut, str(output_file), format_ratio=format_ratio)
        except Exception as e:
            print(f"[PROD TASK ERROR] Cut_{cut_num:03d}: {e}")

        calc_percent = min(98, 10 + int(((idx + 1) / total_cuts) * 85))
        production_state["progress"] = calc_percent
        production_state["completed_cuts"] = idx + 1

        # リアルタイム表示の演出用ウェイト
        await asyncio.sleep(0.4)

    production_state["is_running"] = False
    production_state["is_completed"] = True
    production_state["progress"] = 100
    production_state["status_text"] = "全素材生成完了"
    production_state["detail"] = f"全 {total_cuts} カットの素材保存が完了しました。"

@app.post("/api/start-production")
async def start_production(req: ScriptRequest, background_tasks: BackgroundTasks):
    global production_state
    if production_state["is_running"]:
        return JSONResponse({"status": "already_running", "message": "現在別の生成ジョブが実行中です。"})

    cuts = parse_script_to_storyboard(
        req.script, 
        style=req.style, 
        genre=req.genre, 
        thumbnail_style=req.thumbnail_style, 
        format=req.format
    )
    if not cuts:
        return JSONResponse({"status": "error", "message": "カットを抽出できませんでした。"}, status_code=400)

    project_name = generate_project_name(req.script)
    production_state["current_project"] = project_name

    # JSON & txt 保存
    with open(INPUT_DIR / f"{project_name}_storyboard.json", "w", encoding="utf-8") as f:
        json.dump(cuts, f, ensure_ascii=False, indent=2)
    with open(INPUT_DIR / f"{project_name}.txt", "w", encoding="utf-8") as f:
        f.write(req.script)
    with open(INPUT_DIR / "studio_project_storyboard.json", "w", encoding="utf-8") as f:
        json.dump(cuts, f, ensure_ascii=False, indent=2)
    with open(INPUT_DIR / "studio_project.txt", "w", encoding="utf-8") as f:
        f.write(req.script)

    background_tasks.add_task(run_production_task, cuts, project_name, req.format)
    return {"status": "started", "project_name": project_name}

@app.post("/api/upload-asset")
async def upload_asset(cut_number: int, file: UploadFile = File(...), project_name: Optional[str] = None):
    """外部システムやWebhookから1カット分の素材を直接アップロード投入するエンドポイント"""
    proj = project_name or production_state.get("current_project", "studio_project")
    proj_dir = OUTPUT_DIR / proj
    os.makedirs(proj_dir, exist_ok=True)

    ext = Path(file.filename).suffix.lower() or ".png"
    target_path = proj_dir / f"{cut_number:03d}{ext}"

    with open(target_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"status": "success", "url": f"/output_assets/{proj}/{target_path.name}", "cut_number": cut_number}

@app.post("/api/regenerate-cut")
async def regenerate_cut(req: RegenerateCutRequest):
    proj = req.project_name or production_state.get("current_project", "studio_project")
    json_path = INPUT_DIR / f"{proj}_storyboard.json"
    if not json_path.exists():
        json_path = INPUT_DIR / "studio_project_storyboard.json"

    if not json_path.exists():
        return JSONResponse({"status": "error", "message": "絵コンテデータが見つかりません。"}, status_code=404)

    with open(json_path, "r", encoding="utf-8") as f:
        cuts = json.load(f)

    target_cut = next((c for c in cuts if c.get("cut_number") == req.cut_number), None)
    if not target_cut:
        return JSONResponse({"status": "error", "message": f"Cut_{req.cut_number} が見つかりません。"}, status_code=404)

    proj_dir = OUTPUT_DIR / proj
    os.makedirs(proj_dir, exist_ok=True)
    out_file = proj_dir / f"{req.cut_number:03d}.png"
    if out_file.exists():
        os.remove(out_file)

    generator = AssetGeneratorHook()
    await generator.generate_asset(target_cut, str(out_file))

    return {"status": "success", "cut_number": req.cut_number, "url": f"/output_assets/{proj}/{out_file.name}"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    print(f"\n========================================================")
    print(f"  Video Studio Hub (Portable Edition)")
    print(f"  Access: http://127.0.0.1:{port}")
    print(f"========================================================\n")
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
