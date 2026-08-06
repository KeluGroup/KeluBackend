@echo off
cd /d "%~dp0"
if not defined PORT set PORT=8000
if exist ".env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" set "%%A=%%B"
  )
)
"venv\Scripts\python.exe" -m uvicorn app:app --reload --port %PORT%
