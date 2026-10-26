@echo off
chcp 65001 >nul
cd /d %~dp0
where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
echo ============================================
echo   LLM 学习助手 Agent   http://127.0.0.1:8787
echo ============================================
timeout /t 1 >nul
start "" http://127.0.0.1:8787
%PY% -m uvicorn backend.main:app --host 127.0.0.1 --port 8787
pause
