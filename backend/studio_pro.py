"""
KIMIDORI Studio Pro - Phase 2 backend
  - Jet-cut audio assembly (silence ranges removed, clips packed forward)
  - Wipe overlay (live face video / talking character) at the bottom-right
  - Pexels B-roll cut-in (context keyword search and timed overlay)
  - Studio telop clips (free text / size / colour / timing)
  - Asset upload endpoints (face video, character image, B-roll, BGM)
"""
import array
import json
import logging
import math
import re
import shutil
import subprocess
import wave
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import config

logger = logging.getLogger(__name__)
router = APIRouter()

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
ALLOWED_KINDS = {"face_video", "character_image", "broll", "bgm"}


def _studio_dir(job_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_\-]", "", job_id)
    d = config.TMP_DIR / safe / "studio"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run(cmd: List[str]) -> None:
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0:
        err = (res.stderr or b"").decode("utf-8", errors="ignore")[-600:]
        raise RuntimeError(f"ffmpeg failed: {err}")


def probe_video(path: Path) -> Tuple[int, int, float]:
    res = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration", "-of", "json", str(path)],
        capture_output=True,
    )
    data = json.loads((res.stdout or b"{}").decode("utf-8", errors="ignore") or "{}")
    st = (data.get("streams") or [{}])[0]
    dur = float((data.get("format") or {}).get("duration") or 0.0)
    return int(st.get("width") or 1080), int(st.get("height") or 1920), dur


def probe_audio_duration(path: Path) -> float:
    res = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True,
    )
    try:
        return float((res.stdout or b"0").decode().strip() or 0.0)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Jet-cut audio assembly
# ---------------------------------------------------------------------------
def build_jetcut_audio(src: Path, dst: Path, keep: List[List[float]]) -> bool:
    """Concatenate the kept ranges of src into dst (silence removed)."""
    ranges = [(max(0.0, float(a)), float(b)) for a, b in keep if float(b) - float(a) > 0.02]
    if not ranges or not src.exists():
        return False
    parts = []
    labels = []
    for i, (a, b) in enumerate(ranges):
        parts.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS[a{i}]")
        labels.append(f"[a{i}]")
    if len(ranges) == 1:
        flt = parts[0].replace("[a0]", "[aout]")
    else:
        flt = ";".join(parts) + ";" + "".join(labels) + f"concat=n={len(ranges)}:v=0:a=1[aout]"
    _run([FFMPEG, "-y", "-loglevel", "error", "-i", str(src), "-filter_complex", flt,
          "-map", "[aout]", "-c:a", "libmp3lame", "-q:a", "3", str(dst)])
    return dst.exists() and dst.stat().st_size > 200


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------
def _make_mask(path: Path, size: int, shape: str) -> None:
    from PIL import Image, ImageDraw
    scale = 4
    big = Image.new("L", (size * scale, size * scale), 0)
    d = ImageDraw.Draw(big)
    if shape == "circle":
        d.ellipse((0, 0, size * scale - 1, size * scale - 1), fill=255)
    else:
        d.rounded_rectangle((0, 0, size * scale - 1, size * scale - 1), radius=int(size * scale * 0.18), fill=255)
    big.resize((size, size), Image.LANCZOS).save(path, "PNG")


def _draw_ring(img, shape: str, width: int):
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    s = img.size[0]
    if shape == "circle":
        d.ellipse((1, 1, s - 2, s - 2), outline=(255, 255, 255), width=width)
    else:
        d.rounded_rectangle((1, 1, s - 2, s - 2), radius=int(s * 0.18), outline=(255, 255, 255), width=width)
    return img


def audio_envelope(video: Path, fps: int, work_dir: Path) -> List[float]:
    """Return a normalised 0..1 loudness value per animation frame."""
    wav_path = work_dir / "wipe_env.wav"
    _run([FFMPEG, "-y", "-loglevel", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
          "-f", "wav", str(wav_path)])
    with wave.open(str(wav_path), "rb") as wf:
        n = wf.getnframes()
        rate = wf.getframerate()
        raw = wf.readframes(n)
    samples = array.array("h")
    samples.frombytes(raw[: (len(raw) // 2) * 2])
    win = max(1, int(rate / fps))
    vals: List[float] = []
    for i in range(0, len(samples), win):
        chunk = samples[i:i + win]
        if not chunk:
            break
        acc = sum(c * c for c in chunk) / len(chunk)
        vals.append(math.sqrt(acc))
    if not vals:
        return []
    ordered = sorted(vals)
    ref = ordered[int(len(ordered) * 0.95)] or max(vals) or 1.0
    norm = [min(1.0, v / ref) for v in vals]
    smooth: List[float] = []
    prev = 0.0
    for v in norm:
        prev = prev * 0.45 + v * 0.55
        smooth.append(prev)
    return smooth


def render_talking_character(image_path: Path, env: List[float], out_mp4: Path, size: int,
                             shape: str, mouth_overlay: bool, border: bool, fps: int = 15) -> None:
    """Render a looping-free talking character wipe video driven by the narration loudness."""
    from PIL import Image, ImageDraw
    src = Image.open(image_path).convert("RGB")
    w, h = src.size
    side = min(w, h)
    left = (w - side) // 2
    top = max(0, int((h - side) * 0.25)) if h > w else (h - side) // 2
    src = src.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)

    cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{size}x{size}", "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264",
           "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(out_mp4)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    split_y = int(size * 0.62)
    upper = src.crop((0, 0, size, split_y))
    lower = src.crop((0, split_y, size, size))
    ring_w = max(3, size // 45)
    try:
        for i, a in enumerate(env):
            t = i / fps
            canvas = Image.new("RGB", (size, size), (11, 15, 25))
            stretch = 1.0 + 0.16 * a
            new_lower = lower.resize((size, max(1, int((size - split_y) * stretch))), Image.BILINEAR)
            canvas.paste(upper, (0, 0))
            canvas.paste(new_lower, (0, split_y))
            if mouth_overlay:
                d = ImageDraw.Draw(canvas)
                mw = size * 0.17
                mh = size * (0.012 + 0.075 * a)
                cx, cy = size * 0.5, size * 0.745
                d.ellipse((cx - mw / 2, cy - mh / 2, cx + mw / 2, cy + mh / 2), fill=(60, 12, 20))
            zoom = 1.0 + 0.035 * a
            zs = int(size * zoom)
            canvas = canvas.resize((zs, zs), Image.BILINEAR)
            bob = math.sin(t * 2 * math.pi * 1.4) * size * 0.012
            ox = (zs - size) // 2
            oy = max(0, min(zs - size, int((zs - size) // 2 + bob)))
            canvas = canvas.crop((ox, oy, ox + size, oy + size))
            if border:
                canvas = _draw_ring(canvas, shape, ring_w)
            proc.stdin.write(canvas.tobytes())
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("talking character render failed")


def _render_telop_png(path: Path, width: int, height: int, text: str, size_pct: float,
                      color: str, font_key: Optional[str], y_pct: float) -> None:
    from PIL import Image, ImageDraw
    from processors.batch_asset_generator import BatchAssetGenerator
    gen = BatchAssetGenerator()
    font_px = max(24, int(width * 0.058 * (size_pct / 100.0)))
    font = gen._get_font(font_px, font_key)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    lines = [ln for ln in text.replace("\r", "").split("\n") if ln.strip()] or [text]
    for _ in range(8):
        widest = max(d.textbbox((0, 0), ln, font=font, stroke_width=max(3, font_px // 9))[2] for ln in lines)
        if widest <= width - 40 or font_px <= 24:
            break
        font_px = int(font_px * 0.88)
        font = gen._get_font(font_px, font_key)
    line_h = int(font_px * 1.25)
    total_h = line_h * len(lines)
    y0 = int(height * (y_pct / 100.0) - total_h / 2)
    stroke = max(3, font_px // 9)
    rgb = color if re.match(r"^#[0-9a-fA-F]{6}$", color or "") else "#FFE600"
    for i, ln in enumerate(lines):
        bbox = d.textbbox((0, 0), ln, font=font, stroke_width=stroke)
        tw = bbox[2] - bbox[0]
        x = max(8, (width - tw) // 2)
        d.text((x, y0 + i * line_h), ln, font=font, fill=rgb, stroke_width=stroke, stroke_fill=(0, 0, 0))
    img.save(path, "PNG")


def _download(url: str, dst: Path) -> bool:
    try:
        with httpx.stream("GET", url, timeout=60, follow_redirects=True) as r:
            r.raise_for_status()
            with open(dst, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        return dst.exists() and dst.stat().st_size > 500
    except Exception as e:
        logger.warning(f"B-roll download failed: {e}")
        return False


def _resolve_local(job_id_dir: Path, url: str) -> Optional[Path]:
    m = re.search(r"/api/studio/[^/]+/file/([^?]+)", url or "")
    if m:
        p = job_id_dir / "studio" / Path(m.group(1)).name
        return p if p.exists() else None
    return None


# ---------------------------------------------------------------------------
# Main post process
# ---------------------------------------------------------------------------
def apply_studio_postprocess(job_dir: Path, video_path: Path, state: Dict[str, Any], work_dir: Path) -> Dict[str, Any]:
    studio = state.get("studio") or {}
    wipe = studio.get("wipe") or {}
    broll = [b for b in (studio.get("broll") or []) if b.get("enabled", True) and b.get("url")]
    telops = [t for t in (studio.get("telops") or []) if (t.get("text") or "").strip()]
    telops_on = bool(studio.get("telops_override")) and telops
    wipe_on = bool(wipe.get("enabled")) and (wipe.get("face_url") or wipe.get("char_url"))

    summary = {"broll": 0, "wipe": False, "telops": 0}
    if not (broll or wipe_on or telops_on):
        return summary

    width, height, dur = probe_video(video_path)
    if dur <= 0:
        return summary
    work = work_dir / "studio_pp"
    work.mkdir(parents=True, exist_ok=True)

    inputs: List[str] = ["-i", str(video_path)]
    filters: List[str] = ["[0:v]null[v0]"]
    cur = "v0"
    nxt = 1  # next ffmpeg input index
    stage = 0

    # B-roll
    for i, b in enumerate(broll):
        start = max(0.0, float(b.get("start") or 0.0))
        bdur = max(0.5, float(b.get("duration") or 4.0))
        end = min(dur, start + bdur)
        if end - start < 0.3:
            continue
        ext = ".jpg" if b.get("kind") == "photo" else ".mp4"
        local = work / f"broll_{i:02d}{ext}"
        src_local = _resolve_local(job_dir, b["url"])
        if src_local:
            shutil.copy2(src_local, local)
        elif not _download(b["url"], local):
            continue
        if b.get("kind") == "photo":
            inputs += ["-loop", "1", "-framerate", "30", "-t", f"{end:.2f}", "-i", str(local)]
        else:
            inputs += ["-stream_loop", "-1", "-t", f"{end:.2f}", "-i", str(local)]
        k = nxt
        nxt += 1
        filters.append(
            f"[{k}:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
            f"setsar=1,fps=30,format=yuv420p,setpts=PTS-STARTPTS+{start:.3f}/TB[b{i}]"
        )
        stage += 1
        filters.append(
            f"[{cur}][b{i}]overlay=enable='between(t,{start:.3f},{end:.3f})':eof_action=pass[s{stage}]"
        )
        cur = f"s{stage}"
        summary["broll"] += 1

    # Wipe
    if wipe_on:
        shape = "circle" if wipe.get("shape") != "rounded" else "rounded"
        size = int(width * max(0.12, min(0.5, float(wipe.get("size_pct") or 26) / 100.0)))
        size -= size % 2
        cx = float(wipe.get("x_pct") if wipe.get("x_pct") is not None else 80) / 100.0
        cy = float(wipe.get("y_pct") if wipe.get("y_pct") is not None else 62) / 100.0
        x = int(max(0, min(width - size, cx * width - size / 2)))
        y = int(max(0, min(height - size, cy * height - size / 2)))
        mask = work / "wipe_mask.png"
        _make_mask(mask, size, shape)
        wipe_src: Optional[Path] = None
        if wipe.get("mode") == "face" and wipe.get("face_url"):
            wipe_src = _resolve_local(job_dir, wipe["face_url"])
        elif wipe.get("char_url"):
            img = _resolve_local(job_dir, wipe["char_url"])
            if img:
                env = audio_envelope(video_path, 15, work)
                if env:
                    wipe_src = work / "wipe_char.mp4"
                    render_talking_character(img, env, wipe_src, size, shape,
                                             bool(wipe.get("mouth_overlay", True)), bool(wipe.get("border", True)))
        if wipe_src and wipe_src.exists():
            is_face = wipe.get("mode") == "face"
            inputs += ["-stream_loop", "-1", "-t", f"{dur:.2f}", "-i", str(wipe_src)] if is_face else \
                      ["-t", f"{dur:.2f}", "-i", str(wipe_src)]
            kv = nxt
            nxt += 1
            inputs += ["-loop", "1", "-framerate", "30", "-t", f"{dur:.2f}", "-i", str(mask)]
            km = nxt
            nxt += 1
            filters.append(
                f"[{kv}:v]scale={size}:{size}:force_original_aspect_ratio=increase,crop={size}:{size},"
                f"setsar=1,fps=30,format=rgba[wf]"
            )
            filters.append(f"[{km}:v]scale={size}:{size},format=gray[wm]")
            filters.append("[wf][wm]alphamerge[wa]")
            stage += 1
            filters.append(f"[{cur}][wa]overlay={x}:{y}:eof_action=pass[s{stage}]")
            cur = f"s{stage}"
            summary["wipe"] = True

    # Studio telops
    if telops_on:
        for i, t in enumerate(telops):
            s = max(0.0, float(t.get("start") or 0.0))
            e = min(dur, float(t.get("end") or (s + 2.0)))
            if e - s < 0.2:
                continue
            png = work / f"telop_{i:03d}.png"
            _render_telop_png(png, width, height, str(t.get("text")), float(t.get("size") or 100),
                              str(t.get("color") or "#FFE600"), t.get("font"), float(t.get("y_pct") or 76))
            inputs += ["-loop", "1", "-framerate", "30", "-t", f"{dur:.2f}", "-i", str(png)]
            k = nxt
            nxt += 1
            stage += 1
            filters.append(f"[{k}:v]format=rgba[t{i}]")
            filters.append(f"[{cur}][t{i}]overlay=0:0:enable='between(t,{s:.3f},{e:.3f})':eof_action=pass[s{stage}]")
            cur = f"s{stage}"
            summary["telops"] += 1

    if cur == "v0":
        return summary

    out_tmp = work / "studio_out.mp4"
    script_path = work / "studio_filters.txt"
    script_path.write_text(";\n".join(filters), encoding="utf-8")
    cmd = [FFMPEG, "-y", "-loglevel", "error"] + inputs + [
        "-filter_complex_script", str(script_path), "-map", f"[{cur}]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "copy", "-t", f"{dur:.2f}", str(out_tmp)
    ]
    _run(cmd)
    if out_tmp.exists() and out_tmp.stat().st_size > 1000:
        shutil.copy2(out_tmp, video_path)
    return summary


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@router.post("/api/studio/{job_id}/upload-asset")
async def upload_studio_asset(job_id: str, kind: str = Form(...), file: UploadFile = File(...)):
    if kind not in ALLOWED_KINDS:
        raise HTTPException(status_code=400, detail="unsupported kind")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")
    default_ext = {"face_video": ".mp4", "character_image": ".png", "broll": ".mp4", "bgm": ".mp3"}[kind]
    ext = Path(file.filename or "").suffix.lower() or default_ext
    ts = int(datetime.utcnow().timestamp() * 1000)
    if kind == "bgm":
        bgm_dir = config.DATA_DIR / "bgm"
        bgm_dir.mkdir(parents=True, exist_ok=True)
        name = f"user_bgm_{ts}{ext if ext in ('.mp3', '.wav', '.m4a', '.ogg') else '.mp3'}"
        (bgm_dir / name).write_bytes(raw)
        return {"success": True, "kind": kind, "name": name, "bgm_choice": name}
    name = f"{kind}_{ts}{ext}"
    (_studio_dir(job_id) / name).write_bytes(raw)
    return {"success": True, "kind": kind, "name": name,
            "url": f"/api/studio/{re.sub(r'[^A-Za-z0-9_-]', '', job_id)}/file/{name}"}


@router.get("/api/studio/{job_id}/file/{name}")
async def get_studio_file(job_id: str, name: str):
    p = _studio_dir(job_id) / Path(name).name
    if not p.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(p))


class PexelsSearchRequest(BaseModel):
    query: str
    pexels_api_key: str = ""
    gemini_api_key: str = ""
    kind: str = Field("video", description="video / photo")
    orientation: str = Field("portrait", description="portrait / landscape")
    per_page: int = 6


async def _translate_query(query: str, gemini_key: str) -> str:
    if not gemini_key or all(ord(c) < 128 for c in query):
        return query
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
        body = {"contents": [{"parts": [{"text":
                "Translate this Japanese keyword into 1 to 3 concrete English stock-footage search words. "
                f"Return only the words.\n{query}"}]}]}
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, params={"key": gemini_key}, json=body)
            r.raise_for_status()
            txt = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            return re.sub(r"[^A-Za-z0-9 ]", "", txt)[:60] or query
    except Exception as e:
        logger.warning(f"keyword translate failed: {e}")
        return query


@router.post("/api/studio/pexels-search")
async def studio_pexels_search(req: PexelsSearchRequest):
    if not req.pexels_api_key:
        raise HTTPException(status_code=400, detail="Pexels APIキーが未設定です（設定画面で登録してください）")
    q = await _translate_query(req.query.strip(), req.gemini_api_key)
    headers = {"Authorization": req.pexels_api_key}
    items: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            if req.kind == "photo":
                r = await client.get("https://api.pexels.com/v1/search", headers=headers,
                                     params={"query": q, "per_page": req.per_page, "orientation": req.orientation})
                r.raise_for_status()
                for p in r.json().get("photos", []):
                    items.append({"id": p["id"], "kind": "photo", "thumb": p["src"]["medium"],
                                  "url": p["src"]["large2x"], "duration": 0})
            else:
                r = await client.get("https://api.pexels.com/videos/search", headers=headers,
                                     params={"query": q, "per_page": req.per_page, "orientation": req.orientation})
                r.raise_for_status()
                for v in r.json().get("videos", []):
                    files = sorted([f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4"],
                                   key=lambda f: abs((f.get("width") or 0) - 1080))
                    if not files:
                        continue
                    items.append({"id": v["id"], "kind": "video", "thumb": v.get("image"),
                                  "url": files[0]["link"], "duration": v.get("duration", 0)})
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"素材検索に失敗しました ({e.response.status_code})")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"素材検索に失敗しました: {e}")
    return {"success": True, "query": q, "items": items}


class CharacterRefGenerateRequest(BaseModel):
    name: str = Field("主人公", description="キャラクター名")
    role: str = Field("メインキャラ", description="役割（主人公/メンター/同僚など）")
    clothing: str = Field("", description="服装の特徴（例: ネイビースーツ、白衣など）")
    hairstyle: str = Field("", description="髪型の特徴（例: 黒髪ショート、ポニーテールなど）")
    appearance: str = Field("", description="容姿・特徴（例: 20代後半、知的な眼鏡、穏やかな表情など）")
    visual_style: str = Field("anime_modern", description="ビジュアルスタイル")
    comic_color_mode: str = Field("color", description="color / monochrome")
    gemini_api_key: str = ""
    paid_gemini_api_key: str = ""


def _render_illustrated_character_portrait(
    name: str,
    role: str,
    clothing: str,
    hairstyle: str,
    appearance: str,
    visual_style: str = "anime_modern",
    monochrome: bool = False
):
    from PIL import Image, ImageDraw
    from processors.batch_asset_generator import BatchAssetGenerator
    gen = BatchAssetGenerator()
    w, h = 768, 768
    img = gen._generate_artistic_backdrop(w, h, f"{name} {clothing} {hairstyle}", 1, genre="business")
    draw = ImageDraw.Draw(img)

    # キャラクターのバストアップシルエット＆コミックフレーム装飾
    cx, cy = w // 2, int(h * 0.44)
    # 背面ハローサークル
    draw.ellipse((cx - 190, cy - 190, cx + 190, cy + 190), fill=(16, 185, 129), outline=(255, 255, 255), width=6)
    draw.ellipse((cx - 176, cy - 176, cx + 176, cy + 176), fill=(15, 23, 42))
    # 肩・スーツ/衣装シルエット
    draw.rounded_rectangle((cx - 135, cy + 45, cx + 135, cy + 210), radius=48, fill=(30, 58, 138), outline=(255, 255, 255), width=4)
    # 襟・ネクタイアクセント
    draw.polygon([(cx - 32, cy + 48), (cx + 32, cy + 48), (cx, cy + 135)], fill=(248, 250, 252))
    draw.polygon([(cx - 10, cy + 68), (cx + 10, cy + 68), (cx + 14, cy + 150), (cx, cy + 170), (cx - 14, cy + 150)], fill=(16, 185, 129))
    # 頭部・顔輪郭
    draw.ellipse((cx - 72, cy - 105, cx + 72, cy + 48), fill=(254, 226, 202), outline=(15, 23, 42), width=4)
    # 髪型シルエット
    draw.pieslice((cx - 80, cy - 122, cx + 80, cy + 10), start=170, end=10, fill=(24, 30, 44))
    # 目・表情
    draw.ellipse((cx - 34, cy - 32, cx - 18, cy - 16), fill=(15, 23, 42))
    draw.ellipse((cx + 18, cy - 32, cx + 34, cy - 16), fill=(15, 23, 42))
    draw.arc((cx - 22, cy - 4, cx + 22, cy + 22), start=15, end=165, fill=(15, 23, 42), width=3)

    # 下部キャラクターシート情報プレート
    font_title = gen._get_font(34, "MPLUSRounded1c")
    font_sub = gen._get_font(22, "MPLUSRounded1c")
    draw.rounded_rectangle((36, h - 185, w - 36, h - 28), radius=16, fill=(11, 15, 25), outline=(16, 185, 129), width=3)
    draw.text((60, h - 168), f"{name} [{role}]", font=font_title, fill=(255, 255, 255))
    trait_line1 = f"服装: {clothing or 'ビジネスカジュアル'} / 髪型: {hairstyle or 'ナチュラル'}"
    trait_line2 = f"特徴: {appearance or '知的・共感型キャラクター'} ({visual_style})"
    draw.text((60, h - 116), trait_line1[:34], font=font_sub, fill=(167, 243, 208))
    draw.text((60, h - 78), trait_line2[:36], font=font_sub, fill=(148, 163, 184))

    if monochrome or visual_style == "comic_manga_mono":
        img = gen._apply_monochrome_manga_filter(img)
    return img


@router.post("/api/studio/generate-character-ref")
async def generate_character_ref_endpoint(req: CharacterRefGenerateRequest):
    """
    Phase 3: 長尺動画・ビジネス漫画用のキャラクター一貫性（キャラ固定）リファレンス画像をその場でAI生成する。
    """
    import base64
    from io import BytesIO
    from processors.batch_asset_generator import BatchAssetGenerator, VISUAL_STYLE_CONFIGS

    name = (req.name or "主人公").strip()
    role = (req.role or "メインキャラ").strip()
    clothing = (req.clothing or "").strip()
    hairstyle = (req.hairstyle or "").strip()
    appearance = (req.appearance or "").strip()
    style_key = (req.visual_style or "anime_modern").strip()
    is_mono = (req.comic_color_mode or "").lower() == "monochrome" or style_key == "comic_manga_mono"
    if style_key == "comic_manga" and is_mono:
        style_key = "comic_manga_mono"

    style_cfg = VISUAL_STYLE_CONFIGS.get(style_key, VISUAL_STYLE_CONFIGS["anime_modern"])
    jp_traits = ", ".join(filter(None, [clothing, hairstyle, appearance])) or "Japanese business person, smart casual attire, expressive face"

    eff_key = (req.paid_gemini_api_key or req.gemini_api_key or config.GEMINI_API_KEY or "").strip()
    appearance_prompt_en = f"single character {name} ({role}), {jp_traits}, {style_cfg['scene_desc']}"

    if eff_key and any(ord(c) >= 128 for c in jp_traits):
        try:
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
            body = {
                "contents": [{
                    "parts": [{
                        "text": (
                            "Convert the following Japanese character traits (name, role, clothing, hairstyle, appearance) "
                            "into a concise, comma-separated English visual character sheet prompt for consistent image generation. "
                            "Return ONLY the English description phrase.\n"
                            f"Name: {name}, Role: {role}, Traits: {jp_traits}"
                        )
                    }]
                }]
            }
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(url, params={"key": eff_key}, json=body)
                if r.status_code == 200:
                    en_txt = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if en_txt:
                        appearance_prompt_en = f"single character {name}, {en_txt}, {style_cfg['scene_desc']}"
        except Exception as tr_err:
            logger.warning(f"Character trait translation skipped: {tr_err}")

    gen = BatchAssetGenerator()
    pil_img = None
    if eff_key:
        try:
            master_prompt = (
                f"{style_cfg['master_prefix']} of {name}, {appearance_prompt_en}. "
                f"Centered single figure in a single unified frame. {style_cfg['master_suffix']}"
            )
            pil_img = await gen._generate_with_gemini_nanobanana(
                api_key=eff_key,
                prompt=master_prompt,
                target_size=(768, 768),
                aspect_ratio="1:1",
                visual_style=style_key
            )
            if pil_img and is_mono:
                pil_img = gen._apply_monochrome_manga_filter(pil_img)
        except Exception as nb_err:
            logger.warning(f"NanoBanana character ref gen fallback: {nb_err}")

    if pil_img is None:
        pil_img = _render_illustrated_character_portrait(
            name=name,
            role=role,
            clothing=clothing,
            hairstyle=hairstyle,
            appearance=appearance,
            visual_style=style_key,
            monochrome=is_mono
        )

    buf = BytesIO()
    pil_img.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return {
        "success": True,
        "label": name,
        "role": role,
        "clothing": clothing,
        "hairstyle": hairstyle,
        "appearance": appearance,
        "appearance_prompt_en": appearance_prompt_en,
        "visual_style": style_key,
        "data_url": f"data:image/png;base64,{b64}"
    }

