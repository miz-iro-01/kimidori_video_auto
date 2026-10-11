# ==============================================================================
# KIMIDORI YouTube Auto - ComfyUI + LTX-Video + Cloudflare Tunnel 1発起動コード
# Google Colab のコードセルにそのまま貼り付けて実行してください。
# ==============================================================================
import os
import sys
import time
import socket
import re
import subprocess
from pathlib import Path
from IPython.display import display, HTML

BASE_DIR = Path("/content")
COMFYUI_DIR = BASE_DIR / "ComfyUI"
CUSTOM_NODES_DIR = COMFYUI_DIR / "custom_nodes"
CHECKPOINTS_DIR = COMFYUI_DIR / "models" / "checkpoints"
CLOUDFLARED_PATH = BASE_DIR / "cloudflared"

PORT = 8188
HOST = "127.0.0.1"

# LTX-Video 0.9.1 チェックポイントURL
LTX_MODEL_URL = "https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltx-video-2b-v0.9.1.safetensors"
LTX_MODEL_PATH = CHECKPOINTS_DIR / "ltx-video-2b-v0.9.1.safetensors"
CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"

def log(tag: str, message: str):
    print(f"[{tag.upper()}] {message}", flush=True)

# 1. 既存プロセスのクリーンアップ
subprocess.run(["pkill", "-f", "python main.py"], stderr=subprocess.DEVNULL)
subprocess.run(["pkill", "-f", "cloudflared"], stderr=subprocess.DEVNULL)

# 2. ComfyUI 本体のクローン & 依存関係セットアップ
if not COMFYUI_DIR.exists():
    log("info", "ComfyUI が見つかりません。リポジトリを自動クローンします...")
    subprocess.run(["git", "clone", "https://github.com/comfyanonymous/ComfyUI.git", str(COMFYUI_DIR)], check=True)
    log("info", "ComfyUI の依存パッケージをインストールします...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(COMFYUI_DIR / "requirements.txt")], check=True)
else:
    log("info", "ComfyUI は既に配置されています。")

# 3. カスタムノード (ComfyUI-VideoHelperSuite: 動画結合用)
vhs_dir = CUSTOM_NODES_DIR / "ComfyUI-VideoHelperSuite"
if not vhs_dir.exists():
    log("info", "ComfyUI-VideoHelperSuite (VHS) をクローンします...")
    subprocess.run(["git", "clone", "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git", str(vhs_dir)], check=True)
    vhs_req = vhs_dir / "requirements.txt"
    if vhs_req.exists():
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(vhs_req)], check=True)
else:
    log("info", "ComfyUI-VideoHelperSuite は導入済みです。")

# 4. LTX-Video モデルチェックポイントの高速ダウンロード
CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
if not LTX_MODEL_PATH.exists():
    log("info", f"LTX-Video モデルをダウンロードします: {LTX_MODEL_PATH.name}")
    has_aria2 = subprocess.run(["which", "aria2c"], stdout=subprocess.DEVNULL).returncode == 0
    if not has_aria2:
        subprocess.run(["apt-get", "update", "-qq"], stdout=subprocess.DEVNULL)
        subprocess.run(["apt-get", "install", "-y", "-qq", "aria2"], stdout=subprocess.DEVNULL)
        has_aria2 = True

    if has_aria2:
        subprocess.run([
            "aria2c", "--console-log-level=error", "-c", "-x", "16", "-s", "16", "-k", "1M",
            LTX_MODEL_URL, "-d", str(CHECKPOINTS_DIR), "-o", LTX_MODEL_PATH.name
        ], check=True)
    else:
        subprocess.run(["wget", "-c", LTX_MODEL_URL, "-O", str(LTX_MODEL_PATH)], check=True)
    log("info", "LTX-Video モデルのダウンロードが完了しました。")
else:
    log("info", f"LTX-Video モデルは既に存在します: {LTX_MODEL_PATH.name}")

# 5. Cloudflared の準備
if not CLOUDFLARED_PATH.exists():
    log("info", "Cloudflared をダウンロードします...")
    subprocess.run(["wget", "-q", "-nc", CLOUDFLARED_URL, "-O", str(CLOUDFLARED_PATH)], check=True)
    subprocess.run(["chmod", "+x", str(CLOUDFLARED_PATH)], check=True)

# 6. ComfyUI サーバーのバックグラウンド起動 & ポート監視
log("info", f"ComfyUI をバックグラウンドで起動します (ポート: {PORT})...")
comfy_proc = subprocess.Popen(
    [sys.executable, "main.py", "--listen", HOST, "--port", str(PORT), "--preview-method", "auto"],
    cwd=str(COMFYUI_DIR),
    stdout=subprocess.DEVNULL,
    stderr=subprocess.STDOUT
)

def wait_for_port(host: str, port: int, timeout: int = 120) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(2.0)
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(1.5)
    return False

log("info", f"ポート {PORT} のリッスン待機中...")
if not wait_for_port(HOST, PORT, timeout=120):
    log("error", "ComfyUI の起動がタイムアウトしました。")
    comfy_proc.terminate()
    sys.exit(1)

log("info", f"ComfyUI サーバーが正常に起動しました (127.0.0.1:{PORT})。")

# 7. Cloudflare Tunnel 起動 & 公開URL抽出
log("info", "Cloudflare Tunnel を起動して公開URLを取得します...")
tunnel_proc = subprocess.Popen(
    [str(CLOUDFLARED_PATH), "tunnel", "--url", f"http://{HOST}:{PORT}"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

public_url = None
url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
start_time = time.time()

while time.time() - start_time < 30:
    line = tunnel_proc.stderr.readline()
    if not line:
        continue
    match = url_pattern.search(line)
    if match:
        public_url = match.group(0)
        break

if public_url:
    banner_html = f"""
    <div style="border: 2px solid #00d2ff; background-color: #0f172a; color: #f8fafc; padding: 20px; border-radius: 8px; margin: 15px 0; font-family: monospace;">
        <div style="font-size: 16px; font-weight: bold; margin-bottom: 10px; color: #00d2ff;">[ComfyUI LTX-Video 稼働開始]</div>
        <div style="margin-bottom: 12px; font-size: 14px;">以下の公開URLをコピーし、YouTubeツールの「管理者ダッシュボード」または「Pro版ショート動画」に貼り付けてください:</div>
        <div style="background-color: #1e293b; padding: 10px 14px; border-radius: 6px; font-size: 16px; border-left: 4px solid #00d2ff;">
            <a href="{public_url}" target="_blank" style="color: #38bdf8; text-decoration: underline; font-weight: bold;">{public_url}</a>
        </div>
        <div style="margin-top: 10px; font-size: 12px; color: #94a3b8;">
            * モデル: models/checkpoints/ltx-video-2b-v0.9.1.safetensors (ロード完了)<br>
            * 拡張機能: ComfyUI-VideoHelperSuite (VHS) 導入完了
        </div>
    </div>
    """
    display(HTML(banner_html))
    log("info", f"公開URL: {public_url}")
else:
    log("error", "Cloudflare URLの取得に失敗しました。")
