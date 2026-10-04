
@echo off
title InsightAI Launcher

echo Starting InsightAI Backend...
start "InsightAI Backend" powershell -NoExit -Command "Set-Location 'C:\AI-Data-Analyst\backend'; .\venv\Scripts\Activate.ps1; uvicorn main:app --reload"

timeout /t 3 /nobreak >nul

echo Starting InsightAI Frontend...
start "InsightAI Frontend" powershell -NoExit -Command "Set-Location 'C:\AI-Data-Analyst\frontend'; npm run dev"

timeout /t 5 /nobreak >nul

echo Opening InsightAI Frontend in Chrome...
start "" chrome.exe "http://localhost:5173/"

echo Opening InsightAI Backend Docs in Chrome...
start "" chrome.exe "http://127.0.0.1:8000/docs"

exit