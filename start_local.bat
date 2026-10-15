@echo off
chcp 65001 >nul
echo ========================================================
echo   KIMIDORI YouTube Auto - ローカル開発サーバー起動
echo ========================================================
echo.
echo [1/2] 仮想環境の確認...
if not exist "backend\venv\Scripts\uvicorn.exe" (
    echo [ERROR] backend\venv\Scripts\uvicorn.exe が見つかりません。
    pause
    exit /b 1
)

echo [2/2] ローカルサーバーを起動しています (ポート 8080)...
echo.
echo 以下のURLをブラウザで開いてご利用いただけます:
echo   http://localhost:8080
echo.
echo サーバーを停止するにはこのウィンドウで Ctrl + C を押してください。
echo ========================================================
echo.

start http://localhost:8080
backend\venv\Scripts\uvicorn.exe main:app --app-dir backend --host 127.0.0.1 --port 8080
pause
